from __future__ import annotations

from functools import lru_cache

from sentence_transformers import SentenceTransformer


@lru_cache(maxsize=1)
def get_sentence_model() -> SentenceTransformer:
    """Return a shared SentenceTransformer instance for all embeddings."""
    return SentenceTransformer("all-MiniLM-L6-v2")

