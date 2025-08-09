# flows/ingest_ted.py
import os
import re
import time
import logging
from typing import Any, Dict, List, Optional, Tuple, Union

import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

# Upraviť podľa tvojho projektu:
try:
    from app.models import TenderDoc  # dataclass: id, title, buyer, cpv, deadline, url, text
except Exception:
    # Fallback jednoduchý dataclass, ak by import zlyhal pri skúšaní mimo app balíka.
    from dataclasses import dataclass
    @dataclass
    class TenderDoc:
        id: str
        title: Optional[str] = None
        buyer: Optional[str] = None
        cpv: Optional[List[str]] = None
        deadline: Optional[str] = None  # ISO8601 alebo raw string
        url: Optional[str] = None
        text: Optional[str] = None

TED_SEARCH_URL = os.getenv("TED_SEARCH_URL", "https://api.ted.europa.eu/v3/notices/search")
TED_LANG = os.getenv("TED_LANG", "en")
TED_SCOPE = os.getenv("TED_SCOPE", "ACTIVE")  # ACTIVE | LATEST | ALL
TED_PAGE_LIMIT = min(int(os.getenv("TED_PAGE_LIMIT", "50")), 250)  # max 250 podľa API
TED_TIMEOUT = float(os.getenv("TED_TIMEOUT", "30"))

# -- Pomocné funkcie ---------------------------------------------------------

def _ted_detail_and_html_urls(publication_number: str, lang: str = TED_LANG) -> Tuple[str, str]:
    """
    Vráti (detail_url, html_download_url) pre dané publik. číslo.
    Formát URL je oficiálne zdokumentovaný.
    """
    detail = f"https://ted.europa.eu/{lang}/notice/-/detail/{publication_number}"
    html_dl = f"https://ted.europa.eu/{lang}/notice/{publication_number}/html"
    return detail, html_dl

def _normalize_cpv_field(cpv_raw: Union[None, str, Dict[str, Any], List[Any]]) -> Optional[List[str]]:
    """
    classification-cpv môže byť string, dict s kľúčom 'code', alebo pole takýchto položiek.
    Normalizujeme na list kódov (stringov).
    """
    if cpv_raw is None:
        return None
    if isinstance(cpv_raw, str):
        return [cpv_raw]
    if isinstance(cpv_raw, dict):
        return [cpv_raw.get("code")] if "code" in cpv_raw else [str(cpv_raw)]
    if isinstance(cpv_raw, list):
        out = []
        for item in cpv_raw:
            if isinstance(item, dict) and "code" in item:
                out.append(item["code"])
            elif isinstance(item, str):
                out.append(item)
            else:
                out.append(str(item))
        return out or None
    return [str(cpv_raw)]

def _extract_text_snippet_from_html(html: str, max_chars: int = 6000) -> str:
    """
    Vytiahne plain-text z HTML pre účely indexácie (MVP). 
    """
    soup = BeautifulSoup(html, "html.parser")
    for sel in ["header", "nav", "script", "style", "footer"]:
        for x in soup.select(sel):
            x.extract()
    text = " ".join(soup.stripped_strings)
    # Spracovanie whitespace:
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]

_DEADLINE_LABELS = [
    # Anglické labely, ktoré sa bežne vyskytujú v zobrazení:
    r"Deadline for submission",  # eForms wording
    r"Time limit for receipt of tenders",  # staršie formulácie
    r"Time limit for receipt of tenders or requests to participate",
    r"Deadline for receipt of tenders",  # niekedy takto
]

def _extract_deadline_from_html(html: str) -> Optional[str]:
    """
    Skúsi nájsť deadline v EN HTML. Je to heuristické (MVP).
    Vráti ISO8601 ak sa dá, inak raw reťazec.
    """
    soup = BeautifulSoup(html, "html.parser")
    # 1) Skús explicitné <time> tagy
    for t in soup.find_all("time"):
        # text príbuzný 'deadline' v okolí:
        neighbor = " ".join(t.find_parent().get_text(" ", strip=True).split())
        if re.search(r"deadline|time limit", neighbor, flags=re.I):
            val = t.get("datetime") or t.get_text(strip=True)
            parsed = _try_parse_datetime(val)
            return parsed or val

    # 2) Hľadaj labely a najbližšiu hodnotu
    for pattern in _DEADLINE_LABELS:
        lab = soup.find(string=re.compile(pattern, flags=re.I))
        if lab:
            # Hodnota býva v nasledujúcom elemente alebo súrodeneckom bloku
            # Ideme cez pár next_ prvkov
            cur = lab.parent if hasattr(lab, "parent") else None
            for _ in range(6):
                if not cur:
                    break
                # Kandidát na hodnotu:
                val_tag = cur.find_next(["time", "span", "div", "p"])
                if val_tag:
                    raw = val_tag.get("datetime") or val_tag.get_text(strip=True)
                    parsed = _try_parse_datetime(raw)
                    return parsed or raw
                cur = cur.next_sibling
    return None

def _try_parse_datetime(val: str) -> Optional[str]:
    try:
        dt = date_parser.parse(val, dayfirst=True)
        return dt.isoformat()
    except Exception:
        # Skús vyčistiť formáty typu 14.3.2019 16:00 apod.
        m = re.search(r"(\d{1,2}\.\d{1,2}\.\d{4})(?:\s+(\d{1,2}:\d{2}))?", val)
        if m:
            try:
                dt = date_parser.parse(" ".join(filter(None, m.groups())), dayfirst=True)
                return dt.isoformat()
            except Exception:
                pass
    return None

# -- Hlavné volanie na TED Search API ---------------------------------------

def fetch_ted_notices(
    query: str,
    limit: int = TED_PAGE_LIMIT,
    page: int = 1,
    scope: str = TED_SCOPE,
    include_deadline_from_html: bool = True,
) -> List[TenderDoc]:
    """
    Zavolá TED Search API s expert query a vráti list TenderDoc.
    Pozn.: deadline sa najprv skúsime získať z API (ak je pole vrátené), inak heuristicky z HTML.
    """
    # Polia, ktoré určite chceme mať v odpovedi
    fields = [
        "publication-number",
        "notice-title",
        "buyer-name",
        "classification-cpv",
        # "deadline-???"  # v eForms existujú deadline polia, ale nemajú jednotný alias pre všetky typy; necháme fallback.
    ]

    body = {
        "query": query,
        "fields": fields,
        "page": page,
        "limit": min(limit, 250),
        "scope": scope,
        "checkQuerySyntax": False,
        "paginationMode": "PAGE_NUMBER",  # v MVP neriešime ITERATION token
    }

    resp = requests.post(TED_SEARCH_URL, json=body, timeout=TED_TIMEOUT)
    resp.raise_for_status()
    payload = resp.json()

    results = payload.get("results", [])  # podľa dokumentácie: total + results + (links)
    docs: List[TenderDoc] = []

    for item in results:
        pubnum = item.get("publication-number")
        if not pubnum:
            continue

        title = item.get("notice-title")
        buyer = item.get("buyer-name")
        cpv = _normalize_cpv_field(item.get("classification-cpv"))

        detail_url, html_url = _ted_detail_and_html_urls(pubnum, TED_LANG)

        # Ak by API vracalo deadline pole vrátené v 'item', použi ho:
        deadline_val = None
        for k in item.keys():
            if "deadline" in k.lower() or "time-limit" in k.lower():
                v = item.get(k)
                if isinstance(v, str):
                    deadline_val = _try_parse_datetime(v) or v
                break

        text_val = None
        if include_deadline_from_html or deadline_val is None:
            # Pre MVP stiahneme HTML download a vyextrahujeme text + deadline (fallback)
            try:
                hr = requests.get(html_url, timeout=TED_TIMEOUT)
                hr.raise_for_status()
                html = hr.text
                text_val = _extract_text_snippet_from_html(html, max_chars=6000)
                if deadline_val is None:
                    deadline_val = _extract_deadline_from_html(html)
                # malý delay, aby sme boli priateľskí k službe
                time.sleep(0.1)
            except Exception as e:
                logging.warning("Could not fetch HTML for %s: %s", pubnum, e)

        docs.append(
            TenderDoc(
                id=pubnum,
                title=title,
                buyer=buyer,
                cpv=cpv,
                deadline=deadline_val,
                url=detail_url,
                text=text_val,
            )
        )

    return docs

# -- Pôvodný entrypoint, ktorý nahrádza fetch_stub_notices() -----------------

def ingest_ted_mvp(example_query: Optional[str] = None, limit: int = TED_PAGE_LIMIT) -> List[TenderDoc]:
    """
    Jednoduchý wrapper na použitie vo flow.
    example_query: ak nie je zadané, použijeme rozumné defaulty.
    """
    # Príklad „expert query“ (uprav podľa zamerania):
    # - IT služby (CPV začínajúce 72*), miesto plnenia SK/CZ, len aktívne
    # - Pozn.: V expert query používaš polia a aliasy podľa TED helpu.
    #   Napr. buyer-name (alias AU), publication-date (alias PD) atď.
    #   Kompletná syntax + aliasy sú popísané v „Expert search“ helpe.
    #   Príklad nižšie je len ilustračný.
    if not example_query:
        example_query = "(classification-cpv=72*) AND (place-of-performance IN (SVK CZE))"

    return fetch_ted_notices(query=example_query, limit=limit, page=1, scope=TED_SCOPE)