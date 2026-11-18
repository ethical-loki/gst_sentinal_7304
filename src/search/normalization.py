"""
Layer 1: Data Normalization & Enrichment Engine
================================================
Cleans customs tariff text, extracts hierarchical WCO components (Chapter,
4-Digit Heading, 6-Digit Subheading, 8-Digit Tariff Item), injects commercial
trade synonyms, and builds separate display vs. search texts.
"""

import json
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

    def __init__(
        self,
        raw_excel_path: Optional[Path] = None,
        itc_json_path: Optional[Path] = None,
        gst_json_path: Optional[Path] = None,
    ):
        base_dir = Path(__file__).resolve().parent.parent.parent
        self.raw_path = raw_excel_path or (base_dir / "data" / "raw" / "Master_copy_hsn.xlsx")
        self.itc_json_path = itc_json_path or (base_dir / "data" / "raw" / "itc_hs_codes.json")
        self.gst_json_path = gst_json_path or (base_dir / "data" / "raw" / "gst_rates.json")
        self.enriched_df: Optional[pd.DataFrame] = None

    @staticmethod
    def _load_itc_map(path: Path) -> Dict[str, str]:
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"Failed loading ITC-HS JSON from {path}: {e}")
            return {}
        out: Dict[str, str] = {}
        rows = data if isinstance(data, list) else []
        for item in rows:
            if not isinstance(item, dict):
                continue
            code = str(item.get("code") or item.get("hsn_code") or "").replace(" ", "").strip()
            desc = str(item.get("description") or "").strip()
            if not code or not desc:
                continue
            out[code] = desc
            if len(code) == 7:
                out[code.zfill(8)] = desc
            elif len(code) == 5:
                out[code.zfill(6)] = desc
            elif len(code) == 3:
                out[code.zfill(4)] = desc
        return out

    @staticmethod
    def _load_gst_meta_map(path: Path) -> Dict[str, Dict[str, str]]:
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"Failed loading GST rates JSON from {path}: {e}")
            return {}
        out: Dict[str, Dict[str, str]] = {}
        rows = data if isinstance(data, list) else []
        for item in rows:
            if not isinstance(item, dict):
                continue
            code = str(item.get("code") or "").replace(" ", "").strip()
            if not code:
                continue
            meta = {
                "effective_date": str(item.get("effectiveFrom") or "").strip(),
                "notification_ref": str(item.get("notificationRef") or "").strip(),
                "rate_source": str(item.get("rateSource") or "").strip(),
            }
            out[code] = meta
            if len(code) == 7:
                out[code.zfill(8)] = meta
        return out

    @staticmethod
    def _extract_leaf_and_sub6(full_desc: str, h4_desc: str, h6_desc: str) -> tuple[str, str]:
        """Extracts 6-digit subheading and 8-digit leaf clauses from untruncated statutory text."""
        text = full_desc.strip()
        if not text:
            return h6_desc, ""

        # Strip heading prefix if it duplicates h4_desc
        sub_text = text
        if h4_desc and len(text) > len(h4_desc) + 3 and text.upper().startswith(h4_desc.upper()[:40]):
            pass

        # Split hierarchical dash/colon markers (e.g. "HEADING - SUBHEADING : --- LEAF")
        leaf = ""
        if ":" in sub_text:
            leaf = clean_tariff_text(sub_text.split(":")[-1])
        elif " - " in sub_text:
            leaf = clean_tariff_text(sub_text.split(" - ")[-1])
        elif "-" in sub_text:
            leaf = clean_tariff_text(sub_text.split("-")[-1])
        else:
            leaf = clean_tariff_text(sub_text)

        resolved_h6 = h6_desc
        if not resolved_h6 and " - " in sub_text:
            segs = [clean_tariff_text(s) for s in sub_text.split(" - ") if clean_tariff_text(s)]
            if len(segs) >= 2:
                resolved_h6 = segs[1].split(":")[0].strip() if ":" in segs[1] else segs[1]
        return resolved_h6, leaf

    def process(self) -> pd.DataFrame:
        if not self.raw_path.exists():
            raise FileNotFoundError(f"Master file not found at: {self.raw_path}")

        raw_df = pd.read_excel(self.raw_path)
        raw_df["code_str"] = raw_df["HSN Code"].astype(str).str.replace(" ", "").str.strip()
        raw_df["chapter_str"] = raw_df["chapter_code"].astype(str).str.strip().str.zfill(2)

        itc_map = self._load_itc_map(self.itc_json_path)
        gst_meta_map = self._load_gst_meta_map(self.gst_json_path)

        # 1. Build dictionary of 4-digit headings and 6-digit subheadings (restoring untruncated ITC-HS where available)
        heading_4_map: Dict[str, str] = {}
        subheading_6_map: Dict[str, str] = {}

        for _, row in raw_df.iterrows():
            c = row["code_str"]
            raw_d = str(row.get("HSN Description", "")).strip()
            itc_d = itc_map.get(c, "")
            best_d = itc_d if len(itc_d) > len(raw_d) else raw_d
            d = clean_tariff_text(best_d)
            if len(c) == 4:
                heading_4_map[c] = d
            elif len(c) == 6:
                subheading_6_map[c] = d

        # 2. Enrich all records (prioritizing 8-digit tariff items)
        enriched_rows: List[Dict[str, Any]] = []

        for _, row in raw_df.iterrows():
            code = row["code_str"]
            raw_desc = str(row.get("HSN Description", "")).strip()
            itc_desc = itc_map.get(code, "")
            if itc_desc and (len(raw_desc) == 255 or len(itc_desc) > len(raw_desc)):
                statutory_description = itc_desc
                provenance = "Master_copy_hsn.xlsx + itc_hs_codes.json"
            else:
                statutory_description = raw_desc
                provenance = "Master_copy_hsn.xlsx"

            ch_code = row["chapter_str"]
            ch_title = clean_tariff_text(str(row.get("chapter_title", "")))
            art_kws = clean_tariff_text(str(row.get("Article Keywords", "")))
            mat_kws = clean_tariff_text(str(row.get("Material Keywords", "")))

            h4 = code[:4] if len(code) >= 4 else code
            h6 = code[:6] if len(code) >= 6 else code

            h4_desc = heading_4_map.get(h4, "")
            h6_desc = subheading_6_map.get(h6, "")

            if len(code) == 8:
                h6_desc, item_desc = self._extract_leaf_and_sub6(statutory_description, h4_desc, h6_desc)
            else:
                item_desc = clean_tariff_text(statutory_description)

            # Retrieve injected commercial synonyms for 8-digit, 6-digit, and 4-digit codes
            synonyms: List[str] = []
            for k in [code, h6, h4]:
                if k in COMMERCIAL_SYNONYMS_MAP:
                    synonyms.extend(COMMERCIAL_SYNONYMS_MAP[k])
            seen_syn = set()
            unique_synonyms = []
            for s in synonyms:
                s_clean = s.strip().lower()
                if s_clean not in seen_syn:
                    seen_syn.add(s_clean)
                    unique_synonyms.append(s_clean)
            consumer_synonyms_str = ", ".join(unique_synonyms)

            gst_meta = gst_meta_map.get(code, {})
            is_residual = item_desc.strip().upper() in {"OTHER", "OTHERS"}
            is_truncated = len(statutory_description) == 255
            is_incomplete = not bool(statutory_description.strip())

            # Construct comprehensive Search_Index_Text keeping hierarchy levels distinct
            search_parts = [
                f"Chapter {ch_code}: {ch_title}",
                f"Heading {h4}: {h4_desc}" if h4_desc else "",
                f"Subheading {h6}: {h6_desc}" if h6_desc else "",
                f"Tariff Item {code}: {item_desc}" if item_desc else "",
                f"Statutory: {statutory_description}" if statutory_description else "",
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
                "search_index_text": search_index_text,
                "is_residual": is_residual,
                "is_truncated": is_truncated,
                "is_incomplete": is_incomplete,
                "source_provenance": provenance,
                "effective_date": gst_meta.get("effective_date", ""),
                "notification_ref": gst_meta.get("notification_ref", ""),
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


def validate_enriched_master(df: pd.DataFrame) -> Dict[str, Any]:
    """Runs data-quality validation checks on the enriched statutory HSN master."""
    codes = df["hsn_code"].fillna("").astype(str).str.strip()
    leaf_desc = df["tariff_item_desc"].fillna("").astype(str).str.strip()
    stat_desc = df["statutory_description"].fillna("").astype(str).str.strip()
    eff_dates = [d for d in df.get("effective_date", pd.Series(dtype=str)).fillna("").astype(str).unique() if d]
    return {
        "total_rows": int(len(df)),
        "invalid_or_missing_codes": int((~codes.str.match(r"^\d{4,8}$")).sum()),
        "duplicate_codes": int(codes.duplicated().sum()),
        "empty_leaf_descriptions": int((leaf_desc == "").sum()),
        "generic_residual_count": int(leaf_desc.str.upper().isin({"OTHER", "OTHERS"}).sum()),
        "truncated_255_count": int((stat_desc.str.len() == 255).sum()),
        "missing_heading_4digit_desc": int((df["heading_4digit_desc"].fillna("").astype(str).str.strip() == "").sum()),
        "distinct_effective_dates": sorted(eff_dates),
    }

