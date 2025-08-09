# flows/alerts.py
from __future__ import annotations
import os, json, pathlib, textwrap
from typing import Dict, Any, List, Tuple
from datetime import datetime, timezone
from dateutil import parser as date_parser

import yaml
from prefect import flow, task, get_run_logger

from app.llm.embeddings import embed_query
from app.search.qdrant_client import get_client, COLLECTION  # máme v projekte
from prefect_email import EmailServerCredentials, email_send_message

# --- Nastavenie/konštanty ---
STATE_DIR = pathlib.Path(__file__).resolve().parents[1] / "state" / "alerts"
STATE_DIR.mkdir(parents=True, exist_ok=True)

CANDIDATE_K = int(os.getenv("ALERTS_CANDIDATES", "50"))   # koľko kandidátov si vytiahneme z vektorového vyhľadávania
MIN_SCORE   = float(os.getenv("ALERTS_MIN_SCORE", "0.0"))  # minimálne semantické skóre, inak odfiltrujeme
USE_RERANK  = os.getenv("ALERTS_USE_RERANKER", "false").lower() in ("1","true","yes")

# --- Optional: cross-encoder reranker (ak si ho pridal podľa predošlého kroku) ---
def maybe_rerank(query: str, hits: List[Dict]) -> List[Dict]:
    if not USE_RERANK:
        return hits
    try:
        from app.search.reranker import rerank as ce_rerank
        return ce_rerank(query, hits, text_key="snippet", top_k=len(hits))
    except Exception:
        return hits

@task
def load_profiles(path: str = "alerts/profiles.yaml") -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def _state_path(profile_name: str) -> pathlib.Path:
    return STATE_DIR / f"{profile_name}.json"

def _load_state(profile_name: str) -> Dict[str, Any]:
    p = _state_path(profile_name)
    if p.exists():
        return json.loads(p.read_text("utf-8"))
    return {"seen_ids": [], "last_run_utc": None}

def _save_state(profile_name: str, state: Dict[str, Any]) -> None:
    _state_path(profile_name).write_text(json.dumps(state, ensure_ascii=False, indent=2), "utf-8")

def _payload_to_hit(r) -> Dict[str, Any]:
    # r = qdrant ScoredPoint; očakávame r.payload s našimi kľúčmi
    payload = r.payload or {}
    return {
        "id": payload.get("id") or str(r.id),
        "score": float(getattr(r, "score", 0.0)),
        "title": payload.get("title"),
        "url": payload.get("url"),
        "snippet": (payload.get("text") or "")[:300] + "..." if payload.get("text") else None,
        "country": payload.get("country"),
        "cpv": payload.get("cpv") or [],
        "deadline": payload.get("deadline") or payload.get("deadline_extracted"),
        "buyer": payload.get("buyer"),
    }

@task
def search_candidates(query: str, top_k: int) -> List[Dict[str, Any]]:
    from qdrant_client.http import models as qmodels
    client = get_client()
    qvec = embed_query(query)
    res = client.search(
        collection_name=COLLECTION,
        query_vector=qvec.tolist(),
        limit=top_k,
        with_payload=True,
    )
    return [_payload_to_hit(r) for r in res if float(getattr(r, "score", 0.0)) >= MIN_SCORE]

def _filter_hits(hits: List[Dict], countries: List[str] | None, cpv_prefixes: List[str] | None) -> List[Dict]:
    out = []
    countries = [c.upper() for c in (countries or [])]
    cpv_prefixes = cpv_prefixes or []
    for h in hits:
        if countries and (h.get("country") or "").upper() not in countries:
            continue
        if cpv_prefixes:
            cpvs = [str(x) for x in (h.get("cpv") or [])]
            if not any(any(c.startswith(pref) for c in cpvs) for pref in cpv_prefixes):
                continue
        out.append(h)
    return out

def _new_vs_seen(hits: List[Dict], seen_ids: List[str]) -> List[Dict]:
    seen = set(seen_ids or [])
    return [h for h in hits if str(h.get("id")) not in seen]

def _fmt_deadline(d: Any) -> str:
    if not d:
        return "—"
    try:
        dt = date_parser.parse(str(d))
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(d)

def _build_email_html(profile_name: str, query: str, items: List[Dict]) -> Tuple[str, str]:
    subject = f"TenderSense – nové tendre ({profile_name})"
    if not items:
        html = f"<p>Žiadne nové položky pre profil <b>{profile_name}</b> (dopyt: <code>{query}</code>).</p>"
        return subject, html
    rows = []
    for i, h in enumerate(items, start=1):
        rows.append(f"""
        <tr>
          <td style="padding:6px 8px; font-family:Arial; font-size:13px;">{i}</td>
          <td style="padding:6px 8px; font-family:Arial; font-size:13px;"><a href="{h.get('url')}" target="_blank">{(h.get('title') or '(bez názvu)')}</a></td>
          <td style="padding:6px 8px; font-family:Arial; font-size:13px;">{h.get('buyer') or '—'}</td>
          <td style="padding:6px 8px; font-family:Arial; font-size:13px;">{', '.join(h.get('cpv') or []) or '—'}</td>
          <td style="padding:6px 8px; font-family:Arial; font-size:13px;">{h.get('country') or '—'}</td>
          <td style="padding:6px 8px; font-family:Arial; font-size:13px;">{_fmt_deadline(h.get('deadline'))}</td>
        </tr>
        """)
    html = f"""
    <div style="font-family:Arial; font-size:14px;">
      <p><b>Profil:</b> {profile_name}</p>
      <p><b>Dopyt:</b> <code>{query}</code></p>
      <table border="1" cellspacing="0" cellpadding="0" style="border-collapse:collapse;">
        <thead>
          <tr style="background:#f5f5f5;">
            <th style="padding:6px 8px; font-family:Arial; font-size:13px;">#</th>
            <th style="padding:6px 8px; font-family:Arial; font-size:13px;">Názov</th>
            <th style="padding:6px 8px; font-family:Arial; font-size:13px;">Zadávateľ</th>
            <th style="padding:6px 8px; font-family:Arial; font-size:13px;">CPV</th>
            <th style="padding:6px 8px; font-family:Arial; font-size:13px;">Krajina</th>
            <th style="padding:6px 8px; font-family:Arial; font-size:13px;">Deadline</th>
          </tr>
        </thead>
        <tbody>
          {''.join(rows)}
        </tbody>
      </table>
      <p style="color:#666; font-size:12px; margin-top:12px;">Poslal TenderSense MVP • {datetime.now().strftime("%Y-%m-%d %H:%M")}</p>
    </div>
    """
    return subject, html

@task
def send_email(block_name: str, to: List[str], subject: str, html: str):
    creds = EmailServerCredentials.load(block_name)
    # `email_send_message` pošle text; jednoduché HTML doručíme ako "msg" (väčšina klientov zobrazí).
    email_send_message(
        email_server_credentials=creds,
        subject=subject,
        msg=html,
        email_to=to,
    )

@flow(name="tendersense-alerts")
def alerts_flow(profile: str, email_block: str = "smtp-default"):
    """
    profile – názov profilu z alerts/profiles.yaml
    email_block – názov Prefect Email blocku (SMTP kredenciály)
    """
    log = get_run_logger()
    conf = load_profiles().result()
    prof = conf["profiles"][profile]

    query = prof["query"]
    countries = prof.get("countries")
    cpv_prefixes = prof.get("cpv_prefixes")
    max_results = int(prof.get("max_results", 20))
    email_to = prof["email_to"]
    subject_override = prof.get("subject")

    state = _load_state(profile)
    seen_ids = state.get("seen_ids", [])

    # 1) kandidáti → (voliteľný) rerank → filter
    cands = search_candidates(query, top_k=max(CANDIDATE_K, max_results)).result()
    cands = maybe_rerank(query, cands)
    filt = _filter_hits(cands, countries=countries, cpv_prefixes=cpv_prefixes)

    # 2) nové vs. videné
    new_items = _new_vs_seen(filt[:max_results], seen_ids)

    # 3) e-mail
    subject, html = _build_email_html(profile, query, new_items)
    if subject_override:
        subject = subject_override
    if new_items:
        send_email(email_block, email_to, subject, html)
        log.info("E-mail odoslaný na %s (počet položiek: %d)", email_to, len(new_items))
    else:
        log.info("Žiadne nové položky – e-mail sa neposiela.")

    # 4) ulož stav
    state["seen_ids"] = list(set(seen_ids + [str(x["id"]) for x in new_items]))
    state["last_run_utc"] = datetime.now(timezone.utc).isoformat()
    _save_state(profile, state)
    return {"profile": profile, "new": len(new_items), "checked": len(filt)}
    
if __name__ == "__main__":
    # manuálny test: pošli raz
    alerts_flow(profile="it_sk_cz_daily", email_block="smtp-default")
