"""Create a tiny sample CSV and trigger ingest via API."""

import csv
import os
from datetime import date, timedelta

from app.embeddings import embed_documents
from app.qdrant_client_utils import ensure_collection, upsert_documents


def main():

    DATA = [
        {
            "id": "T-001",
            "title": "Software development services for municipal portal",
            "description": "Development and maintenance of a public portal including CMS and integrations.",
            "url": "https://example.org/tenders/T-001",
            "deadline": (date.today() + timedelta(days=21)).isoformat(),
        },
        {
            "id": "T-002",
            "title": "Network equipment procurement",
            "description": "Switches and routers, delivery and installation, support for 24 months.",
            "url": "https://example.org/tenders/T-002",
            "deadline": (date.today() + timedelta(days=30)).isoformat(),
        },
    ]

    ROOT = os.path.dirname(os.path.dirname(__file__))
    CSV_PATH = os.path.join(ROOT, "sample_data", "notices.csv")
    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["id", "title", "description", "url", "deadline"])
        w.writeheader()
        for row in DATA:
            w.writerow(row)

    print(f"Wrote {CSV_PATH}")

    # Optionally call API /ingest
    try:
        import requests

        r = requests.post("http://localhost:8000/ingest", timeout=30)
        print("Ingest response:", r.json())
    except Exception as e:
        print("Note: could not call API /ingest (is it running?)", e)

    texts = [
        "Cybersecurity audit ISO 27001 for municipality",
        "Cloud migration tender for data platform",
    ]
    embs = embed_documents(texts)
    ensure_collection(embs.shape[1])
    payloads = [{"id": f"seed-{i}", "title": t, "text": t} for i, t in enumerate(texts)]
    upsert_documents(embs, payloads)
    print("Seed OK")


if __name__ == "__main__":
    main()
