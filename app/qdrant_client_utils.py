# app/qdrant_client_utils.py
from __future__ import annotations
import os
from uuid import uuid4
from typing import Iterable, Mapping, Any
from functools import lru_cache

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

from .embeddings import embed_texts, embed_query

QDRANT_URL = os.getenv("QDRANT_URL", "http://ts-qdrant:6333")
COLLECTION = os.getenv("QDRANT_COLLECTION", "docs")

@lru_cache(maxsize=1)
def client() -> QdrantClient:
    return QdrantClient(url=QDRANT_URL, timeout=30.0)

def _dim() -> int:
    return len(embed_query("test"))

def ensure_collection(name: str = COLLECTION) -> None:
    c = client()
    collections = {col.name for col in c.get_collections().collections}
    if name not in collections:
        c.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=_dim(), distance=Distance.COSINE),
        )

def upsert_documents(
    texts: Iterable[str],
    metadatas: Iterable[Mapping[str, Any]] | None = None,
    collection: str = COLLECTION,
) -> None:
    c = client()
    ensure_collection(collection)
    texts = list(texts)
    vecs = embed_texts(texts)
    if metadatas is None:
        metadatas = [{} for _ in texts]
    else:
        metadatas = list(metadatas)
    points = [
        PointStruct(id=uuid4().hex, vector=vec, payload={"text": text, **dict(meta)})
        for text, vec, meta in zip(texts, vecs, metadatas)
    ]
    c.upsert(collection_name=collection, points=points)

def upsert_points(
    points: Iterable[PointStruct] | Iterable[Mapping[str, Any]],
    collection: str = COLLECTION,
) -> None:
    """Spätnokompatibilné s pôvodnými testami: prijme PointStruct alebo dict."""
    c = client()
    ensure_collection(collection)
    norm: list[PointStruct] = []
    for p in points:
        if isinstance(p, PointStruct):
            norm.append(p)
            continue
        pid = p.get("id", uuid4().hex)
        vec = p.get("vector") or p.get("embedding")
        if vec is None:
            raise ValueError("point needs 'vector' (or 'embedding').")
        payload = p.get("payload")
        if payload is None:
            payload = {k: v for k, v in p.items() if k not in ("id", "vector", "embedding")}
        norm.append(PointStruct(id=pid, vector=vec, payload=payload))
    c.upsert(collection_name=collection, points=norm)

def search(query_vector: list[float], limit: int = 5, collection: str = COLLECTION):
    c = client()
    ensure_collection(collection)
    return c.search(
        collection_name=collection,
        query_vector=query_vector,
        limit=limit,
        with_payload=True,
        with_vectors=False,
    )
