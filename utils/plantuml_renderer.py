"""
PlantUML rendering utility — converts PlantUML text into PNG images.

Uses two rendering backends for reliability:
  1. Kroki.io  (primary  — fast, supports POST, no URL-length limits)
  2. PlantUML server (fallback — classic URL-encoded GET)
"""

import zlib
import base64
import requests
import json
from io import BytesIO
from typing import Optional

KROKI_URL = "https://kroki.io/plantuml/png"
PLANTUML_SERVER = "http://www.plantuml.com/plantuml"


# ═══════════════════════════════════════════════════════════════
#  Backend 1: Kroki.io (Primary — simple POST with base64 body)
# ═══════════════════════════════════════════════════════════════

def _render_via_kroki(plantuml_code: str) -> Optional[bytes]:
    """
    Render via Kroki.io — sends diagram source as base64-encoded
    JSON POST body. Very reliable and fast.
    """
    try:
        # Kroki accepts the diagram source directly in JSON
        payload = json.dumps({"diagram_source": plantuml_code})
        r = requests.post(
            KROKI_URL,
            headers={"Content-Type": "application/json"},
            data=payload,
            timeout=30,
        )
        if r.status_code == 200 and len(r.content) > 100:
            return r.content
        print(f"[PlantUML Renderer] Kroki returned HTTP {r.status_code}")
        return None
    except Exception as e:
        print(f"[PlantUML Renderer] Kroki error: {e}")
        return None


# ═══════════════════════════════════════════════════════════════
#  Backend 2: PlantUML Server (Fallback — GET with custom encoding)
# ═══════════════════════════════════════════════════════════════

def _encode_plantuml(text: str) -> str:
    """
    Encode PlantUML text for the server URL using the official
    deflate + custom-base64 scheme.
    """
    data = text.encode("utf-8")
    compressed = zlib.compress(data, 9)[2:-4]  # raw deflate
    return _encode64(compressed)


def _encode64(data: bytes) -> str:
    """PlantUML's custom base64 encoding (different alphabet)."""
    alphabet = (
        "0123456789"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "abcdefghijklmnopqrstuvwxyz"
        "-_"
    )
    result = []
    for i in range(0, len(data), 3):
        chunk = data[i:i + 3]
        if len(chunk) == 3:
            b1, b2, b3 = chunk
            result.append(alphabet[b1 >> 2])
            result.append(alphabet[((b1 & 0x3) << 4) | (b2 >> 4)])
            result.append(alphabet[((b2 & 0xF) << 2) | (b3 >> 6)])
            result.append(alphabet[b3 & 0x3F])
        elif len(chunk) == 2:
            b1, b2 = chunk
            result.append(alphabet[b1 >> 2])
            result.append(alphabet[((b1 & 0x3) << 4) | (b2 >> 4)])
            result.append(alphabet[(b2 & 0xF) << 2])
        elif len(chunk) == 1:
            b1 = chunk[0]
            result.append(alphabet[b1 >> 2])
            result.append(alphabet[(b1 & 0x3) << 4])
    return "".join(result)


def _render_via_plantuml_server(plantuml_code: str) -> Optional[bytes]:
    """Render via the public PlantUML server (GET with encoded URL)."""
    try:
        encoded = _encode_plantuml(plantuml_code)
        url = f"{PLANTUML_SERVER}/png/{encoded}"
        r = requests.get(url, timeout=30)
        if r.status_code == 200 and len(r.content) > 100:
            return r.content
        print(f"[PlantUML Renderer] PlantUML server returned HTTP {r.status_code}")
        return None
    except Exception as e:
        print(f"[PlantUML Renderer] PlantUML server error: {e}")
        return None


# ═══════════════════════════════════════════════════════════════
#  Public API
# ═══════════════════════════════════════════════════════════════

def render_diagram(plantuml_code: str) -> Optional[bytes]:
    """
    Render PlantUML code to PNG bytes.
    Tries Kroki first, falls back to the PlantUML server.
    Returns PNG bytes, or None on failure.
    """
    # Clean up: ensure we only have the @startuml...@enduml block
    code = _clean_plantuml(plantuml_code)

    print(f"[PlantUML Renderer] Rendering diagram ({len(code)} chars)...")

    # Try Kroki first (faster, more reliable)
    img = _render_via_kroki(code)
    if img:
        print(f"[PlantUML Renderer] OK - Kroki rendered successfully ({len(img)} bytes)")
        return img

    # Fallback to PlantUML server
    print("[PlantUML Renderer] Kroki failed, trying PlantUML server...")
    img = _render_via_plantuml_server(code)
    if img:
        print(f"[PlantUML Renderer] OK - PlantUML server rendered ({len(img)} bytes)")
        return img

    print("[PlantUML Renderer] FAIL - Both backends failed")
    return None


def render_to_bytesio(plantuml_code: str) -> Optional[BytesIO]:
    """Render and return as a BytesIO object (for Streamlit st.image)."""
    img_bytes = render_diagram(plantuml_code)
    if img_bytes:
        return BytesIO(img_bytes)
    return None


def get_diagram_url(plantuml_code: str, fmt: str = "png") -> str:
    """Return the PlantUML server URL for the given code."""
    encoded = _encode_plantuml(_clean_plantuml(plantuml_code))
    return f"{PLANTUML_SERVER}/{fmt}/{encoded}"


def _clean_plantuml(code: str) -> str:
    """
    Strip any markdown fences or extra text around the PlantUML block.
    Ensures we only pass @startuml...@enduml to the renderer.
    """
    # Remove markdown code fences
    for fence in ("```plantuml", "```puml", "```uml", "```"):
        code = code.replace(fence, "")

    # Extract only the @startuml...@enduml block
    start = code.find("@startuml")
    end = code.find("@enduml")
    if start != -1 and end != -1:
        return code[start:end + len("@enduml")].strip()

    # If no @startuml found, wrap it
    if "@startuml" not in code:
        code = "@startuml\n" + code.strip() + "\n@enduml"

    return code.strip()
