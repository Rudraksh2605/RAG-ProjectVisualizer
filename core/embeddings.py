"""
Embedding service — calls Ollama embedding API.
Auto-detects available model: prefers nomic-embed-text,
falls back to deepseek-coder (which also supports embeddings).

Performance features:
  - HTTP connection pooling via requests.Session
  - Batch embedding using Ollama's /api/embed batch endpoint
  - Parallel fallback for older Ollama versions
"""

import logging
import requests
from typing import List, Optional
import config

log = logging.getLogger("embeddings")

# ── Module-level state (resolved once, reused) ─────────────────
_resolved_model: Optional[str] = None

# ── HTTP session for connection pooling ────────────────────────
_session: Optional[requests.Session] = None


def _get_session() -> requests.Session:
    """Return a shared HTTP session for connection pooling."""
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update({"Content-Type": "application/json"})
    return _session


def _resolve_embedding_model() -> str:
    """Pick the best available embedding model from Ollama."""
    global _resolved_model
    if _resolved_model:
        return _resolved_model

    try:
        s = _get_session()
        r = s.get(f"{config.OLLAMA_BASE_URL}/api/tags", timeout=5)
        if r.status_code == 200:
            models = [m["name"] for m in r.json().get("models", [])]

            # Prefer nomic-embed-text
            for m in models:
                if "nomic-embed-text" in m:
                    _resolved_model = m
                    log.info("Using dedicated embedding model: %s", m)
                    return m

            # Fallback: any model with "embed" in name
            for m in models:
                if "embed" in m.lower():
                    _resolved_model = m
                    log.info("Using embedding model: %s", m)
                    return m

            # Last resort: use the LLM model itself (deepseek-coder)
            for m in models:
                if "deepseek" in m.lower() or "coder" in m.lower() or "qwen" in m.lower():
                    _resolved_model = m
                    log.warning(
                        "No dedicated embedding model found! Falling back to LLM "
                        "model '%s' for embeddings. Retrieval quality will be "
                        "DEGRADED. Run 'ollama pull nomic-embed-text' for better results.",
                        m,
                    )
                    return m

            # Use whatever is first
            if models:
                _resolved_model = models[0]
                log.warning(
                    "No embedding model found. Using first available model '%s'. "
                    "Retrieval quality may be degraded.",
                    models[0],
                )
                return models[0]
    except Exception:
        pass

    # Default from config
    _resolved_model = config.EMBEDDING_MODEL
    log.info("Using default embedding model from config: %s", _resolved_model)
    return _resolved_model


def _call_ollama_embed(model: str, text: str) -> List[float]:
    """
    Embed a single text via Ollama.
    Try both endpoints:
      - /api/embeddings  (older Ollama)
      - /api/embed       (newer Ollama ≥ 0.4)
    """
    base = config.OLLAMA_BASE_URL
    s = _get_session()

    # Try /api/embeddings first (uses "prompt" key)
    try:
        r = s.post(
            f"{base}/api/embeddings",
            json={"model": model, "prompt": text},
            timeout=120,
        )
        if r.status_code == 200:
            emb = r.json().get("embedding", [])
            if emb:
                return emb
    except requests.ConnectionError:
        raise RuntimeError(
            f"Cannot connect to Ollama at {base}. "
            "Make sure Ollama is running."
        )

    # Try /api/embed (newer API, uses "input" key)
    try:
        r = s.post(
            f"{base}/api/embed",
            json={"model": model, "input": text},
            timeout=120,
        )
        if r.status_code == 200:
            data = r.json()
            # Newer API returns {"embeddings": [[...]]}
            embeddings = data.get("embeddings", [])
            if embeddings and len(embeddings) > 0:
                return embeddings[0]
            # Or sometimes {"embedding": [...]}
            emb = data.get("embedding", [])
            if emb:
                return emb
    except Exception:
        pass

    raise RuntimeError(
        f"Embedding failed for model '{model}'. "
        f"Try running: ollama pull nomic-embed-text"
    )


def _call_ollama_embed_batch(model: str, texts: List[str]) -> List[List[float]]:
    """
    Embed multiple texts in a single API call using Ollama's batch
    /api/embed endpoint (supports list input in newer Ollama ≥ 0.4).

    Falls back to individual calls if the batch endpoint is not available.
    """
    base = config.OLLAMA_BASE_URL
    s = _get_session()

    try:
        r = s.post(
            f"{base}/api/embed",
            json={"model": model, "input": texts},
            timeout=300,
        )
        if r.status_code == 200:
            data = r.json()
            embs = data.get("embeddings", [])
            if embs and len(embs) == len(texts):
                return embs
    except Exception:
        pass

    # Fallback: individual calls
    return [_call_ollama_embed(model, t) for t in texts]


def embed_text(text: str) -> List[float]:
    """
    Embed a single text string.
    Auto-resolves the best available model.
    """
    model = _resolve_embedding_model()
    return _call_ollama_embed(model, text)


def embed_batch(texts: List[str],
                progress_callback=None,
                batch_size: int = 16) -> List[List[float]]:
    """
    Embed a list of texts using batch API calls.

    Sends texts in groups of *batch_size* to the Ollama batch embedding
    endpoint, reducing HTTP overhead compared to one-request-per-text.
    Falls back to parallel individual calls for older Ollama versions.
    """
    model = _resolve_embedding_model()
    n = len(texts)
    results = []
    done_count = 0

    for i in range(0, n, batch_size):
        batch = texts[i:i + batch_size]
        batch_embs = _call_ollama_embed_batch(model, batch)
        results.extend(batch_embs)
        done_count += len(batch)
        if progress_callback:
            progress_callback(done_count, n)

    return results


def is_embedding_model_available() -> bool:
    """Quick check whether any usable embedding model exists."""
    try:
        model = _resolve_embedding_model()
        return model is not None
    except Exception:
        return False


def is_dedicated_embedding_model() -> bool:
    """
    Return True only if the resolved model is a real embedding model
    (contains 'embed' in its name), not a coder/LLM fallback.
    """
    try:
        model = _resolve_embedding_model()
        return model is not None and "embed" in model.lower()
    except Exception:
        return False
