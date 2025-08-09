from typing import List, Dict
from qdrant_client import QdrantClient
from qdrant_client.http import models as qm
from .config import settings

client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)

def ensure_collection(dim: int = 384):
    client.recreate_collection(
        collection_name=settings.qdrant_collection,
        vectors_config=qm.VectorParams(size=dim, distance=qm.Distance.COSINE),
    )

def upsert_points(payloads: List[Dict], vectors: List[List[float]]):
    points = [qm.PointStruct(id=i, vector=vectors[i], payload=payloads[i]) for i in range(len(payloads))]
    client.upsert(collection_name=settings.qdrant_collection, points=points)

def search(query_vector: List[float], limit: int = 5) -> List[Dict]:
    res = client.search(
        collection_name=settings.qdrant_collection,
        query_vector=query_vector,
        limit=limit,
        with_payload=True,
    )
    return [
        {"score": r.score, **(r.payload or {})}
        for r in res
    ]
