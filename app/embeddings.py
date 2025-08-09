from typing import List
from sentence_transformers import SentenceTransformer
from .config import settings

_model = SentenceTransformer(settings.embedding_model, device=settings.embedding_device)

def embed_texts(texts: List[str]) -> List[List[float]]:
    return _model.encode(texts, normalize_embeddings=True).tolist()
