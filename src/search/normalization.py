"""
Layer 1: Data Normalization & Enrichment Engine
================================================
Cleans customs tariff text, extracts hierarchical WCO components (Chapter,
4-Digit Heading, 6-Digit Subheading, 8-Digit Tariff Item), injects commercial
trade synonyms, and builds separate display vs. search texts.
"""

import re
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
import pandas as pd

logger = logging.getLogger(__name__)

# Dynamic trade synonyms dictionary (neutralized; dynamic synonyms extracted from Master dataset columns)
COMMERCIAL_SYNONYMS_MAP: Dict[str, List[str]] = {}


def clean_tariff_text(raw_text: str) -> str:
    """
    Cleans OCR artifacts, extra punctuation, and formatting noise from statutory text.
    """
    if not raw_text or pd.isna(raw_text):
        return ""
    text = str(raw_text).strip()
    # Normalize colons, hyphens, and bullet artifacts
    text = re.sub(r"[\s\:\;\-\–\—]{2,}", " - ", text)
    text = re.sub(r"^\s*[\-\–\—\:\;\.]+\s*", "", text)
    text = re.sub(r"\s*[\-\–\—\:\;]+\s*$", "", text)
    # Strip brackets artifacts like [handloom cotton] if messy
    text = re.sub(r"\s+", " ", text)
    return text.strip()


class MasterHSNEnricher:
    """
    Enriches Master_copy_hsn.xlsx into structured Layer 1 records.
    """

    def __init__(self, raw_excel_path: Optional[Path] = None):
        base_dir = Path(__file__).resolve().parent.parent.parent
        self.raw_path = raw_excel_path or (base_dir / "data" / "raw" / "Master_copy_hsn.xlsx")
        self.enriched_df: Optional[pd.DataFrame] = None

    def process(self) -> pd.DataFrame:
        if not self.raw_path.exists():
            raise FileNotFoundError(f"Master file not found at: {self.raw_path}")

        raw_df = pd.read_excel(self.raw_path)
        raw_df["code_str"] = raw_df["HSN Code"].astype(str).str.replace(" ", "").str.strip()
        raw_df["chapter_str"] = raw_df["chapter_code"].astype(str).str.strip().str.zfill(2)

        # 1. Build dictionary of 4-digit headings and 6-digit subheadings
        heading_4_map: Dict[str, str] = {}
        subheading_6_map: Dict[str, str] = {}

        for _, row in raw_df.iterrows():
            c = row["code_str"]
            d = clean_tariff_text(str(row.get("HSN Description", "")))
            if len(c) == 4:
                heading_4_map[c] = d
            elif len(c) == 6:
                subheading_6_map[c] = d

        # 2. Enrich all records (prioritizing 8-digit tariff items)
        enriched_rows: List[Dict[str, Any]] = []

        for _, row in raw_df.iterrows():
            code = row["code_str"]
            raw_desc = str(row.get("HSN Description", "")).strip()
            ch_code = row["chapter_str"]
            ch_title = clean_tariff_text(str(row.get("chapter_title", "")))
            art_kws = clean_tariff_text(str(row.get("Article Keywords", "")))
            mat_kws = clean_tariff_text(str(row.get("Material Keywords", "")))

            h4 = code[:4] if len(code) >= 4 else code
            h6 = code[:6] if len(code) >= 6 else code

            h4_desc = heading_4_map.get(h4, "")
            h6_desc = subheading_6_map.get(h6, "")

            # If this is an 8-digit item, separate the specific item sub-clause
            item_desc = ""
            if len(code) == 8:
                if ":" in raw_desc:
                    item_desc = clean_tariff_text(raw_desc.split(":")[-1])
                elif "-" in raw_desc:
                    item_desc = clean_tariff_text(raw_desc.split("-")[-1])
                else:
                    item_desc = clean_tariff_text(raw_desc)
            elif len(code) == 6:
                item_desc = clean_tariff_text(raw_desc)
            elif len(code) == 4:
                item_desc = clean_tariff_text(raw_desc)

            # Retrieve injected commercial synonyms for 8-digit, 6-digit, and 4-digit codes
            synonyms: List[str] = []
            for k in [code, h6, h4]:
                if k in COMMERCIAL_SYNONYMS_MAP:
                    synonyms.extend(COMMERCIAL_SYNONYMS_MAP[k])
            # Deduplicate synonyms
            seen_syn = set()
            unique_synonyms = []
            for s in synonyms:
                s_clean = s.strip().lower()
                if s_clean not in seen_syn:
                    seen_syn.add(s_clean)
                    unique_synonyms.append(s_clean)
            consumer_synonyms_str = ", ".join(unique_synonyms)

            # Build statutory display text vs. search index text
            statutory_description = raw_desc

            # Construct comprehensive Search_Index_Text
            search_parts = [
                f"Chapter {ch_code}: {ch_title}",
                f"Heading {h4}: {h4_desc}" if h4_desc else "",
                f"Subheading {h6}: {h6_desc}" if h6_desc else "",
                f"Tariff Item {code}: {item_desc}" if item_desc else "",
                f"Trade Synonyms: {consumer_synonyms_str}" if consumer_synonyms_str else "",
                f"Articles: {art_kws}" if art_kws else "",
                f"Materials: {mat_kws}" if mat_kws else ""
            ]
            search_index_text = " | ".join(p for p in search_parts if p.strip())

            enriched_rows.append({
                "hsn_code": code,
                "code_length": len(code),
                "chapter_code": ch_code,
                "chapter_title": ch_title,
                "heading_4digit": h4,
                "heading_4digit_desc": h4_desc,
                "subheading_6digit": h6,
                "subheading_6digit_desc": h6_desc,
                "tariff_item_8digit": code if len(code) == 8 else None,
                "tariff_item_desc": item_desc,
                "statutory_description": statutory_description,
                "consumer_synonyms": consumer_synonyms_str,
                "article_keywords": art_kws,
                "material_keywords": mat_kws,
                "search_index_text": search_index_text
            })

        self.enriched_df = pd.DataFrame(enriched_rows)
        return self.enriched_df

    def save(self, output_parquet_path: Optional[Path] = None):
        if self.enriched_df is None:
            self.process()
        base_dir = Path(__file__).resolve().parent.parent.parent
        out_path = output_parquet_path or (base_dir / "data" / "enriched_master_hsn.parquet")
        self.enriched_df.to_parquet(out_path, index=False)
        logger.info(f"[MasterHSNEnricher] Enriched dataset saved to: {out_path} ({len(self.enriched_df)} rows)")
        return out_path

