# app/llm/structured_extract.py
from __future__ import annotations
import json
import os
import re
from typing import List, Optional, Tuple, Any, Dict
from datetime import datetime
from pydantic import BaseModel, Field, validator, constr, ValidationError
from dateutil import parser as date_parser

from .providers import generate_json, has_llm

# ====== Pydantic schéma výstupu ======

CPVCode = constr(pattern=r"^\d{8}(?:-\d)?$")  # 8 číslic + voliteľný check digit, napr. 72222300-0

class ExtractionOut(BaseModel):
    deadline: Optional[datetime] = Field(
        None,
        description="Deadline vo formáte ISO 8601 (napr. 2025-08-17T16:00:00Z)."
    )
    cpv: List[CPVCode] = Field(
        default_factory=list,
        description="Zoznam CPV kódov (8 číslic, voliteľne '-X')."
    )
    requirements: List[constr(min_length=3, max_length=400)] = Field(
        default_factory=list,
        description="Zoznam stručných bodov požiadaviek (max ~400 znakov každý)."
    )

    @validator("cpv", pre=True, each_item=True)
    def _normalize_cpv(cls, v: str) -> str:
        return v.strip()

# ====== Prompty a pomocné funkcie ======

SYSTEM = (
    "Si extrakčný engine pre verejné obstarávania. "
    "Extrahuj požadované polia presne podľa schémy a vráť IBA JSON."
)

def _build_user_prompt(text: str, lang: str = "sk") -> str:
    # Prompt v SK/CS je OK, modely chápu aj mix
    return f"""
Text (jazyk: {lang}):
\"\"\"{text[:12000]}\"\"\"

ÚLOHA:
1) deadline – ak je uvedený, daj ISO8601 (napr. 2025-08-17T16:00:00Z). Ak čas chýba, daj len dátum (00:00Z).
2) cpv – všetky CPV kódy, ktoré sa v texte vyskytnú (formát 8 číslic, voliteľne '-X').
3) requirements – 3 až 10 bodov (stručné vety) so zásadnými požiadavkami na dodávateľa / predmet.

Výstup: IBA JSON, bez komentárov ani vysvetlení.
"""

def _schema_dict() -> Dict[str, Any]:
    # Pydantic → JSON Schema (použijeme pre „strict“ JSON u podporovaných providerov)
    return ExtractionOut.model_json_schema()

def _fallback_regex_cpv(text: str) -> List[str]:
    # Záložná heuristika, keby LLM zlyhalo
    hits = re.findall(r"\b(\d{8}(?:-\d)?)\b", text)
    out, seen = [], set()
    for h in hits:
        if h not in seen:
            out.append(h); seen.add(h)
    return out[:15]

# ====== Hlavná extrakcia s repair slučkou ======

def extract_structured(
    text: str,
    lang: str = "sk",
    max_retries: int = 2,
    strict_json: bool = True,
) -> Tuple[ExtractionOut, str]:
    """
    Vráti (pydantic_obj, raw_json_str). Používa LLM + JSON schema a repair slučku.
    Ak LLM/JSON zlyhá, vráti heuristický fallback pre CPV a prázdne ostatné polia.
    """
    if not has_llm():
        # Bez LLM: fallback
        cpv = _fallback_regex_cpv(text)
        return ExtractionOut(cpv=cpv, requirements=[], deadline=None), json.dumps({"cpv": cpv, "requirements": [], "deadline": None})

    user = _build_user_prompt(text, lang=lang)
    schema = _schema_dict()

    last_json = None
    last_err = None

    for attempt in range(max_retries + 1):
        if attempt == 0:
            # 1) prvý pokus – „strict JSON“ ak provider podporuje
            raw = generate_json(
                prompt=user,
                system=SYSTEM,
                schema=schema if strict_json else None,
                enforce_json=True
            )
        else:
            # 2) repair prompt s vysvetlením chýb
            repair_msg = f"""
Toto je NÁVRAT LLM, ktorý porušuje schému alebo nie je platný JSON:

<raw_json>
{last_json}
</raw_json>

Chyby validácie:
{last_err}

Oprav JSON tak, aby presne spĺňal schému (typy, formáty, rozsahy). Vráť iba JSON.
"""
            raw = generate_json(
                prompt=repair_msg,
                system=SYSTEM,
                schema=schema if strict_json else None,
                enforce_json=True
            )

        last_json = raw

        # Skús parse + validáciu
        try:
            data = json.loads(raw)
        except Exception as e:
            last_err = f"JSON parse error: {e}"
            continue

        try:
            obj = ExtractionOut.model_validate(data)
            return obj, json.dumps(obj.model_dump(mode="json"), ensure_ascii=False)
        except ValidationError as ve:
            last_err = ve.json()

    # Fallback ak všetky pokusy zlyhali
    cpv = _fallback_regex_cpv(text)
    return ExtractionOut(cpv=cpv, requirements=[], deadline=None), json.dumps({"cpv": cpv, "requirements": [], "deadline": None}, ensure_ascii=False)
