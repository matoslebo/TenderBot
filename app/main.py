# app/main.py

from fastapi import FastAPI
from .data.models import SearchRequest, SearchHit, QARequest, QAResponse
from .llm.embeddings import embed_query
from .search.qdrant_client import search as q_search
from .search.reranker import rerank as ce_rerank     # ← PRIDANÉ
from .rag.qa import simple_rag

import os

app = FastAPI(title="TenderSense MVP")
CANDIDATE_K = int(os.getenv("RERANK_CANDIDATES", "10"))  # koľko kandidátov dáme cross-encoderu

@app.get("/")
def health():
    return {"status": "ok"}

@app.post("/search", response_model=list[SearchHit])
def semantic_search(req: SearchRequest):
    q = embed_query(req.query)
    # 1) semantické kandidáty z Qdrant (embeddingy)
    candidates = q_search(q, top_k=max(CANDIDATE_K, req.top_k))
    # 2) reranking cez cross-encoder (párové skórovanie query × text)
    ranked = ce_rerank(req.query, candidates, text_key="snippet", top_k=req.top_k)
    # 3) vrátime top-K; do 'score' dáme rerank skóre (lepšie reflektuje finálne poradie)
    return [SearchHit(
        id=h["id"],
        score=h.get("rerank_score", h["score"]),
        title=h.get("title"),
        snippet=h.get("snippet"),
        url=h.get("url"),
    ) for h in ranked]

@app.post("/qa", response_model=QAResponse)
def rag_qa(req: QARequest):
    res = simple_rag(req.question, top_k=req.top_k)
    return QAResponse(**res)


