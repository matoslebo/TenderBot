# app/qdrant_client_utils.py
from __future__ import annotations
import os
from uuid import uuid4
from typing import Iterable, Mapping, Any

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

from .embeddings import embed_texts, embed_query

QDRANT_URL = os.getenv("QDRANT_URL", "http://ts-qdrant:6333")
COLLECTION = os.getenv("QDRANT_COLLECTION", "docs")

_client: QdrantClient | None = None


def client() -> QdrantClient:
    global _client
    if _client is None:
        # Ak je QDRANT_URL plné (http/https), používaj url=...
        _client = QdrantClient(url=QDRANT_URL, timeout=30.0)
    return _client


def _dim() -> int:
    # zisti rozmer vektora jedným rýchlym embed-om
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

    points = []
    for text, vec, meta in zip(texts, vecs, metadatas):
        payload = {"text": text, **dict(meta)}
        points.append(PointStruct(id=uuid4().hex, vector=vec, payload=payload))

    c.upsert(collection_name=collection, points=points)


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
