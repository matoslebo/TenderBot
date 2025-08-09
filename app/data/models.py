from pydantic import BaseModel, HttpUrl, Field
from typing import List, Optional
from datetime import datetime
class TenderDoc(BaseModel):
    id: str
    title: str
    buyer: Optional[str] = None
    country: Optional[str] = None
    region: Optional[str] = None
    cpv: Optional[List[str]] = None
    estimated_value_eur: Optional[float] = None
    deadline: Optional[datetime] = None
    language: Optional[str] = None
    url: Optional[HttpUrl] = None
    text: str = Field(..., description="Plný text/summary oznámenia")
class SearchRequest(BaseModel):
    query: str
    top_k: int = 5
class SearchHit(BaseModel):
    id: str
    score: float
    title: Optional[str] = None
    snippet: Optional[str] = None
    url: Optional[str] = None
class QARequest(BaseModel):
    question: str
    top_k: int = 4
class QAResponse(BaseModel):
    answer: str
    references: List[str]
