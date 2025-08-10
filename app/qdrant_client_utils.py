# app/qdrant_client_utils.py
from __future__ import annotations

import os
from uuid import uuid4
from typing import Iterable, Mapping, Any
from functools import lru_cache

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

from .embeddings import embed_texts, embed_query

DEFAULT_QDRANT_URL = "http://ts-qdrant:6333"
COLLECTION = os.getenv("QDRANT_COLLECTION", "docs")


def _resolve_qdrant_url() -> str:
    """
    Vráti použiteľnú URL na Qdrant.
    Podporuje:
      - plnú URL (http/https)
      - len hostname[:port]
      - prázdnu alebo len schému -> fallback na DEFAULT_QDRANT_URL
    """
    raw = (os.getenv("QDRANT_URL") or "").strip()

    if not raw or raw in ("http://", "https://"):
        return DEFAULT_QDRANT_URL

    if raw.startswith(("http://", "https://")):
        return raw

    # Bez schémy: doplň http:// a port 6333, ak chýba
    if ":" in raw:
        return f"http://{raw}"
    return f"http://{raw}:6333"


@lru_cache(maxsize=1)
def client() -> QdrantClient:
    """
    Lazy singleton Qdrant klient (bez global premenných).
    """
    return QdrantClient(url=_resolve_qdrant_url(), prefer_grpc=False, timeout=30.0)


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

    points: list[PointStruct] = []
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
