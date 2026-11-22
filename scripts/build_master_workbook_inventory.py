"""
scripts/build_master_workbook_inventory.py
========================================
Builds a traceable benchmark & audit inventory strictly from `data/raw/Master_copy_hsn.xlsx`,
verifying expected HSN labels against `data/enriched_master_hsn.parquet` without silently
modifying existing benchmark labels.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List

import openpyxl
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.benchmark_phase17_independent import INDEPENDENT_100

# Master-workbook cross-chapter evaluation items: 3 diverse headings per chapter across all 9
# chapters in Master_copy_hsn.xlsx (zero overlap with INDEPENDENT_100 or train/val query strings;
# Ch 84 & Ch 85 use remaining zero-leakage 8-digit HSNs not present in train/val).
MASTER_WORKBOOK_27: List[Dict[str, str]] = [
    # Chapter 19
    {"query": "malted milk infant food powder in retail tin", "expected_hsn": "19011010", "expected_chapter": "19", "difficulty": "commercial_specific"},
    {"query": "uncooked dry pasta containing egg semolina", "expected_hsn": "19021100", "expected_chapter": "19", "difficulty": "processing_modifier"},
    {"query": "liquid barley malt extract brewing ingredient", "expected_hsn": "19019010", "expected_chapter": "19", "difficulty": "simple"},
    # Chapter 39
    {"query": "linear low density polyethylene plastic pellets primary form", "expected_hsn": "39011010", "expected_chapter": "39", "difficulty": "technical_polymer"},
    {"query": "low density polyethylene resin granules primary form", "expected_hsn": "39011020", "expected_chapter": "39", "difficulty": "technical_polymer"},
    {"query": "interlocking poly vinyl chloride rigid conduit pipe", "expected_hsn": "39172310", "expected_chapter": "39", "difficulty": "material_form"},
    # Chapter 61
    {"query": "men knitted pure wool warm winter overcoat", "expected_hsn": "61011010", "expected_chapter": "61", "difficulty": "construction_material"},
    {"query": "men knitted kashmir goat cashmere luxury coat", "expected_hsn": "61011020", "expected_chapter": "61", "difficulty": "material_specific"},
    {"query": "knitted cotton yarn gloves for industrial handling", "expected_hsn": "61169200", "expected_chapter": "61", "difficulty": "article_material"},
    # Chapter 62
    {"query": "men woven fine animal hair tailored overcoat", "expected_hsn": "62011100", "expected_chapter": "62", "difficulty": "construction_material"},
    {"query": "men woven waterproof cotton rain trench coat", "expected_hsn": "62011210", "expected_chapter": "62", "difficulty": "functional_garment"},
    {"query": "woven cotton fabric handkerchief pocket square", "expected_hsn": "62132000", "expected_chapter": "62", "difficulty": "simple"},
    # Chapter 73
    {"query": "hot rolled steel sheet piling interlocking structural beam", "expected_hsn": "73011000", "expected_chapter": "73", "difficulty": "structural_industrial"},
    {"query": "perforated slotted mild steel racking angle section", "expected_hsn": "73012010", "expected_chapter": "73", "difficulty": "simple"},
    {"query": "stainless steel twisted wire rope strand cable", "expected_hsn": "73121030", "expected_chapter": "73", "difficulty": "material_article"},
    # Chapter 84 (Zero-leakage 8d HSNs from Master_copy_hsn.xlsx)
    {"query": "highly polished zinc sheet for printing process block making", "expected_hsn": "84425050", "expected_chapter": "84", "difficulty": "zero_leakage_technical"},
    {"query": "rotary gravure printing press industrial machinery", "expected_hsn": "84431700", "expected_chapter": "84", "difficulty": "zero_leakage_complete_machine"},
    {"query": "industrial cotton textile dyeing and bleaching machine", "expected_hsn": "84514011", "expected_chapter": "84", "difficulty": "zero_leakage_industry_specific"},
    # Chapter 85 (Zero-leakage 8d HSNs from Master_copy_hsn.xlsx)
    {"query": "high bit rate digital subscriber line hdsl telecom system", "expected_hsn": "85175040", "expected_chapter": "85", "difficulty": "zero_leakage_technical"},
    {"query": "cathode ray tube computer display monitor unit", "expected_hsn": "85284100", "expected_chapter": "85", "difficulty": "zero_leakage_complete_device"},
    {"query": "negative temperature coefficient thermistor resistor component", "expected_hsn": "85334030", "expected_chapter": "85", "difficulty": "zero_leakage_component"},
    # Chapter 87
    {"query": "pedestrian controlled walking agricultural garden tractor", "expected_hsn": "87011000", "expected_chapter": "87", "difficulty": "vehicle_specific"},
    {"query": "heavy commercial semi trailer road tractor over 1800cc", "expected_hsn": "87012090", "expected_chapter": "87", "difficulty": "numeric_threshold"},
    {"query": "armoured military combat fighting motor vehicle", "expected_hsn": "87100000", "expected_chapter": "87", "difficulty": "simple"},
    # Chapter 94
    {"query": "passenger seat built for commercial aircraft cabin", "expected_hsn": "94011000", "expected_chapter": "94", "difficulty": "intended_use"},
    {"query": "ergonomic bucket passenger seat for motor vehicle", "expected_hsn": "94012000", "expected_chapter": "94", "difficulty": "intended_use"},
    {"query": "height adjustable revolving office swivel chair seat", "expected_hsn": "94013000", "expected_chapter": "94", "difficulty": "functional_feature"},
]


KNOWN_BENCHMARK_LABEL_MISMATCHES = {
    61: "Benchmark specifies 84198970 (semiconductor/LCD vapour deposition), whereas statutory autoclave steriliser is 84192010 (AUTO CLAVES).",
    67: "Benchmark specifies 84335300 (ROOT OR TUBER HARVESTING MACHINES) for a grain threshing machine query (statutory threshing machinery is 84335200).",
    79: "Benchmark specifies 85176250 (DIGIAL LOOP CARRIER SYSTEM (DLC)) for a multiplexer query (statutory multiplexers are 85175070 / 85176270).",
    80: "Benchmark specifies 85176270 (MULTIPLEXERS) for an ethernet router query (statutory routers are 85176930).",
}


def build_inventory() -> Dict[str, Any]:
    xlsx_path = ROOT / "data" / "raw" / "Master_copy_hsn.xlsx"
    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    ws = wb["Sheet1"]
    rows: List[Dict[str, Any]] = []
    header = None
    for r_idx, row in enumerate(ws.iter_rows(values_only=True), start=1):
        vals = [("" if v is None else str(v).strip()) for v in row]
        if header is None:
            header = vals
            continue
        if not any(vals):
            continue
        rec = {header[i]: vals[i] if i < len(vals) else "" for i in range(len(header))}
        rec["_sheet"] = "Sheet1"
        rec["_excel_row"] = r_idx
        rows.append(rec)
    wb.close()

    xlsx_df = pd.DataFrame(rows)
    xlsx_df["hsn_clean"] = xlsx_df["HSN Code"].str.strip()
    xlsx_df["ch_str"] = xlsx_df["chapter_code"].str.zfill(2)
    by_hsn = {r["hsn_clean"]: r for _, r in xlsx_df.iterrows()}

    enr_df = pd.read_parquet(ROOT / "data" / "enriched_master_hsn.parquet")
    enr_df["hsn_clean"] = enr_df["hsn_code"].astype(str).str.strip()
    enr_by_hsn = {r["hsn_clean"]: r for _, r in enr_df.iterrows()}

    tr_df = pd.read_parquet(ROOT / "data" / "training_pairs" / "full_pairs_train.parquet")
    va_df = pd.read_parquet(ROOT / "data" / "training_pairs" / "full_pairs_val.parquet")
    train_hsns = set(tr_df["hsn_code"].astype(str).str.strip()) | set(va_df["hsn_code"].astype(str).str.strip())
    train_queries = {str(q).lower().strip() for q in tr_df["query"]} | {str(q).lower().strip() for q in va_df["query"]}

    ind_records: List[Dict[str, Any]] = []
    for idx, item in enumerate(INDEPENDENT_100, start=1):
        exp = item["expected_hsn"]
        xr = by_hsn.get(exp, {})
        er = enr_by_hsn.get(exp, {})
        ver_status = (
            "BENCHMARK_LABEL_MISMATCH"
            if idx in KNOWN_BENCHMARK_LABEL_MISMATCHES
            else ("VERIFIED_STATUTORY_MATCH" if exp in enr_by_hsn and exp in by_hsn else "UNVERIFIED")
        )
        ind_records.append({
            "case_id": idx,
            "query": item["query"],
            "expected_hsn": exp,
            "expected_chapter": item["expected_chapter"],
            "category": item["category"],
            "source_sheet": xr.get("_sheet", "MISSING"),
            "source_row": int(xr.get("_excel_row", -1)),
            "workbook_description": xr.get("HSN Description", ""),
            "statutory_subheading_desc": str(er.get("subheading_6digit_desc", "")),
            "statutory_tariff_item_desc": str(er.get("tariff_item_desc", "")),
            "statutory_verification_status": ver_status,
            "verification_note": KNOWN_BENCHMARK_LABEL_MISMATCHES.get(idx, ""),
            "expected_hsn_in_train_val": exp in train_hsns,
            "query_in_train_val": item["query"].lower().strip() in train_queries,
        })

    # Validate zero duplicate queries & trace MASTER_WORKBOOK_27
    seen_q = {r["query"].lower().strip() for r in INDEPENDENT_100}
    m27_records: List[Dict[str, Any]] = []
    for idx, item in enumerate(MASTER_WORKBOOK_27, start=1):
        exp = item["expected_hsn"]
        ql = item["query"].lower().strip()
        assert ql not in seen_q, f"Duplicate query with INDEPENDENT_100/m27: {ql}"
        assert ql not in train_queries, f"Query leakage with train/val: {ql}"
        assert exp in by_hsn, f"{exp} missing from Master_copy_hsn.xlsx"
        assert exp in enr_by_hsn, f"{exp} missing from enriched_master_hsn.parquet"
        seen_q.add(ql)
        xr = by_hsn[exp]
        er = enr_by_hsn[exp]
        m27_records.append({
            "case_id": idx,
            "query": item["query"],
            "expected_hsn": exp,
            "expected_chapter": item["expected_chapter"],
            "difficulty": item["difficulty"],
            "source_sheet": xr["_sheet"],
            "source_row": int(xr["_excel_row"]),
            "workbook_description": xr["HSN Description"],
            "statutory_subheading_desc": str(er.get("subheading_6digit_desc", "")),
            "statutory_tariff_item_desc": str(er.get("tariff_item_desc", "")),
            "statutory_verification_status": "VERIFIED_STATUTORY_MATCH",
            "expected_hsn_in_train_val": exp in train_hsns,
            "query_in_train_val": False,
        })

    payload = {
        "master_workbook_path": str(xlsx_path),
        "workbook_stats": {
            "sheets": ["Sheet1"],
            "total_data_rows": int(len(xlsx_df)),
            "chapters_present": sorted(xlsx_df["ch_str"].unique().tolist()),
            "chapter_count": int(xlsx_df["ch_str"].nunique()),
            "code_length_counts": {str(k): int(v) for k, v in Counter(xlsx_df["hsn_clean"].str.len()).items()},
            "unique_hsn_codes": int(xlsx_df["hsn_clean"].nunique()),
            "duplicate_hsn_rows": int(xlsx_df.duplicated(subset=["hsn_clean"]).sum()),
            "placeholder_descriptions": int((xlsx_df["HSN Description"].str.lower().str.strip() == "master category").sum()) + int(xlsx_df["HSN Description"].str.match(r"^(?:n/?a|none|null|nil|nan|-+|\.+)$", case=False).sum()),
            "zero_leakage_8digit_count": int(len(xlsx_df[(xlsx_df["hsn_clean"].str.len() == 8) & (~xlsx_df["hsn_clean"].isin(train_hsns))])),
        },
        "independent_100_traceable": ind_records,
        "master_workbook_cross_chapter_27": m27_records,
    }
    out = ROOT / "data" / "eval" / "master_workbook_traceable_inventory.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Saved {out}: workbook_rows={len(xlsx_df)}, chapters={payload['workbook_stats']['chapters_present']}, m27={len(m27_records)}")
    return payload


if __name__ == "__main__":
    build_inventory()
