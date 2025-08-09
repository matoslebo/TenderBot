"""Create a tiny sample CSV and trigger ingest via API."""

import csv
import os
from datetime import date, timedelta

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
