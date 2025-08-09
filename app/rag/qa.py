# app/rag/qa.py
from typing import List
from ..search import qdrant_client
from ..llm.embeddings import embed_query
from ..llm.providers import generate_answer
from ..search.reranker import rerank as ce_rerank   # ← PRIDANÉ
import os

SYSTEM_PROMPT = (
    "Si asistent pre verejné obstarávania. Odpovedaj stručne a iba z poskytnutého kontextu. "
    "Ak informácia nie je v kontexte, povedz 'neviem na základe kontextu'."
)

CANDIDATE_K = int(os.getenv("RERANK_CANDIDATES", "10"))  # default 10

def simple_rag(question: str, top_k: int = 4) -> dict:
    q_emb = embed_query(question)
    # 1) vyber širší set kandidátov cez vektory
    candidates = qdrant_client.search(q_emb, top_k=max(CANDIDATE_K, top_k))
    # 2) rerank cez cross-encoder ⇒ zúžime na top-K pre kontext
    hits = ce_rerank(question, candidates, text_key="snippet", top_k=top_k)

    context_blocks, refs = [], []
    for h in hits:
        if h.get("snippet"):
            context_blocks.append(h["snippet"])
        if h.get("url"):
            refs.append(h["url"])
    context = "\n\n---\n\n".join(context_blocks) if context_blocks else "Žiadny kontext."
    prompt = f"KONTEKST:\n{context}\n\nOTÁZKA: {question}\n\nODPOVEĎ:"
    answer = generate_answer(prompt, system=SYSTEM_PROMPT)
    return { "answer": answer, "references": refs }
