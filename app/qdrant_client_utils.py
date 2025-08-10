# app/qdrant_client_utils.py
from __future__ import annotations

import os
from collections.abc import Iterable, Mapping
from typing import Any
from uuid import uuid4

import httpx

from .embeddings import embed_query, embed_texts

QDRANT_URL = os.getenv("QDRANT_URL", "http://ts-qdrant:6333").rstrip("/")
COLLECTION = os.getenv("QDRANT_COLLECTION", "docs")


def _http() -> httpx.Client:
    # dôležité: http2=False => žiadne HTTP/2 huncútstva cez ACA internal
    return httpx.Client(base_url=QDRANT_URL, timeout=30.0, http2=False)


def _dim() -> int:
    return len(embed_query("test"))


def ensure_collection(name: str = COLLECTION, dim: int | None = None) -> None:
    if dim is None:
        dim = _dim()
    with _http() as h:
        # zisti existujúce kolekcie
        resp = h.get("/collections")
        resp.raise_for_status()
        names = {c["name"] for c in resp.json()["result"]["collections"]}
        if name in names:
            return
        # vytvor
        payload = {"vectors": {"size": dim, "distance": "Cosine"}}
        r2 = h.put(f"/collections/{name}", json=payload)
        r2.raise_for_status()


def upsert_documents(
    texts: Iterable[str],
    metadatas: Iterable[Mapping[str, Any]] | None = None,
    collection: str = COLLECTION,
) -> None:
    texts = list(texts)
    vecs = embed_texts(texts)
    if metadatas is None:
        metadatas = [{} for _ in texts]
    else:
        metadatas = list(metadatas)

    ensure_collection(collection)

    points = []
    for text, vec, meta in zip(texts, vecs, metadatas, strict=False):
        payload = {"text": text, **dict(meta)}
        points.append({"id": uuid4().hex, "vector": vec, "payload": payload})

    with _http() as h:
        r = h.put(f"/collections/{collection}/points", json={"points": points})
        r.raise_for_status()


def search(query_vector: list[float], limit: int = 5, collection: str = COLLECTION):
    ensure_collection(collection)
    with _http() as h:
        body = {
            "vector": query_vector,
            "limit": limit,
            "with_payload": True,
            "with_vector": False,
        }
        r = h.post(f"/collections/{collection}/points/search", json=body)
        r.raise_for_status()
        return r.json()["result"]
