"""
Embedding service — calls Ollama embedding API.
Auto-detects available model: prefers nomic-embed-text,
falls back to deepseek-coder (which also supports embeddings).
"""

import requests
from typing import List, Optional
import config

# ── Module-level state (resolved once, reused) ─────────────────
_resolved_model: Optional[str] = None


def _resolve_embedding_model() -> str:
    """Pick the best available embedding model from Ollama."""
    global _resolved_model
    if _resolved_model:
        return _resolved_model

    try:
        r = requests.get(f"{config.OLLAMA_BASE_URL}/api/tags", timeout=5)
        if r.status_code == 200:
            models = [m["name"] for m in r.json().get("models", [])]

            # Prefer nomic-embed-text
            for m in models:
                if "nomic-embed-text" in m:
                    _resolved_model = m
                    print(f"[Embeddings] Using model: {m}")
                    return m

            # Fallback: any model with "embed" in name
            for m in models:
                if "embed" in m.lower():
                    _resolved_model = m
                    print(f"[Embeddings] Using model: {m}")
                    return m

            # Last resort: use the LLM model itself (deepseek-coder)
            for m in models:
                if "deepseek" in m.lower() or "coder" in m.lower():
                    _resolved_model = m
                    print(f"[Embeddings] Fallback to LLM model for embeddings: {m}")
                    return m

            # Use whatever is first
            if models:
                _resolved_model = models[0]
                print(f"[Embeddings] Using first available model: {models[0]}")
                return models[0]
    except Exception:
        pass

    # Default from config
    _resolved_model = config.EMBEDDING_MODEL
    return _resolved_model


def _call_ollama_embed(model: str, text: str) -> List[float]:
    """
    Try both Ollama embedding endpoints:
      - /api/embeddings  (older Ollama)
      - /api/embed       (newer Ollama ≥ 0.4)
    """
    base = config.OLLAMA_BASE_URL

    # Try /api/embeddings first (uses "prompt" key)
    try:
        r = requests.post(
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
        r = requests.post(
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


def embed_text(text: str) -> List[float]:
    """
    Embed a single text string.
    Auto-resolves the best available model.
    """
    model = _resolve_embedding_model()
    return _call_ollama_embed(model, text)


def embed_batch(texts: List[str],
                progress_callback=None) -> List[List[float]]:
    """
    Embed a list of texts using parallel requests to keep the GPU busy.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    model = _resolve_embedding_model()
    n = len(texts)
    results = [None] * n     # pre-allocate to preserve order
    done_count = [0]          # mutable counter for callback

    def _embed_one(idx_text):
        idx, text = idx_text
        return idx, _call_ollama_embed(model, text)

    # 4 parallel workers — matches OLLAMA_NUM_PARALLEL default
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_embed_one, (i, t)): i
                   for i, t in enumerate(texts)}

        for future in as_completed(futures):
            idx, emb = future.result()
            results[idx] = emb
            done_count[0] += 1
            if progress_callback:
                progress_callback(done_count[0], n)

    return results


def is_embedding_model_available() -> bool:
    """Quick check whether any usable embedding model exists."""
    try:
        model = _resolve_embedding_model()
        return model is not None
    except Exception:
        return False
