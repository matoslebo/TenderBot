from typing import List
import numpy as np
from sentence_transformers import SentenceTransformer
from functools import lru_cache
import os
MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "intfloat/multilingual-e5-base")
@lru_cache(maxsize=1)
def _load_model():
    return SentenceTransformer(MODEL_NAME)
def embed_documents(texts: List[str]) -> np.ndarray:
    model = _load_model()
    return model.encode([f"passage: {t}" for t in texts], normalize_embeddings=True)
def embed_query(query: str) -> np.ndarray:
    model = _load_model()
    return model.encode([f"query: {query}"], normalize_embeddings=True)[0]
