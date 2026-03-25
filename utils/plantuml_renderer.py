"""
PlantUML rendering utility — converts PlantUML text into PNG images.

Uses two rendering backends for reliability:
  1. Kroki.io  (primary  — fast, supports POST, no URL-length limits)
  2. PlantUML server (fallback — classic URL-encoded GET)
"""

import re
import zlib
import requests
import json
import hashlib
import threading
from io import BytesIO
from collections import OrderedDict
from typing import Optional
from requests.adapters import HTTPAdapter
import config

KROKI_URL = config.KROKI_URL
PLANTUML_SERVER = config.PLANTUML_SERVER
_session: Optional[requests.Session] = None
_render_cache: "OrderedDict[str, bytes]" = OrderedDict()
_cache_lock = threading.RLock()


def _get_session() -> requests.Session:
    """Return a shared HTTP session for connection pooling."""
    global _session
    if _session is None:
        _session = requests.Session()
        adapter = HTTPAdapter(pool_connections=16, pool_maxsize=16, max_retries=0)
        _session.mount("http://", adapter)
        _session.mount("https://", adapter)
    return _session


def _cache_get(key: str) -> Optional[bytes]:
    with _cache_lock:
        value = _render_cache.get(key)
        if value is not None:
            _render_cache.move_to_end(key)
        return value


def _cache_put(key: str, value: bytes):
    with _cache_lock:
        _render_cache[key] = value
        _render_cache.move_to_end(key)
        while len(_render_cache) > config.RENDER_CACHE_MAX_ENTRIES:
            _render_cache.popitem(last=False)


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
        r = _get_session().post(
            KROKI_URL,
            headers={"Content-Type": "application/json"},
            data=payload,
            timeout=30,
        )
        content_type = r.headers.get("content-type", "")
        if r.status_code == 200 and "image" in content_type and len(r.content) > 200:
            return r.content
        if r.status_code != 200:
            body_preview = r.text[:200] if r.text else "(empty)"
            print(f"[PlantUML Renderer] Kroki HTTP {r.status_code}: {body_preview}")
        else:
            print(f"[PlantUML Renderer] Kroki bad response: type={content_type}, len={len(r.content)}")
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


def _render_via_plantuml_server(plantuml_code: str, accept_error_image: bool = False) -> Optional[bytes]:
    """
    Render via the public PlantUML server (GET with encoded URL).
    If accept_error_image is True, accept HTTP 400 responses that
    contain an image (PlantUML server returns error diagrams as PNG).
    """
    try:
        encoded = _encode_plantuml(plantuml_code)
        url = f"{PLANTUML_SERVER}/png/{encoded}"
        r = _get_session().get(url, timeout=30)
        content_type = r.headers.get("content-type", "")
        if r.status_code == 200 and "image" in content_type and len(r.content) > 200:
            return r.content
        # Accept error images (HTTP 400 with image/png) as last resort
        if accept_error_image and r.status_code == 400 and "image" in content_type and len(r.content) > 200:
            print(f"[PlantUML Renderer] PlantUML server: returning error image ({len(r.content)} bytes)")
            return r.content
        print(
            f"[PlantUML Renderer] PlantUML server: HTTP {r.status_code}, "
            f"type={content_type}, len={len(r.content)}"
        )
        return None
    except Exception as e:
        print(f"[PlantUML Renderer] PlantUML server error: {e}")
        return None


# ═══════════════════════════════════════════════════════════════
#  Public API
# ═══════════════════════════════════════════════════════════════

def render_diagram(plantuml_code: str, debug: bool = False) -> Optional[bytes]:
    """
    Render PlantUML code to PNG bytes.

    Tries Kroki first, falls back to the PlantUML server.
    Error images (HTTP 400 with syntax-error PNG) are NOT treated as
    success — they return None so the UI can display a proper error.

    Set debug=True to accept error images for diagnostic purposes only.

    Returns PNG bytes on success, or None on failure.
    """
    # Clean up: ensure we only have the @startuml...@enduml block
    code = _clean_plantuml(plantuml_code)
    # Final sanitization to catch any remaining LLM artifacts
    code = _sanitize_for_render(code)
    cache_key = hashlib.sha256(code.encode("utf-8")).hexdigest()

    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    print(f"[PlantUML Renderer] Rendering diagram ({len(code)} chars)...")

    # Try Kroki first (faster, more reliable)
    img = _render_via_kroki(code)
    if img:
        _cache_put(cache_key, img)
        print(f"[PlantUML Renderer] OK - Kroki rendered successfully ({len(img)} bytes)")
        return img

    # Fallback to PlantUML server (strict — only accept HTTP 200)
    print("[PlantUML Renderer] Kroki failed, trying PlantUML server...")
    img = _render_via_plantuml_server(code)
    if img:
        _cache_put(cache_key, img)
        print(f"[PlantUML Renderer] OK - PlantUML server rendered ({len(img)} bytes)")
        return img

    # Debug mode only: accept error images for diagnostics
    if debug:
        print("[PlantUML Renderer] Debug mode: accepting error image...")
        img = _render_via_plantuml_server(code, accept_error_image=True)
        if img:
            print(f"[PlantUML Renderer] DEBUG - Returning error image ({len(img)} bytes)")
            return img

    print("[PlantUML Renderer] FAIL - All backends failed (syntax error in PlantUML)")
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


def _sanitize_for_render(code: str) -> str:
    """
    Final sanitization pass right before sending to rendering backends.
    Catches common LLM artifacts that slip through the generation pipeline.
    """
    # Remove any remaining markdown artifacts
    code = code.replace("```", "")

    # Remove blank lines between @startuml and the first real line
    code = re.sub(r'(@startuml)\s*\n(\s*\n)+', r'\1\n', code)

    # Remove duplicate @startuml / @enduml
    code = re.sub(r'(@startuml\s*\n?){2,}', '@startuml\n', code, flags=re.IGNORECASE)
    code = re.sub(r'(@enduml\s*\n?){2,}', '@enduml', code, flags=re.IGNORECASE)

    # Remove any text AFTER @enduml (LLM sometimes appends explanations)
    end_idx = code.find('@enduml')
    if end_idx != -1:
        code = code[:end_idx + len('@enduml')]

    # Remove any text BEFORE @startuml (LLM sometimes prepends explanations)
    start_idx = code.find('@startuml')
    if start_idx > 0:
        code = code[start_idx:]

    # Remove lines that are clearly LLM commentary (not PlantUML)
    commentary_prefixes = (
        'here is', "here's", 'below is', 'this diagram',
        'note:', 'explanation:', 'the above', 'as you can see',
        'i hope', 'let me', 'please note', 'sure,', 'certainly',
        'the following', 'this is', 'i have',
    )
    lines = code.split('\n')
    cleaned = []
    for line in lines:
        stripped = line.strip().lower()
        if any(stripped.startswith(p) for p in commentary_prefixes):
            continue
        cleaned.append(line)
    code = '\n'.join(cleaned)

    # Remove empty skinparam blocks: skinparam word { }
    code = re.sub(r'skinparam\s+\w+\s*\{\s*\}', '', code, flags=re.IGNORECASE)

    # Fix common bad arrow syntax that LLMs produce
    # e.g., "-->" with nothing on one side
    code = re.sub(r'^\s*-->\s*$', '', code, flags=re.MULTILINE)
    code = re.sub(r'^\s*<--\s*$', '', code, flags=re.MULTILINE)

    return code.strip()
