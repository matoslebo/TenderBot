import os
from fastapi import FastAPI, Query, Header, HTTPException
from pydantic import BaseModel

from .embeddings import embed_texts
from .qdrant_client_utils import ensure_collection, search, upsert_points

app = FastAPI(title="TenderBot API", version="0.1.0")

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN")

class QARequest(BaseModel):
    question: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ingest")
def ingest():
    """Load sample_data/notices.csv and index to Qdrant."""
    import csv
    import os

    ensure_collection()
    csv_path = os.path.join(os.path.dirname(__file__), "..", "sample_data", "notices.csv")
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append(row)
    texts = [f"{r['title']}\n{r['description']}" for r in rows]
    vectors = embed_texts(texts)
    payloads = [
        {
            "id": r["id"],
            "title": r["title"],
            "description": r["description"],
            "url": r["url"],
            "deadline": r["deadline"],
        }
        for r in rows
    ]
    upsert_points(payloads, vectors)
    return {"ingested": len(rows)}


@app.get("/search")
def search_route(q: str = Query(..., min_length=2), k: int = 5):
    vec = embed_texts([q])[0]
    hits = search(vec, limit=k)
    return {"query": q, "results": hits}


@app.post("/qa")
def qa(req: QARequest):
    # Simple extractive pseudo-QA: find top doc and return its description + naive snippet
    vec = embed_texts([req.question])[0]
    hits = search(vec, limit=1)
    if not hits:
        return {"answer": "No relevant tenders found."}
    doc = hits[0]
    answer = f"Likely relevant: {doc.get('title')} (deadline: {doc.get('deadline')})\n{doc.get('description')}\nURL: {doc.get('url')}"
    return {"answer": answer, "evidence": doc}


ADMIN_TOKEN = os.getenv("ADMIN_TOKEN")

def require_admin(x_admin_token: str | None = Header(default=None)):
    if not ADMIN_TOKEN:
        raise HTTPException(status_code=500, detail="ADMIN_TOKEN not configured")
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/admin/seed")
def admin_seed(x_admin_token: str | None = Header(default=None)):
    require_admin(x_admin_token)
    from scripts.seed_sample import main as seed_main
    seed_main()
    return {"status": "seeded"}

@app.post("/admin/ingest")
def admin_ingest(x_admin_token: str | None = Header(default=None)):
    require_admin(x_admin_token)
    from flows.ingest_all import ingest_all
    out = ingest_all(dq_fail_on_error=False)
    return {"status": "ingested", "result": out}