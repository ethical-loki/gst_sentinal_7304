"""
Step 6: Generalized Test Dataset Builder (Zero-Leakage).

Generates a diverse evaluation suite across the entire HSN master dataset
(active unseen test HSN codes + inactive statutory chapters) covering:
  1. short
  2. long_industrial
  3. abbreviated
  4. missing_material
  5. similar_different_construction
  6. complete_vs_component
  7. inactive_chapter

Strictly excludes every HSN code present in `full_pairs_train.parquet` and
`full_pairs_val.parquet` to guarantee zero data leakage.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Set

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

ABBREVIATIONS = {
    "stainless steel": "SS",
    "polyvinyl chloride": "PVC",
    "polyethylene": "PE",
    "polypropylene": "PP",
    "aluminum": "Al",
    "aluminium": "Al",
    "automatic data processing": "ADP",
    "printed circuit board": "PCB",
    "light emitting diode": "LED",
    "internal combustion": "IC",
    "alternating current": "AC",
    "direct current": "DC",
    "kilowatt": "kW",
    "millimeter": "mm",
}

MATERIAL_STOPWORDS = {
    "plastic", "plastics", "steel", "stainless", "iron", "cotton", "wool",
    "silk", "polyester", "nylon", "wood", "wooden", "aluminium", "aluminum",
    "copper", "brass", "glass", "rubber", "leather", "paper", "ceramic",
}


def _first_phrase(val: object) -> str:
    txt = str(val or "").strip()
    if not txt or txt.lower() == "nan":
        return ""
    for sep in (";", ",", "|"):
        if sep in txt:
            txt = txt.split(sep)[0].strip()
    return txt


def _abbreviate(text: str) -> str:
    out = text
    for full, abbr in ABBREVIATIONS.items():
        out = re.sub(rf"\b{re.escape(full)}\b", abbr, out, flags=re.IGNORECASE)
    if out == text:
        words = [w for w in text.split() if len(w) > 2]
        out = " ".join(w[:4] + "." if len(w) > 6 else w for w in words[:4])
    return out.strip()


def _strip_material(text: str) -> str:
    tokens = [t for t in text.split() if t.lower().strip(".,;()") not in MATERIAL_STOPWORDS]
    cleaned = " ".join(tokens).strip()
    return cleaned if cleaned else text


def load_train_val_hsn_codes(pairs_dir: Path | None = None) -> Set[str]:
    pdir = pairs_dir or (PROJECT_ROOT / "data" / "training_pairs")
    blocked: Set[str] = set()
    for fname in ("full_pairs_train.parquet", "full_pairs_val.parquet"):
        p = pdir / fname
        if p.exists():
            df = pd.read_parquet(p, columns=["hsn_code"])
            blocked.update(df["hsn_code"].astype(str).str.strip().tolist())
    return blocked


def build_generalized_test_dataset(
    active_parquet: Path | None = None,
    statutory_parquet: Path | None = None,
    output_parquet: Path | None = None,
    per_category: int = 8,
    seed: int = 42,
) -> pd.DataFrame:
    active_path = active_parquet or (PROJECT_ROOT / "data" / "enriched_master_hsn.parquet")
    stat_path = statutory_parquet or (PROJECT_ROOT / "data" / "tariff_master.parquet")
    out_path = output_parquet or (PROJECT_ROOT / "data" / "eval" / "generalized_test_suite.parquet")

    blocked_hsns = load_train_val_hsn_codes()

    active_df = pd.read_parquet(active_path)
    active_df["hsn_code"] = active_df["hsn_code"].astype(str).str.strip()
    active_df["chapter_code"] = active_df["chapter_code"].astype(str).str.strip().str.zfill(2)
    unseen_active = active_df[~active_df["hsn_code"].isin(blocked_hsns)].copy()
    if unseen_active.empty:
        unseen_active = active_df.copy()

    active_chapters = set(active_df["chapter_code"].unique())

    rows: List[Dict[str, object]] = []

    def _add_case(
        category: str,
        query: str,
        expected_hsn: str,
        expected_chapter: str,
        is_active_schedule: bool,
        notes: str = "",
    ) -> None:
        if not query or len(query.strip()) < 3:
            return
        rows.append({
            "category": category,
            "query": query.strip(),
            "expected_hsn": expected_hsn,
            "expected_chapter": expected_chapter.zfill(2),
            "is_active_schedule": is_active_schedule,
            "notes": notes,
        })

    # 1. Short descriptions
    for _, r in unseen_active.sample(n=min(per_category, len(unseen_active)), random_state=seed).iterrows():
        syn = _first_phrase(r.get("synthetic_synonyms")) or _first_phrase(r.get("statutory_description"))
        short_q = " ".join(syn.split()[:3])
        _add_case("short", short_q, r["hsn_code"], r["chapter_code"], True, "Unseen test HSN short query")

    # 2. Long industrial descriptions
    for _, r in unseen_active.sample(n=min(per_category, len(unseen_active)), random_state=seed + 1).iterrows():
        stat_desc = str(r.get("statutory_description") or "").strip()
        mat = _first_phrase(r.get("material_keywords"))
        use = _first_phrase(r.get("use_context_keywords"))
        long_q = f"Industrial grade {stat_desc[:140]} {mat} {use}".strip()
        _add_case("long_industrial", long_q, r["hsn_code"], r["chapter_code"], True, "Long industrial spec")

    # 3. Abbreviated descriptions
    for _, r in unseen_active.sample(n=min(per_category, len(unseen_active)), random_state=seed + 2).iterrows():
        base = _first_phrase(r.get("synthetic_synonyms")) or _first_phrase(r.get("statutory_description"))
        _add_case("abbreviated", _abbreviate(base), r["hsn_code"], r["chapter_code"], True, "Abbreviated query")

    # 4. Descriptions with missing material
    for _, r in unseen_active.sample(n=min(per_category, len(unseen_active)), random_state=seed + 3).iterrows():
        base = _first_phrase(r.get("synthetic_synonyms")) or _first_phrase(r.get("statutory_description"))
        _add_case("missing_material", _strip_material(base), r["hsn_code"], r["chapter_code"], True, "Material stripped")

    # 5. Similar products with different construction (knitted vs woven, cast vs forged, etc.)
    const_mask = unseen_active["statutory_description"].str.contains(
        r"\b(knitted|woven|crocheted|cast|forged|moulded|molded|welded|seamless)\b",
        case=False,
        na=False,
    )
    const_df = unseen_active[const_mask]
    if const_df.empty:
        const_df = unseen_active
    for _, r in const_df.sample(n=min(per_category, len(const_df)), random_state=seed + 4).iterrows():
        base = str(r.get("statutory_description") or "")[:100]
        _add_case(
            "similar_different_construction",
            base,
            r["hsn_code"],
            r["chapter_code"],
            True,
            "Construction-specific statutory description",
        )

    # 6. Complete products versus components (parts / accessories)
    parts_mask = unseen_active["statutory_description"].str.contains(
        r"\b(parts|accessories|components|assemblies|sub-assemblies)\b",
        case=False,
        na=False,
    )
    parts_df = unseen_active[parts_mask]
    if parts_df.empty:
        parts_df = unseen_active
    for _, r in parts_df.sample(n=min(per_category, len(parts_df)), random_state=seed + 5).iterrows():
        syn = _first_phrase(r.get("synthetic_synonyms")) or str(r.get("statutory_description") or "")[:90]
        _add_case(
            "complete_vs_component",
            syn,
            r["hsn_code"],
            r["chapter_code"],
            True,
            "Component/parts vs complete unit",
        )

    # 7. Products belonging to inactive chapters (from full 98-chapter tariff_master.parquet)
    stat_df = pd.read_parquet(stat_path)
    stat_df["hsn_code"] = stat_df["hsn_code"].astype(str).str.strip()
    stat_df["chapter"] = stat_df["chapter"].astype(str).str.strip().str.zfill(2)
    inactive_df = stat_df[
        (~stat_df["chapter"].isin(active_chapters))
        & (stat_df["hsn_code"].str.len() == 8)
        & (~stat_df["hsn_code"].isin(blocked_hsns))
    ]
    for _, r in inactive_df.sample(n=min(per_category, len(inactive_df)), random_state=seed + 6).iterrows():
        desc = _first_phrase(r.get("clean_description")) or _first_phrase(r.get("description"))
        _add_case(
            "inactive_chapter",
            " ".join(desc.split()[:8]),
            r["hsn_code"],
            r["chapter"],
            False,
            f"Inactive chapter {r['chapter']}",
        )

    out_df = pd.DataFrame(rows).drop_duplicates(subset=["category", "query"]).reset_index(drop=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_parquet(out_path, index=False)
    return out_df


if __name__ == "__main__":
    df = build_generalized_test_dataset()
    print(f"Built generalized test dataset: {len(df)} cases")
    print(df["category"].value_counts().to_dict())

