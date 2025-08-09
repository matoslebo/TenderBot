# app/search/reranker.py
import os
from functools import lru_cache
from typing import List, Dict

from sentence_transformers import CrossEncoder  # potrebuješ sentence-transformers + torch

MODEL_NAME = os.getenv("CROSS_ENCODER_MODEL_NAME", "cross-encoder/ms-marco-MiniLM-L-6-v2")

@lru_cache(maxsize=1)
def _load_model() -> CrossEncoder:
    # prvé spustenie stiahne model (~40–90 MB); cache ho v procese
    return CrossEncoder(MODEL_NAME)

def rerank(query: str, hits: List[Dict], *, text_key: str = "snippet", top_k: int | None = None) -> List[Dict]:
    """
    Vstup: pôvodné hits zo semantického vyhľadávania (embeddingy).
    Výstup: hits zoradené podľa cross-encoder skóre (desc); doplní 'rerank_score'.
    """
    model = _load_model()
    pairs = [(query, (h.get(text_key) or h.get("title") or "")) for h in hits]
    scores = model.predict(pairs)  # numpy array (float32)
    for h, s in zip(hits, scores):
        h["rerank_score"] = float(s)
    hits_sorted = sorted(hits, key=lambda x: x["rerank_score"], reverse=True)
    return hits_sorted[:top_k] if top_k else hits_sorted
