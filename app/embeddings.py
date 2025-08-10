from sentence_transformers import SentenceTransformer
from typing import List
from .config import settings

_model = SentenceTransformer(settings.embedding_model, device=settings.embedding_device)


def embed_texts(texts: list[str]) -> list[list[float]]:
    return _model.encode(texts, normalize_embeddings=True).tolist()

def embed_documents(texts: List[str]) -> List[List[float]]:
    """Lightweight wrapper so scripts.seed_sample can import it."""
    return [embed_query(t) for t in texts]