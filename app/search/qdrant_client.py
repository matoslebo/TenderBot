# app/search/qdrant_client.py
import os
import uuid
from functools import lru_cache
from typing import List, Dict, Any

import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
COLLECTION = os.getenv("QDRANT_COLLECTION", "tendersense_mvp")
VECTOR_SIZE = int(os.getenv("EMBEDDING_DIM", "768"))

@lru_cache(maxsize=1)
def get_client() -> QdrantClient:
    return QdrantClient(url=QDRANT_URL)

def ensure_collection(vector_size: int | None = None):
    """
    Ensure Qdrant collection exists and its vector size matches.
    - If `vector_size` is given (e.g. from embeddings.shape[1]), use it.
    - Otherwise fall back to VECTOR_SIZE env (default 768).
    If mismatch is detected, the collection is recreated.
    """
    client = get_client()
    size = int(vector_size or VECTOR_SIZE)

    try:
        info = client.get_collection(COLLECTION)
        # get existing size from info (works across qdrant-client versions)
        try:
            existing = info.config.params.vectors.size
        except Exception:
            existing = info.dict()["result"]["config"]["params"]["vectors"]["size"]
        if int(existing) != size:
            client.recreate_collection(
                collection_name=COLLECTION,
                vectors_config=qmodels.VectorParams(size=size, distance=qmodels.Distance.COSINE),
            )
    except Exception:
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config=qmodels.VectorParams(size=size, distance=qmodels.Distance.COSINE),
        )

def _as_list(vec):
    if isinstance(vec, np.ndarray):
        return vec.astype(float).tolist()
    # iterovateľné -> list floatov
    return [float(x) for x in vec]

def _stable_uuid(value: str) -> str:
    # deterministický UUID z tvojho ID/URL (rovnaký vstup => rovnaký UUID)
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"tendersense::{value}"))

def upsert_documents(embeddings: List, payloads: List[Dict[str, Any]]):
    """
    embeddings – list vektorov (dĺžka = VECTOR_SIZE)
    payloads   – list dictov s kľúčmi (id/title/url/text/...)
    """
    ensure_collection()
    client = get_client()

    points: List[qmodels.PointStruct] = []
    for i, (vec, payload) in enumerate(zip(embeddings, payloads)):
        # 1) Point ID musí byť int alebo UUID → urobíme stabilný UUID z business ID (alebo URL)
        raw_id = str(payload.get("id") or payload.get("url") or i)
        point_id = _stable_uuid(raw_id)

        # 2) vektor ako list floatov
        vector = _as_list(vec)

        # 3) skladáme point; payload ponechávame vrátane pôvodného "id"
        points.append(
            qmodels.PointStruct(
                id=point_id,
                vector=vector,
                payload=payload,
            )
        )

    client.upsert(collection_name=COLLECTION, points=points, wait=True)

def search(query_vector, top_k: int = 5) -> List[Dict[str, Any]]:
    ensure_collection()
    client = get_client()
    qv = _as_list(query_vector)
    res = client.search(
        collection_name=COLLECTION,
        query_vector=qv,
        limit=top_k,
        with_payload=True,
    )
    hits = []
    for r in res:
        p = r.payload or {}
        hits.append({
            # pre UI/reporty použijeme business ID z payloadu; ak by chýbalo, vezmeme Qdrant id
            "id": p.get("id") or str(r.id),
            "score": float(getattr(r, "score", 0.0)),
            "title": p.get("title"),
            "snippet": (p.get("text") or p.get("text_enriched") or "")[:300] or None,
            "url": p.get("url"),
        })
    return hits
