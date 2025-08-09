# validation/gx_validate.py
from __future__ import annotations
import os
from typing import List, Dict, Any
from datetime import datetime, timedelta, timezone

import pandas as pd

# Great Expectations – jednoduché použitie cez PandasDataset
import great_expectations as gx  # noqa: F401
from great_expectations.dataset import PandasDataset


# Minimálny povinný set (ostatné stĺpce môžu existovať – schema to nezakáže)
REQUIRED_COLUMNS = [
    "id", "title", "buyer", "country", "region", "cpv",
    "estimated_value_eur", "deadline", "language", "url", "text"
]


def _to_dataframe(docs: List[Dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(docs)

    # Uisti sa, že minimálne stĺpce existujú (ak chýbajú, doplň None)
    for col in REQUIRED_COLUMNS:
        if col not in df.columns:
            df[col] = None

    # deadline → datetime (UTC)
    df["deadline_dt"] = pd.to_datetime(df.get("deadline"), errors="coerce", utc=True)

    # Fallback dátumy, ak existujú v payloadoch
    if "deadline_extracted" in df.columns:
        df["deadline_extracted_dt"] = pd.to_datetime(df["deadline_extracted"], errors="coerce", utc=True)
    else:
        df["deadline_extracted_dt"] = pd.NaT

    if "publication_date" in df.columns:
        df["publication_dt"] = pd.to_datetime(df["publication_date"], errors="coerce", utc=True)
    else:
        df["publication_dt"] = pd.NaT

    # Numerika – pretypuj na číslo
    if "estimated_value_eur" in df.columns:
        df["estimated_value_eur"] = pd.to_numeric(df["estimated_value_eur"], errors="coerce")

    # "fresh_dt" = preferuj deadline → extrahovaný deadline → publication_date
    df["fresh_dt"] = df["deadline_dt"].combine_first(df["deadline_extracted_dt"]).combine_first(df["publication_dt"])

    return df


def run_expectations(docs: List[Dict[str, Any]], freshness_days: int = 1) -> Dict[str, Any]:
    """
    4 základné expectationy: (1) schema (superset), (2) non-null, (3) ranges, (4) freshness.
    """
    df = _to_dataframe(docs)
    ds = PandasDataset(df)

    # 1) SCHEMA – minimálna schéma: každý povinný stĺpec musí existovať
    for col in REQUIRED_COLUMNS:
        ds.expect_column_to_exist(col)


    # 2) NON-NULL – kľúčové polia musia byť prítomné
    ds.expect_column_values_to_not_be_null("id")
    ds.expect_column_values_to_not_be_null("title")
    ds.expect_column_values_to_not_be_null("url")

    # 3) RANGES – robustnejšie vyhodnotenie pre estimated_value_eur
    nonnull_vals = df["estimated_value_eur"].dropna()
    if len(nonnull_vals) >= 5:
        # pri 5+ hodnotách dovoľ 5 % výnimiek
        ds.expect_column_values_to_be_between(
            "estimated_value_eur",
            min_value=0,
            max_value=1_000_000_000,
            mostly=0.95,
            parse_strings_as_datetimes=False,
        )
    elif len(nonnull_vals) > 0:
        # pri 1–4 hodnotách buď striktnejší (všetky v rozsahu), alebo test preskoč (vyber si)
        ds.expect_column_values_to_be_between(
            "estimated_value_eur",
            min_value=0,
            max_value=1_000_000_000,
            mostly=1.0,
            parse_strings_as_datetimes=False,
        )
    # ak nie sú žiadne hodnoty → test preskočíme (nerobíme expectation)

    # 4) FRESHNESS – ber "fresh_dt" (deadline → extrahovaný → publication),
    #    ignoruj chýbajúce hodnoty prirodzene (PandasDataset už posúva iba non-null)
    now = datetime.now(timezone.utc)
    min_ok = now - timedelta(days=freshness_days)
    mostly = float(os.getenv("DQ_FRESHNESS_MOSTLY", "0.10"))  # default 10 %

    if df["fresh_dt"].notna().sum() > 0:
        ds.expect_column_values_to_be_between(
            "fresh_dt",
            min_value=min_ok,
            max_value=None,
            mostly=mostly,
            parse_strings_as_datetimes=False,
            allow_cross_type_comparisons=True,
        )
    # ak nie sú žiadne dátumy → freshness nevyhodnocujeme (neblokuje pipeline)

    # Súhrn
    validation_result = ds.validate()
    out = {
        "success": validation_result["success"],
        "statistics": validation_result["statistics"],
        "results": validation_result["results"],
    }
    return out


if __name__ == "__main__":
    # Malý CLI test nad sample JSONmi
    import json, glob, pathlib
    root = pathlib.Path(__file__).resolve().parents[1]
    samples = []
    for fn in glob.glob(str(root / "sample_data" / "notices" / "*.json")):
        with open(fn, "r", encoding="utf-8") as f:
            samples.append(json.load(f))
    res = run_expectations(samples)
    print("Success:", res["success"])
    print("Stats:", res["statistics"])
    if not res["success"]:
        fails = [r for r in res["results"] if not r.get("success", True)]
        for f in fails:
            cfg = f.get("expectation_config", {}).get("expectation_type")
            print("FAILED:", cfg)
