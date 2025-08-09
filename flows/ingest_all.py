# flows/ingest_all.py
from typing import List, Dict, Any
import os

from app.llm.embeddings import embed_documents
from app.search.qdrant_client import upsert_documents
from flows.ingest_ted import ingest_ted_mvp
from flows.ingest_nen import fetch_nen_recent
from validation.gx_validate import run_expectations
from app.llm.structured_extract import extract_structured  # ← LLM JSON extrakcia

# ──────────────────────────────────────────────────────────────────────────────
# Pomocné: jednoduchý výber jazyka pre prompt (SK/CZ → sk/cs, inak en)
def _pick_lang(doc) -> str:
    if getattr(doc, "language", None):
        return (doc.language or "").strip().lower()[:2] or "en"
    country = (getattr(doc, "country", None) or "").upper()
    if country == "CZ":
        return "cs"
    if country == "SK":
        return "sk"
    return "en"
# ──────────────────────────────────────────────────────────────────────────────

def ingest_all(
    limit_ted: int = 50,
    limit_nen: int = 30,
    dq_fail_on_error: bool = True,
    enrich_with_llm: bool = True
):
    # 1) Zdroje
    ted_docs = ingest_ted_mvp(limit=limit_ted)
    nen_docs = fetch_nen_recent(limit=limit_nen)
    docs = ted_docs + nen_docs

    # 2) LLM extrakcia → doplnenie polí (deadline/cpv/requirements) + enriched text
    payloads: List[Dict[str, Any]] = []
    enable_extract = enrich_with_llm and os.getenv("ENABLE_STRUCTURED_EXTRACT", "true").lower() in ("1", "true", "yes")

    for d in docs:
        rec: Dict[str, Any] = d.model_dump()
        if enable_extract:
            lang = _pick_lang(d)
            obj, _raw = extract_structured(rec.get("text") or rec.get("title") or "", lang=lang)

            # ulož extrahované polia do nových kľúčov
            rec["deadline_extracted"] = obj.deadline.isoformat() if obj.deadline else None
            rec["cpv_extracted"] = obj.cpv
            rec["requirements_extracted"] = obj.requirements

            # backfill do core polí, ak chýbali v zdroji
            if not rec.get("deadline") and obj.deadline:
                rec["deadline"] = obj.deadline.isoformat()
            if (not rec.get("cpv")) and obj.cpv:
                rec["cpv"] = obj.cpv

            # enriched text (na embeddingy), snippet ostáva z 'text'
            base_text = rec.get("text") or rec.get("title") or ""
            if obj.requirements:
                rec["text_enriched"] = base_text + "\n\nPožiadavky:\n- " + "\n- ".join(obj.requirements)
            else:
                rec["text_enriched"] = base_text
        else:
            rec["text_enriched"] = rec.get("text") or rec.get("title") or ""

        payloads.append(rec)

    # 3) Data Quality (GX) – schema, non-null, ranges, freshness
    dq = run_expectations(payloads, freshness_days=1)
    if not dq["success"]:
        print("Data quality FAILED:", dq["statistics"])
        if dq_fail_on_error:
            return {"indexed": 0, "dq_passed": False, "dq_stats": dq["statistics"]}

    # 4) Indexácia do vektorovej DB
    #    Embedding berieme z 'text_enriched' (ak nie je, padáme na 'text' → 'title')
    texts = [p.get("text_enriched") or p.get("text") or (p.get("title") or "") for p in payloads]
    embs = embed_documents(texts)
    upsert_documents(embs, payloads)

    return {"indexed": len(payloads), "dq_passed": dq["success"], "dq_stats": dq["statistics"]}

if __name__ == "__main__":
    out = ingest_all()
    print("Indexed", out)
