# flows/extract_gold.py
import os, json, glob, pathlib
from typing import List, Dict, Any

from app.llm.structured_extract import extract_structured

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "sample_data" / "notices"
OUT = ROOT / "sample_data" / "gold"
OUT.mkdir(parents=True, exist_ok=True)

def run(batch_limit: int = 100, lang: str = "sk"):
    fns = list(glob.glob(str(SRC / "*.json")))[:batch_limit]
    for fn in fns:
        with open(fn, "r", encoding="utf-8") as f:
            d = json.load(f)
        text = d.get("text") or ""
        obj, raw = extract_structured(text=text, lang=lang, max_retries=2, strict_json=True)
        extraction_json_ready = obj.model_dump(mode="json") 
        out = {
            "id": d.get("id"),
            "title": d.get("title"),
            "url": d.get("url"),
            "extraction": extraction_json_ready,
        }
        ofn = OUT / f"{d.get('id')}.json"
        with open(ofn, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print("extracted:", ofn.name)

if __name__ == "__main__":
    run()
