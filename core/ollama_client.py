"""
HTTP client for the Ollama API — handles both text generation
(DeepSeek Coder) and health checks.

Performance: uses a shared requests.Session for HTTP connection pooling.
"""

import json
import requests
import re
from typing import Optional, Generator
from requests.adapters import HTTPAdapter
import config


# ── HTTP session for connection pooling ────────────────────────
_session: Optional[requests.Session] = None


def _get_session() -> requests.Session:
    """Return a shared HTTP session for connection pooling."""
    global _session
    if _session is None:
        _session = requests.Session()
        adapter = HTTPAdapter(pool_connections=16, pool_maxsize=16, max_retries=0)
        _session.mount("http://", adapter)
        _session.mount("https://", adapter)
    return _session


# Tokens that models may leak into their output
_LEAK_TOKENS = re.compile(r'<\|im_start\|>|<\|im_end\|>|<\|EOT\|>|<\|endoftext\|>')


def _get_model_runtime_profile(model: str) -> dict:
    """Return the first matching model runtime profile from config."""
    model_name = (model or "").lower()
    profiles = getattr(config, "MODEL_RUNTIME_PROFILES", {})
    for pattern, profile in profiles.items():
        if pattern.lower() in model_name:
            return profile or {}
    return {}


def _clean_response(text: str) -> str:
    """Strip leaked special tokens and <think> blocks from model output."""
    # Remove <think>...</think> blocks (deepseek-coder, qwen2.5-coder)
    cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    # Handle unclosed <think> (model hit token limit mid-thought)
    cleaned = re.sub(r'<think>.*', '', cleaned, flags=re.DOTALL)
    cleaned = _LEAK_TOKENS.sub('', cleaned)
    # Collapse runs of whitespace that remain after stripping
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned.strip()


def check_ollama_status() -> dict:
    """
    Returns {"ok": bool, "models": [...], "error": str|None}.
    """
    try:
        s = _get_session()
        r = s.get(f"{config.OLLAMA_BASE_URL}/api/tags", timeout=5)
        if r.status_code == 200:
            models = [m["name"] for m in r.json().get("models", [])]
            return {"ok": True, "models": models, "error": None}
        return {"ok": False, "models": [], "error": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"ok": False, "models": [], "error": str(e)}


def generate(prompt: str,
             model: str = None,
             temperature: float = None,
             max_tokens: int = None,
             context_size: int = None,
             format_json: bool = False) -> str:
    """
    Synchronous text generation via Ollama /api/generate.
    Returns the full response string.

    If format_json=True, forces Ollama to produce valid JSON output
    by setting the 'format' parameter in the API request.
    """
    model = model or config.LLM_MODEL
    profile = _get_model_runtime_profile(model)
    effective_num_predict = max_tokens or config.LLM_MAX_TOKENS
    predict_cap = profile.get("num_predict_cap")
    if predict_cap:
        effective_num_predict = min(effective_num_predict, predict_cap)

    effective_num_ctx = context_size or config.LLM_CONTEXT_SIZE
    ctx_cap = profile.get("num_ctx_cap")
    if ctx_cap:
        effective_num_ctx = min(effective_num_ctx, ctx_cap)

    options = {
        "temperature": temperature or config.LLM_TEMPERATURE,
        "top_p": config.LLM_TOP_P,
        "top_k": config.LLM_TOP_K,
        "repeat_penalty": config.LLM_REPEAT_PENALTY,
        "num_predict": effective_num_predict,
        "num_ctx": effective_num_ctx,
    }
    for key in ("num_thread", "num_batch", "num_gpu"):
        value = profile.get(key)
        if value is not None:
            options[key] = value

    body = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "keep_alive": config.OLLAMA_KEEP_ALIVE,
        "options": options,
    }
    if format_json and profile.get("use_native_json_mode", True):
        body["format"] = "json"
    try:
        s = _get_session()
        r = s.post(
            f"{config.OLLAMA_BASE_URL}/api/generate",
            json=body,
            timeout=600,
        )
        if r.status_code == 200:
            return _clean_response(r.json().get("response", ""))
        return f"[Ollama error: HTTP {r.status_code}]"
    except Exception as e:
        return f"[Ollama error: {e}]"


def generate_stream(prompt: str,
                    model: str = None) -> Generator[str, None, None]:
    """
    Streaming text generation — yields tokens one at a time.
    Useful for the Streamlit chat interface.
    """
    model = model or config.LLM_MODEL
    profile = _get_model_runtime_profile(model)
    options = {
        "temperature": config.LLM_TEMPERATURE,
        "top_p": config.LLM_TOP_P,
        "top_k": config.LLM_TOP_K,
        "repeat_penalty": config.LLM_REPEAT_PENALTY,
        "num_predict": min(
            config.LLM_MAX_TOKENS,
            profile.get("num_predict_cap", config.LLM_MAX_TOKENS),
        ),
        "num_ctx": min(
            config.LLM_CONTEXT_SIZE,
            profile.get("num_ctx_cap", config.LLM_CONTEXT_SIZE),
        ),
    }
    for key in ("num_thread", "num_batch", "num_gpu"):
        value = profile.get(key)
        if value is not None:
            options[key] = value

    body = {
        "model": model,
        "prompt": prompt,
        "stream": True,
        "keep_alive": config.OLLAMA_KEEP_ALIVE,
        "options": options,
    }
    try:
        s = _get_session()
        r = s.post(
            f"{config.OLLAMA_BASE_URL}/api/generate",
            json=body,
            stream=True,
            timeout=300,
        )
        for line in r.iter_lines(decode_unicode=True):
            if not line:
                continue
            data = json.loads(line)
            token = data.get("response", "")
            if token:
                # Clean leaked tokens from streaming output
                cleaned = _LEAK_TOKENS.sub('', token)
                if cleaned:
                    yield cleaned
            if data.get("done"):
                break
    except Exception as e:
        yield f"\n[Streaming error: {e}]"
