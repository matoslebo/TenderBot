# flows/ingest_nen.py
import os, re, time, logging
from typing import List, Dict, Optional, Tuple
import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from app.data.models import TenderDoc  # id, title, buyer, cpv, deadline, url, text

# Konfigurácia
NEN_BASE = os.getenv("NEN_BASE", "https://nen.nipez.cz")
NEN_LANG = os.getenv("NEN_LANG", "cs")  # "cs" alebo "en"
NEN_LIST_URL = f"{NEN_BASE}/verejne-zakazky" if NEN_LANG == "cs" else f"{NEN_BASE}/{NEN_LANG}/verejne-zakazky"
NEN_TIMEOUT = float(os.getenv("NEN_TIMEOUT", "30"))
NEN_THROTTLE_SEC = float(os.getenv("NEN_THROTTLE_SEC", "0.5"))

HEADERS = {
    "User-Agent": "TenderSense-MVP/1.0 (+contact: demo)",
    "Accept-Language": "cs,en;q=0.8",
}

DETAIL_PATH_RE = re.compile(r"/(?:[a-z]{2}/)?verejne-zakazky/detail-zakazky/([A-Z0-9\-]+)")

CPV_RE = re.compile(r"\b\d{8}-\d\b")  # napr. 72222300-0
DATETIME_HINT_RE = re.compile(r"(lhůta|lhuta|term[ií]n|deadline|time\s*limit|receipt\s*of\s*tenders)", re.I)
DATETIME_CZ_RE = re.compile(r"(\d{1,2}\.\s*\d{1,2}\.\s*\d{4})(?:\s*[,\s]\s*(\d{1,2}:\d{2}))?")


def _abs_url(path: str) -> str:
    if path.startswith("http"):
        return path
    return f"{NEN_BASE}{path if path.startswith('/') else '/'+path}"

def _get(url: str) -> str:
    r = requests.get(url, timeout=NEN_TIMEOUT, headers=HEADERS)
    r.raise_for_status()
    return r.text

def _find_detail_links(html: str, max_links: int) -> List[str]:
    soup = BeautifulSoup(html, "lxml")
    links = []
    for a in soup.find_all("a", href=True):
        m = DETAIL_PATH_RE.search(a["href"])
        if m:
            links.append(_abs_url(a["href"]))
        if len(links) >= max_links:
            break
    # zbav sa duplicit (zoznam môže obsahovať link viackrát)
    seen, uniq = set(), []
    for u in links:
        if u not in seen:
            uniq.append(u); seen.add(u)
    return uniq

def _extract_title(soup: BeautifulSoup) -> Optional[str]:
    # typicky <h1> v hlavičke detailu
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        return h1.get_text(" ", strip=True)
    # fallback: <title>
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    return None

def _extract_buyer(soup: BeautifulSoup) -> Optional[str]:
    # Hľadaj label "Zadavatel" alebo "Contracting Authority"
    labels = ["Zadavatel", "Zadavatel", "Contracting Authority", "Contracting authority"]
    # pokus 1: definície <dt>/<dd>
    for dt in soup.find_all("dt"):
        key = dt.get_text(" ", strip=True)
        if any(lbl.lower() in key.lower() for lbl in labels):
            dd = dt.find_next_sibling("dd")
            if dd:
                return dd.get_text(" ", strip=True)
    # pokus 2: tabuľky
    for tr in soup.find_all("tr"):
        th = tr.find("th")
        td = tr.find("td")
        if th and td:
            key = th.get_text(" ", strip=True)
            if any(lbl.lower() in key.lower() for lbl in labels):
                return td.get_text(" ", strip=True)
    return None

def _extract_cpv(soup: BeautifulSoup) -> Optional[List[str]]:
    text = soup.get_text(" ", strip=True)
    codes = list(sorted(set(CPV_RE.findall(text))))
    return codes or None

def _try_parse_datetime(val: str) -> Optional[str]:
    try:
        return date_parser.parse(val, dayfirst=True).isoformat()
    except Exception:
        return None

def _extract_deadline(soup: BeautifulSoup) -> Optional[str]:
    # 1) <time datetime="...">
    for t in soup.find_all("time"):
        val = t.get("datetime") or t.get_text(strip=True)
        iso = _try_parse_datetime(val)
        if iso:
            # zvyčajne tieto <time> tagy sú spoľahlivé
            return iso

    # 2) Label + hodnota v okolí
    for tag in soup.find_all(["div", "p", "li", "dt", "th", "td", "span"]):
        txt = tag.get_text(" ", strip=True)
        if DATETIME_HINT_RE.search(txt):
            # pozri najbližší kandidát s dátumom
            cand = tag.find_next(["time", "span", "td", "dd", "div"])
            if cand:
                raw = cand.get("datetime") or cand.get_text(" ", strip=True)
                iso = _try_parse_datetime(raw)
                if iso:
                    return iso

    # 3) Hrubá heuristika cez celý text (CZ formát dd.mm.yyyy [hh:mm])
    text = soup.get_text(" ", strip=True)
    m = DATETIME_CZ_RE.search(text)
    if m:
        iso = _try_parse_datetime(m.group(0))
        if iso:
            return iso

    # nič spoľahlivé – radšej vráť None, NIE raw text
    return None

def _extract_subject_text(soup: BeautifulSoup, max_chars: int = 8000) -> Optional[str]:
    # Typicky sekcia "Popis předmětu" (CS) alebo "SUBJECT-MATTER DESCRIPTION" (EN)
    headers = soup.find_all(["h2", "h3", "h4"])
    for h in headers:
        label = h.get_text(" ", strip=True).lower()
        if any(k in label for k in ["popis předmětu", "předmět zakázky", "subject-matter"]):
            # zober nasledujúce odseky až po ďalšiu hlavičku
            parts = []
            sib = h.find_next_sibling()
            while sib and sib.name not in ["h2", "h3", "h4"]:
                txt = sib.get_text(" ", strip=True)
                if txt:
                    parts.append(txt)
                sib = sib.find_next_sibling()
            text = " ".join(parts).strip()
            if text:
                return text[:max_chars]
    # fallback: prvé väčšie <section> alebo dlhší <p>
    for p in soup.find_all("p"):
        s = p.get_text(" ", strip=True)
        if len(s) > 120:
            return s[:max_chars]
    return None

def _parse_detail(url: str) -> TenderDoc:
    html = _get(url)
    soup = BeautifulSoup(html, "lxml")
    title = _extract_title(soup)
    buyer = _extract_buyer(soup)
    cpv = _extract_cpv(soup)
    deadline = _extract_deadline(soup)
    if deadline and not _try_parse_datetime(deadline):
        # poistka – ak by prišiel neparsovateľný string, zahodíme
        deadline = None
    text = _extract_subject_text(soup)
    m = re.search(r"/detail-zakazky/([A-Z0-9\-]+)", url)
    tid = m.group(1) if m else url.rsplit("/", 1)[-1]
    return TenderDoc(
        id=tid,
        title=title or tid,
        buyer=buyer,
        cpv=cpv,
        deadline=deadline,  # ISO string alebo None → Pydantic si to skonvertuje
        url=url,
        text=text,
    )

def fetch_nen_recent(limit: int = 30) -> List[TenderDoc]:
    """
    Zoberie posledné zákazky zo zoznamu a načíta ich detaily (do 'limit').
    """
    html = _get(NEN_LIST_URL)
    links = _find_detail_links(html, max_links=limit * 2)  # nájdeme viac, potom osekáme duplicitné
    docs: List[TenderDoc] = []
    for link in links[:limit]:
        try:
            docs.append(_parse_detail(link))
            time.sleep(NEN_THROTTLE_SEC)
        except Exception as e:
            logging.warning("NEN detail parse failed for %s: %s", link, e)
    return docs
