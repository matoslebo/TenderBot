import os

from pydantic import BaseModel


class Settings(BaseModel):
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    embedding_device: str = os.getenv("EMBEDDING_DEVICE", "cpu")
    qdrant_host: str = os.getenv("QDRANT_HOST", "localhost")
    qdrant_port: int = int(os.getenv("QDRANT_PORT", "6333"))
    qdrant_collection: str = os.getenv("QDRANT_COLLECTION", "tenders")


settings = Settings()
