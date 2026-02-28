"""
ChromaDB vector store wrapper — persistent, zero-config.
Stores code chunks with embeddings and metadata for filtered
similarity search.
"""

import os
import chromadb
from typing import List, Dict, Optional
import config
from core.chunker import CodeChunk


_client: Optional[chromadb.ClientAPI] = None
_collection: Optional[chromadb.Collection] = None


def _get_client(persist_dir: str = None):
    global _client
    if _client is None:
        path = persist_dir or config.CHROMA_PERSIST_DIR
        os.makedirs(path, exist_ok=True)
        _client = chromadb.PersistentClient(path=path)
    return _client


def get_collection(name: str = None):
    global _collection
    if _collection is None:
        cname = name or config.CHROMA_COLLECTION_NAME
        _collection = _get_client().get_or_create_collection(
            name=cname,
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def reset_collection(name: str = None):
    """Delete and recreate the collection (for re-indexing)."""
    global _collection
    client = _get_client()
    cname = name or config.CHROMA_COLLECTION_NAME
    try:
        client.delete_collection(cname)
    except Exception:
        pass
    _collection = client.get_or_create_collection(
        name=cname,
        metadata={"hnsw:space": "cosine"},
    )
    return _collection


def upsert_chunks(chunks: List[CodeChunk],
                  embeddings: List[List[float]],
                  batch_size: int = 5000):
    """Insert or update chunks with their embeddings (batched)."""
    coll = get_collection()
    for i in range(0, len(chunks), batch_size):
        batch_c = chunks[i:i + batch_size]
        batch_e = embeddings[i:i + batch_size]
        coll.upsert(
            ids=[c.id for c in batch_c],
            embeddings=batch_e,
            documents=[c.content for c in batch_c],
            metadatas=[c.metadata() for c in batch_c],
        )


def search(query_embedding: List[float],
           top_k: int = None,
           where: Optional[Dict] = None,
           where_document: Optional[Dict] = None) -> Dict:
    """
    Similarity search.

    Returns a dict with keys: 'ids', 'documents', 'metadatas', 'distances'.
    Each value is a list-of-lists (batch dim=1).
    """
    coll = get_collection()
    k = min(top_k or config.RAG_TOP_K, coll.count() or 1)
    if k < 1:
        return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}
    kwargs = {
        "query_embeddings": [query_embedding],
        "n_results": k,
    }
    if where:
        kwargs["where"] = where
    if where_document:
        kwargs["where_document"] = where_document

    return coll.query(**kwargs)


def count() -> int:
    return get_collection().count()


def get_all_metadata() -> List[Dict]:
    """Return metadata for every chunk in the collection."""
    coll = get_collection()
    n = coll.count()
    if n == 0:
        return []
    result = coll.get(include=["metadatas"])
    return result.get("metadatas", [])
