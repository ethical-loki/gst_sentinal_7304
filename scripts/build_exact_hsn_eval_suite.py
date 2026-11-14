"""
Build a verified Exact-HSN & Progressive Clarification Evaluation Dataset
(`data/eval/exact_hsn_eval_suite.parquet`) from unseen 8-digit leaf HSNs
in `data/enriched_master_hsn.parquet`.

Zero overlap with `full_pairs_train.parquet`, `generalized_test_suite.parquet`,
or `generalized_test_large.parquet`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Set

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _clean_text(val: object) -> str:
    s = str(val or "").strip()
    if s.lower() in ("", "nan", "none", "other", "others", "-"):
        return ""
    return re.sub(r"\s+", " ", s).strip()


def main() -> None:
    master = pd.read_parquet(PROJECT_ROOT / "data" / "enriched_master_hsn.parquet")

    used_hsns: Set[str] = set()
    used_queries: Set[str] = set()
    for p in [
        PROJECT_ROOT / "data" / "eval" / "generalized_test_suite.parquet",
        PROJECT_ROOT / "data" / "eval" / "generalized_test_large.parquet",
    ]:
        if p.exists():
            d = pd.read_parquet(p)
            used_hsns.update(d["expected_hsn"].astype(str).str.strip())
            used_queries.update(d["query"].astype(str).str.strip().str.lower())

    train_p = PROJECT_ROOT / "data" / "training_pairs" / "full_pairs_train.parquet"
    if train_p.exists():
        td = pd.read_parquet(train_p)
        for col in ("hsn_code", "expected_hsn"):
            if col in td.columns:
                used_hsns.update(td[col].astype(str).str.strip())
        for col in ("query", "product_description", "anchor"):
            if col in td.columns:
                used_queries.update(td[col].astype(str).str.strip().str.lower())

    # Filter to 8-digit leaf HSNs with specific (non-"Other") statutory descriptions
    leaf = master[master["hsn_code"].astype(str).str.strip().str.len() == 8].copy()
    leaf["hsn_code"] = leaf["hsn_code"].astype(str).str.strip()
    leaf["chapter_code"] = leaf["chapter_code"].astype(str).str.strip().str.zfill(2)
    leaf = leaf[~leaf["hsn_code"].isin(used_hsns)].copy()

    # Keep rows whose tariff_item_desc or statutory_description is informative
    rows: List[Dict[str, object]] = []
    chapters = sorted(leaf["chapter_code"].unique().tolist())

    for ch in chapters:
        ch_df = leaf[leaf["chapter_code"] == ch].copy()
        # Prefer unique statutory_description within the chapter so exact 8-digit target is unambiguous
        desc_counts = ch_df["statutory_description"].astype(str).str.lower().value_counts()
        ch_df["desc_freq"] = ch_df["statutory_description"].astype(str).str.lower().map(desc_counts)

        specific = ch_df[
            (ch_df["desc_freq"] == 1)
            & (ch_df["tariff_item_desc"].apply(lambda x: len(_clean_text(x)) >= 12))
            & (ch_df["heading_4digit_desc"].apply(lambda x: len(_clean_text(x)) >= 8))
        ].reset_index(drop=True)

        if specific.empty:
            continue

        # 3 detailed unambiguous exact-HSN cases per chapter
        for idx in range(min(3, len(specific))):
            r = specific.iloc[idx]
            h4 = _clean_text(r["heading_4digit_desc"])
            s6 = _clean_text(r["subheading_6digit_desc"])
            t8 = _clean_text(r["tariff_item_desc"])
            mat = _clean_text(r["material_keywords"])

            parts = []
            for p in (h4, s6, t8):
                if p and p.lower() not in " ".join(parts).lower():
                    parts.append(p)
            detailed_query = " - ".join(parts)
            if mat and mat.lower() not in detailed_query.lower():
                detailed_query = f"{detailed_query} ({mat.split(',')[0].strip()})"

            if detailed_query.lower() in used_queries:
                continue
            used_queries.add(detailed_query.lower())
            rows.append({
                "case_type": "exact_detailed",
                "query": detailed_query,
                "expected_hsn": r["hsn_code"],
                "expected_chapter": ch,
                "clarification_attributes_json": "{}",
                "is_active_schedule": True,
                "notes": f"Unseen 8-digit leaf HSN {r['hsn_code']} in chapter {ch}",
            })

        # 2 ambiguous + progressive clarification cases per chapter
        start_amb = min(3, len(specific))
        for idx in range(start_amb, min(start_amb + 2, len(specific))):
            r = specific.iloc[idx]
            h4 = _clean_text(r["heading_4digit_desc"])
            s6 = _clean_text(r["subheading_6digit_desc"])
            t8 = _clean_text(r["tariff_item_desc"])
            mat = _clean_text(r["material_keywords"])

            ambiguous_query = h4
            if ambiguous_query.lower() in used_queries:
                art = _clean_text(r["article_keywords"])
                ambiguous_query = f"{h4} {art.split(',')[0].strip()}".strip() if art else h4

            clar_attrs: Dict[str, str] = {}
            if t8:
                clar_attrs["specification"] = t8
            if s6 and s6.lower() != t8.lower():
                clar_attrs["category"] = s6
            if mat:
                clar_attrs["material"] = mat.split(",")[0].strip()

            rows.append({
                "case_type": "ambiguous_with_clarification",
                "query": ambiguous_query,
                "expected_hsn": r["hsn_code"],
                "expected_chapter": ch,
                "clarification_attributes_json": json.dumps(clar_attrs),
                "is_active_schedule": True,
                "notes": f"Ambiguous heading query resolving to {r['hsn_code']} after clarification",
            })

    out_df = pd.DataFrame(rows)
    out_path = PROJECT_ROOT / "data" / "eval" / "exact_hsn_eval_suite.parquet"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_parquet(out_path, index=False)
    print(f"Saved {len(out_df)} verified exact-HSN eval cases to {out_path}")
    print(out_df["case_type"].value_counts().to_dict())
    print("Chapters covered:", sorted(out_df["expected_chapter"].unique().tolist()))


if __name__ == "__main__":
    main()

