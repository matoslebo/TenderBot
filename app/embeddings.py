from __future__ import annotations
from functools import lru_cache

from sentence_transformers import SentenceTransformer

from .config import settings


@lru_cache(maxsize=1)
def _get_model() -> SentenceTransformer:
    model_name = getattr(settings, "embedding_model", "sentence-transformers/all-MiniLM-L6-v2")
    device = getattr(settings, "embedding_device", "cpu")
    return SentenceTransformer(model_name, device=device)


def embed_query(text: str) -> list[float]:
    model = _get_model()
    vec = model.encode([text], normalize_embeddings=True)[0]
    return vec.tolist()


def embed_documents(texts: list[str]) -> list[list[float]]:
    model = _get_model()
    vecs = model.encode(texts, normalize_embeddings=True)
    return [v.tolist() for v in vecs]


# ---- Aliases to keep backward compatibility ----
def embed_text(text: str) -> list[float]:
    """Single text alias for embed_query."""
    return embed_query(text)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Batch alias for embed_documents (expected by app.main import)."""
    return embed_documents(texts)

__all__ = ["embed_texts", "embed_query", "embed_documents"]
