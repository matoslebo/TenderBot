# Vytvorí 2 ukážkové tendre a naindexuje ich do Qdrantu
import os, json, uuid
from datetime import datetime, timedelta
from app.llm.embeddings import embed_documents
from app.search.qdrant_client import upsert_documents, ensure_collection
base_dir = os.path.dirname(os.path.dirname(__file__))
sample_dir = os.path.join(base_dir, "sample_data", "notices")
os.makedirs(sample_dir, exist_ok=True)
docs = [
    {
        "id": str(uuid.uuid4()),
        "title": "Dodávka a údržba informačného systému pre mestský úrad",
        "buyer": "Mesto Bratislava",
        "country": "SK",
        "region": "Bratislavský kraj",
        "cpv": ["72222300", "48000000"],
        "estimated_value_eur": 240000.0,
        "deadline": (datetime.utcnow() + timedelta(days=18)).isoformat() + "Z",
        "language": "sk",
        "url": "https://example.com/tender/1",
        "text": "Predmetom zákazky je dodávka, implementácia a údržba informačného systému pre mestský úrad, vrátane školenia používateľov a podpory. Požaduje sa skúsenosť s projektmi v oblasti samosprávy, SLA 8/5, reakčný čas do 4 hodín, a referencie aspoň 2 úspešne nasadené projekty.",
    },
    {
        "id": str(uuid.uuid4()),
        "title": "Kybernetický audit a penetračné testy pre nemocnicu",
        "buyer": "Fakultná nemocnica Olomouc",
        "country": "CZ",
        "region": "Olomoucký kraj",
        "cpv": ["72212730", "72222300"],
        "estimated_value_eur": 85000.0,
        "deadline": (datetime.utcnow() + timedelta(days=12)).isoformat() + "Z",
        "language": "cs",
        "url": "https://example.com/tender/2",
        "text": "Předmětem zakázky je provedení kybernetického auditu dle NIS2 a následné penetrační testy. Zadavatel vyžaduje ISO 27001, doložení kvalifikace auditorů a report do 30 dnů od podpisu smlouvy.",
    },
]
for i, d in enumerate(docs, start=1):
    fn = os.path.join(sample_dir, f"sample_{i}.json")
    with open(fn, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
texts = [d["text"] for d in docs]
from app.llm.embeddings import embed_documents
embs = embed_documents(texts)
ensure_collection(embs.shape[1])
upsert_documents(embs, docs)
print("✅ Vytvorené a naindexované ukážkové tendre:", [d["title"] for d in docs])
