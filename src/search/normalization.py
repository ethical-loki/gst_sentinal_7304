"""
Layer 1: Complete Statutory Master Data Quality Audit, Normalization & Enrichment
================================================================================
Normalizes and enriches authoritative Indian ITC-HS / CBIC statutory records into
a structured, config-driven schema with:
1. Full statutory coverage across all available HSN Goods chapters (01..98,
   excluding WCO-reserved Chapter 77) plus separate Chapter 99 SAC accounting.
2. Complete Section -> Chapter -> Heading (4d) -> Subheading (6d) -> Tariff Item (8d)
   hierarchy without copying parent headings blindly into leaf descriptions.
3. Authoritative 255-char truncation recovery from untruncated `itc_hs_codes.json`
   and curated `Master_copy_hsn` sources (zero fabricated descriptions).
4. Explicit code-length & parent-child integrity validation and quality flags
   (`is_residual`, `is_truncated`, `is_incomplete`, `missing_parent_heading`,
   `missing_parent_subheading`, `invalid_code_format`, `quality_flags`).
5. Authoritative GST metadata, provenance, publication version, effective dates,
   and honest legal-note coverage tracking (never equating missing notes to "no
   legal restrictions").
6. External JSON source configuration (`data/statutory_master_config.json`) so
   future statutory schedule updates require zero classification-code edits.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_CONFIG_PATH = ROOT_DIR / "data" / "statutory_master_config.json"

# Generic trade abbreviations retained for retrieval normalization only (zero product-to-HSN mappings)
COMMERCIAL_SYNONYMS_MAP: Dict[str, str] = {
    "pvc": "polyvinyl chloride",
    "hdpe": "high density polyethylene",
    "ldpe": "low density polyethylene",
    "lldpe": "linear low density polyethylene",
    "pp": "polypropylene",
    "pet": "polyethylene terephthalate",
    "upvc": "unplasticised polyvinyl chloride",
    "cpvc": "chlorinated polyvinyl chloride",
    "abs": "acrylonitrile butadiene styrene",
    "ptfe": "polytetrafluoroethylene",
    "pu": "polyurethane",
    "gi": "galvanised iron",
    "ms": "mild steel",
    "ss": "stainless steel",
    "ci": "cast iron",
    "smps": "switched mode power supply static converter",
    "led": "light emitting diode",
    "lcd": "liquid crystal display",
    "pcb": "printed circuit board",
    "mcb": "miniature circuit breaker",
    "ups": "uninterruptible power supply static converter",
    "ac": "alternating current",
    "dc": "direct current",
}


def clean_tariff_text(text: Any) -> str:
    """Safely normalizes statutory tariff text without stripping semantic commas or dashes."""
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return ""
    s = str(text).strip()
    if s.lower() in ("nan", "none", "null"):
        return ""
    s = re.sub(r"[\x00-\x1f\x7f-\x9f\u200b-\u200d\ufeff]", " ", s)
    s = re.sub(r"\+L\d+", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _has_alnum(text: str) -> bool:
    return bool(re.search(r"[a-zA-Z0-9]", text or ""))


def _is_residual_clause(text: str) -> bool:
    norm = re.sub(r"[^a-zA-Z0-9\s]", "", (text or "").upper()).strip()
    return norm in ("OTHER", "OTHERS", "ALL OTHER", "OTHER GOODS", "OTHERS NES")


def _strip_leading_dashes(text: str) -> str:
    return re.sub(r"^[-–—:\s]+", "", (text or "").strip()).strip()


def _normalize_for_prefix(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]", " ", (text or "").lower())).strip()


def _resolve_path(base_dir: Path, raw: Optional[str], fallback: Path) -> Path:
    if raw:
        p = Path(raw)
        return p if p.is_absolute() else (base_dir / p)
    return fallback


class MasterHSNEnricher:
    """
    Config-driven Layer 1 statutory master builder & enricher.
    Combines complete CBIC/ITC-HS statutory parquet rows with untruncated
    `itc_hs_codes.json` text, curated `Master_copy_hsn` article/material keywords,
    `gst_rates.json` effective dates/notifications, and digitized Section/Chapter rules.
    """

    def __init__(
        self,
        raw_excel_path: Optional[Path] = None,
        itc_json_path: Optional[Path] = None,
        gst_json_path: Optional[Path] = None,
        config_path: Optional[Path] = None,
        statutory_parquet_path: Optional[Path] = None,
        hierarchy_map_path: Optional[Path] = None,
        legal_notes_path: Optional[Path] = None,
    ):
        self.base_dir = ROOT_DIR
        self.config_path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
        self.config = self._load_config(self.config_path)
        sources = self.config.get("sources", {})

        self.statutory_parquet_path = (
            Path(statutory_parquet_path)
            if statutory_parquet_path
            else _resolve_path(self.base_dir, sources.get("primary_statutory_parquet"), self.base_dir / "data" / "tariff_master.parquet")
        )
        self.hierarchy_map_path = (
            Path(hierarchy_map_path)
            if hierarchy_map_path
            else _resolve_path(self.base_dir, sources.get("hierarchy_map_parquet"), self.base_dir / "data" / "tariff_hierarchy_map.parquet")
        )
        self.raw_parquet_path = _resolve_path(
            self.base_dir, sources.get("keyword_enrichment_parquet"), self.base_dir / "data" / "Master_copy_hsn.parquet"
        )
        self.raw_path = (
            Path(raw_excel_path)
            if raw_excel_path
            else _resolve_path(self.base_dir, sources.get("keyword_enrichment_excel"), self.base_dir / "data" / "raw" / "Master_copy_hsn.xlsx")
        )
        self.itc_json_path = (
            Path(itc_json_path)
            if itc_json_path
            else _resolve_path(self.base_dir, sources.get("itc_untruncated_json"), self.base_dir / "data" / "raw" / "itc_hs_codes.json")
        )
        self.gst_json_path = (
            Path(gst_json_path)
            if gst_json_path
            else _resolve_path(self.base_dir, sources.get("gst_rates_json"), self.base_dir / "data" / "raw" / "gst_rates.json")
        )
        self.legal_notes_path = (
            Path(legal_notes_path)
            if legal_notes_path
            else _resolve_path(self.base_dir, sources.get("legal_notes_json"), self.base_dir / "data" / "statutory_rules.json")
        )
        self.extra_legal_notes_path = _resolve_path(
            self.base_dir, sources.get("extra_legal_notes_json"), self.base_dir / "data" / "statutory_legal_notes.json"
        )

        self.source_authority = str(self.config.get("source_authority") or "CBIC / DGFT ITC-HS & GST Schedule")
        self.publication_version = str(self.config.get("publication_version") or "ITC-HS 2022")
        self.default_effective_date = str(self.config.get("default_effective_date") or "")
        self.default_notification_ref = str(self.config.get("default_notification_ref") or "")

        self.enriched_df: Optional[pd.DataFrame] = None
        self.sac_df: Optional[pd.DataFrame] = None
        self.audit_stats: Dict[str, Any] = {}

    @staticmethod
    def _load_config(config_path: Path) -> Dict[str, Any]:
        if config_path.exists():
            try:
                return json.loads(config_path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"[MasterHSNEnricher] Could not parse config {config_path}: {e}")
        return {}

    @staticmethod
    def _load_itc_map(path: Path) -> Dict[str, str]:
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            out: Dict[str, str] = {}
            for item in data:
                code = str(item.get("code") or "").strip().zfill(8)
                desc = clean_tariff_text(item.get("description") or "")
                if code and desc:
                    out[code] = desc
            return out
        except Exception as e:
            logger.warning(f"[MasterHSNEnricher] Could not load {path}: {e}")
            return {}

    @staticmethod
    def _load_gst_meta_map(path: Path) -> Dict[str, Dict[str, Any]]:
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            out: Dict[str, Dict[str, Any]] = {}
            for item in data:
                code = str(item.get("code") or "").strip().zfill(8)
                if code:
                    out[code] = {
                        "effective_date": str(item.get("effectiveFrom") or ""),
                        "notification_ref": str(item.get("notificationRef") or ""),
                        "igst_rate": item.get("igstRate"),
                        "cgst_rate": item.get("cgstRate"),
                        "sgst_rate": item.get("sgstRate"),
                        "cess_rate": item.get("cessRate"),
                        "gst_rate_source": str(item.get("rateSource") or ""),
                    }
            return out
        except Exception as e:
            logger.warning(f"[MasterHSNEnricher] Could not load {path}: {e}")
            return {}

    def _load_legal_notes_by_chapter(self) -> Dict[str, List[Dict[str, Any]]]:
        """Loads authoritative Section/Chapter rules without inventing unstated chapters."""
        by_ch: Dict[str, List[Dict[str, Any]]] = {}
        files = [self.legal_notes_path]
        if self.extra_legal_notes_path and self.extra_legal_notes_path.exists():
            files.append(self.extra_legal_notes_path)

        for fp in files:
            if not fp or not fp.exists():
                continue
            try:
                raw = json.loads(fp.read_text(encoding="utf-8"))
                entries = raw if isinstance(raw, list) else raw.get("notes", [])
                for item in entries:
                    if not isinstance(item, dict):
                        continue
                    chapters: Set[str] = set()
                    tc = item.get("target_chapter")
                    if tc:
                        chapters.add(str(tc).strip().zfill(2))
                    for m in re.findall(r"\bChapter\s+(\d{1,2})\b", str(item.get("source_note") or ""), flags=re.IGNORECASE):
                        chapters.add(m.zfill(2))
                    for ch_item in item.get("chapters", []) or []:
                        chapters.add(str(ch_item).strip().zfill(2))
                    for ch in chapters:
                        by_ch.setdefault(ch, []).append(item)
            except Exception as e:
                logger.warning(f"[MasterHSNEnricher] Could not load legal notes from {fp}: {e}")
        return by_ch

    def _chapter_to_section(self, ch_code: str) -> Tuple[str, str]:
        ch_num = int(ch_code) if str(ch_code).isdigit() else -1
        for sec in self.config.get("wco_sections", []):
            if sec.get("start", -1) <= ch_num <= sec.get("end", -1):
                return str(sec["section"]), str(sec["title"])
        if ch_num == 99:
            return "SAC", "Services Accounting Code (SAC)"
        if ch_num == 98:
            return "Section XXI-IN", "Special Classification Provisions"
        return "UNKNOWN", ""

    @staticmethod
    def _extract_leaf_and_sub6(full_desc: str, h4_desc: str, h6_desc: str) -> Tuple[str, str]:
        """
        Strips parent 4-digit heading text and separates 6-digit subheading clause from
        8-digit leaf tariff clause without blindly copying parents into leaf records.
        """
        full_clean = clean_tariff_text(full_desc)
        h4_clean = clean_tariff_text(h4_desc)
        h6_clean = clean_tariff_text(h6_desc)

        if not _has_alnum(full_clean):
            return "", h6_clean

        # Handle child-first format occasionally present in tariff_master (`-- LEAF - HEADING...`)
        if re.match(r"^[-–—]+\s*", full_clean) and h4_clean:
            h4_head = h4_clean[:40].upper()
            pos = full_clean.upper().find(h4_head) if len(h4_head) >= 12 else -1
            if pos > 3:
                front_clause = _strip_leading_dashes(full_clean[:pos].rstrip(" -:"))
                if _has_alnum(front_clause):
                    return front_clause, h6_clean

        remainder = full_clean
        if h4_clean:
            norm_full = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]", " ", full_clean.lower())).strip()
            norm_h4 = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]", " ", h4_clean.lower())).strip()
            h4_words = norm_h4.split()
            full_words = norm_full.split()
            match_len = 0
            for w1, w2 in zip(h4_words, full_words):
                if w1 != w2:
                    break
                match_len += 1
            min_match = min(3, len(h4_words)) if h4_words else 0
            if match_len >= min_match and match_len > 0:
                pattern_parts = [re.escape(w) for w in full_words[:match_len]]
                m = re.match(r"^\s*" + r"[^a-zA-Z0-9]*".join(pattern_parts), full_clean, flags=re.IGNORECASE)
                if m:
                    tail = full_clean[m.end():].lstrip()
                    # If parent 4d heading was truncated at 255 chars and full_clean still has the rest of the heading before " - ", skip up to " - "
                    if len(h4_clean) == 255 and not tail.startswith("-") and " - " in tail:
                        tail = tail.split(" - ", 1)[1]
                    candidate_rem = tail.strip(" -:;,)")
                    remainder = candidate_rem if _has_alnum(candidate_rem) else full_clean

        if h6_clean and _has_alnum(h6_clean):
            clean_h6_body = h6_clean
            if h4_clean and len(h4_clean) >= 12:
                extracted_h6, _ = MasterHSNEnricher._extract_leaf_and_sub6(h6_clean, h4_clean, "")
                if _has_alnum(extracted_h6):
                    clean_h6_body = extracted_h6
            if clean_h6_body and remainder.upper().startswith(clean_h6_body.upper()):
                after_h6 = remainder[len(clean_h6_body):]
                if not after_h6 or after_h6[0] in (" ", "-", ":", ";", ","):
                    after_h6_clean = after_h6.strip(" -:;,")
                    if ":" in after_h6_clean:
                        parts = [p.strip() for p in after_h6_clean.split(":") if _has_alnum(p)]
                        if parts:
                            return _strip_leading_dashes(parts[-1]), clean_h6_body
                    if _has_alnum(after_h6_clean):
                        return _strip_leading_dashes(after_h6_clean), clean_h6_body
            if ":" in remainder:
                parts = [p.strip() for p in remainder.split(":") if _has_alnum(p)]
                if len(parts) >= 2:
                    return _strip_leading_dashes(parts[-1]), _strip_leading_dashes(clean_h6_body or parts[0])
            if _has_alnum(remainder):
                return _strip_leading_dashes(remainder), _strip_leading_dashes(clean_h6_body)

        if ":" in remainder:
            parts = [p.strip() for p in remainder.split(":") if _has_alnum(p)]
            if len(parts) >= 2:
                return _strip_leading_dashes(parts[-1]), _strip_leading_dashes(" : ".join(parts[:-1]))

        if " - " in remainder:
            parts = [p.strip() for p in remainder.split(" - ") if _has_alnum(p)]
            if len(parts) >= 2:
                return _strip_leading_dashes(parts[-1]), _strip_leading_dashes(" - ".join(parts[:-1]))

        leaf = _strip_leading_dashes(remainder if _has_alnum(remainder) else full_clean)
        sub6_out = _strip_leading_dashes(h6_clean) if _has_alnum(h6_clean) else ""
        return leaf, sub6_out

    @staticmethod
    def _recover_4d_heading_from_children(
        h4_code: str, raw_h4_desc: str, itc_by_4d: Dict[str, List[str]]
    ) -> str:
        """
        Safely recovers an Excel-truncated 255-char 4-digit heading ONLY when matching
        untruncated ITC-HS 8-digit children share the exact unambiguous heading stem.
        """
        if len(raw_h4_desc) != 255:
            return raw_h4_desc
        pref = _normalize_for_prefix(raw_h4_desc[:220])
        if len(pref) < 40:
            return raw_h4_desc
        children = itc_by_4d.get(h4_code, [])
        if not children:
            return raw_h4_desc

        stems: Set[str] = set()
        for child_desc in children:
            if len(child_desc) <= 255:
                continue
            if not _normalize_for_prefix(child_desc[:260]).startswith(pref):
                continue
            tail_window = child_desc[235:]
            cut_idx = len(child_desc)
            for sep in (" - ", " : ", " -- ", "---"):
                pos = tail_window.find(sep)
                if pos != -1:
                    cut_idx = min(cut_idx, 235 + pos)
            candidate_stem = child_desc[:cut_idx].strip(" -:")
            if len(candidate_stem) > 255:
                stems.add(candidate_stem)
        if len(stems) == 1:
            return next(iter(stems))
        return raw_h4_desc

    def _load_curated_keyword_map(self) -> Dict[str, Dict[str, str]]:
        """Loads curated descriptions + article/material keywords from Master_copy_hsn."""
        df_mc: Optional[pd.DataFrame] = None
        if self.raw_parquet_path.exists():
            df_mc = pd.read_parquet(self.raw_parquet_path)
        elif self.raw_path.exists():
            df_mc = pd.read_excel(self.raw_path)

        out: Dict[str, Dict[str, str]] = {}
        if df_mc is None or df_mc.empty:
            return out

        for _, r in df_mc.iterrows():
            c = str(r.get("HSN Code") or "").strip()
            if not c:
                continue
            out[c] = {
                "chapter_title": clean_tariff_text(r.get("chapter_title") or ""),
                "hsn_desc": clean_tariff_text(r.get("HSN Description") or ""),
                "article_keywords": clean_tariff_text(r.get("Article Keywords") or ""),
                "material_keywords": clean_tariff_text(r.get("Material Keywords") or ""),
            }
        return out

    def _load_chapter_titles_from_hierarchy_map(self) -> Dict[str, str]:
        titles: Dict[str, str] = {}
        if not self.hierarchy_map_path.exists():
            return titles
        try:
            hm = pd.read_parquet(self.hierarchy_map_path, columns=["chapter", "search_text"])
            for _, r in hm.drop_duplicates("chapter").iterrows():
                ch = str(r["chapter"]).strip().zfill(2)
                st = str(r["search_text"] or "")
                first_seg = st.split("|")[0].strip() if "|" in st else st.strip()
                first_seg = re.sub(rf"^Chapter\s+{re.escape(ch)}\s*-\s*", "", first_seg, flags=re.IGNORECASE)
                if first_seg:
                    titles[ch] = clean_tariff_text(first_seg)
        except Exception as e:
            logger.warning(f"[MasterHSNEnricher] Could not read chapter titles from {self.hierarchy_map_path}: {e}")
        return titles

    def process(self) -> pd.DataFrame:
        itc_map = self._load_itc_map(self.itc_json_path)
        gst_meta_map = self._load_gst_meta_map(self.gst_json_path)
        legal_notes_by_ch = self._load_legal_notes_by_chapter()
        curated_map = self._load_curated_keyword_map()
        hm_titles = self._load_chapter_titles_from_hierarchy_map()

        itc_by_4d: Dict[str, List[str]] = {}
        for c, desc in itc_map.items():
            if _has_alnum(desc):
                itc_by_4d.setdefault(c[:4], []).append(desc)

        raw_records: List[Dict[str, Any]] = []
        seen_codes: Set[str] = set()
        duplicate_codes: Set[str] = set()

        # 1. Primary 98-chapter statutory source (`tariff_master.parquet`)
        if self.statutory_parquet_path.exists():
            tm = pd.read_parquet(self.statutory_parquet_path)
            for _, r in tm.iterrows():
                code = str(r.get("hsn_code") or "").strip()
                if not code:
                    continue
                if code in seen_codes:
                    duplicate_codes.add(code)
                    continue
                seen_codes.add(code)
                raw_records.append({
                    "hsn_code": code,
                    "chapter_code": str(r.get("chapter") or code[:2]).strip().zfill(2),
                    "tm_desc": clean_tariff_text(r.get("description") or r.get("hsn_description") or ""),
                    "effective_date": str(r.get("effective_date") or "").strip(),
                    "is_blocked_17_5": int(r.get("is_blocked_17_5") or 0),
                    "blocked_17_5_reason": clean_tariff_text(r.get("blocked_17_5_reason") or ""),
                    "from_tm": True,
                    "from_itc_only": False,
                })
        else:
            # Fallback if parquet unavailable: load curated Master_copy_hsn
            for code, meta in curated_map.items():
                raw_records.append({
                    "hsn_code": code,
                    "chapter_code": code[:2].zfill(2),
                    "tm_desc": meta["hsn_desc"],
                    "effective_date": self.default_effective_date,
                    "is_blocked_17_5": 0,
                    "blocked_17_5_reason": "",
                    "from_tm": False,
                    "from_itc_only": False,
                })
                seen_codes.add(code)

        # 2. Import additional authoritative 8-digit records from `itc_hs_codes.json` not in primary parquet
        for code, desc in sorted(itc_map.items()):
            if code not in seen_codes:
                seen_codes.add(code)
                raw_records.append({
                    "hsn_code": code,
                    "chapter_code": code[:2].zfill(2),
                    "tm_desc": desc if _has_alnum(desc) else "",
                    "effective_date": self.default_effective_date,
                    "is_blocked_17_5": 0,
                    "blocked_17_5_reason": "",
                    "from_tm": False,
                    "from_itc_only": True,
                })

        # 3. Also ensure any code only in curated Master_copy_hsn is preserved
        for code, meta in curated_map.items():
            if code not in seen_codes:
                seen_codes.add(code)
                raw_records.append({
                    "hsn_code": code,
                    "chapter_code": code[:2].zfill(2),
                    "tm_desc": meta["hsn_desc"],
                    "effective_date": self.default_effective_date,
                    "is_blocked_17_5": 0,
                    "blocked_17_5_reason": "",
                    "from_tm": False,
                    "from_itc_only": False,
                })

        sac_chapters = set(self.config.get("sac_service_chapters", ["99"]))
        special_chapters = set(self.config.get("special_provision_chapters", ["98"]))

        # Index best raw description per 4d and 6d code for parent-child resolution
        raw_desc_by_code: Dict[str, Tuple[str, str]] = {}
        for rec in raw_records:
            c = rec["hsn_code"]
            cur = curated_map.get(c, {})
            base_desc = rec["tm_desc"]
            cur_desc = cur.get("hsn_desc", "")
            provenance = "tariff_master.parquet" if rec["from_tm"] else "itc_hs_codes.json"

            if c in curated_map and _has_alnum(cur_desc):
                if len(base_desc) == 255 and len(cur_desc) != 255:
                    base_desc = cur_desc
                    provenance = "Master_copy_hsn"
                elif not _has_alnum(base_desc):
                    base_desc = cur_desc
                    provenance = "Master_copy_hsn"
                elif not rec["tm_desc"].startswith("-") and len(cur_desc) >= len(base_desc):
                    base_desc = cur_desc
                    provenance = "Master_copy_hsn"

            if len(c) == 8 and c in itc_map and _has_alnum(itc_map[c]) and len(itc_map[c]) != 255:
                base_desc = itc_map[c]
                provenance = (
                    "Master_copy_hsn + itc_hs_codes.json"
                    if c in curated_map
                    else "tariff_master.parquet + itc_hs_codes.json"
                )
            elif len(c) == 8 and c in itc_map and _has_alnum(itc_map[c]) and (
                not _has_alnum(base_desc) or base_desc.startswith("-")
            ):
                base_desc = itc_map[c]
                provenance = "tariff_master.parquet + itc_hs_codes.json"
            elif len(c) == 4 and len(base_desc) == 255:
                recovered = self._recover_4d_heading_from_children(c, base_desc, itc_by_4d)
                if len(recovered) > 255:
                    base_desc = recovered
                    provenance = "tariff_master.parquet + itc_hs_codes.json"

            raw_desc_by_code[c] = (base_desc, provenance)

        all_codes = set(raw_desc_by_code.keys())
        rows: List[Dict[str, Any]] = []
        sac_rows: List[Dict[str, Any]] = []

        for rec in sorted(raw_records, key=lambda x: x["hsn_code"]):
            hsn_code = rec["hsn_code"]
            ch_code = rec["chapter_code"]
            code_len = len(hsn_code)
            invalid_code_format = (not hsn_code.isdigit()) or (code_len not in (4, 6, 8))

            sec_code, sec_title = self._chapter_to_section(ch_code)
            if ch_code in sac_chapters:
                tariff_schedule = "SAC_SERVICES"
            elif ch_code in special_chapters:
                tariff_schedule = "SPECIAL_PROVISIONS"
            else:
                tariff_schedule = "HSN_GOODS"

            cur = curated_map.get(hsn_code, {})
            ch_title = hm_titles.get(ch_code) or cur.get("chapter_title") or f"Chapter {ch_code}"

            full_desc, provenance = raw_desc_by_code[hsn_code]
            h4 = hsn_code[:4] if code_len >= 4 else ""
            h6 = hsn_code[:6] if code_len >= 6 else (h4 if code_len == 4 else "")
            h8 = hsn_code if code_len == 8 else ""

            missing_parent_heading = (code_len >= 6) and (h4 not in all_codes)
            missing_parent_subheading = (code_len == 8) and (h6 not in all_codes)

            h4_desc = raw_desc_by_code.get(h4, ("", ""))[0] if h4 else ""
            h6_raw_desc = raw_desc_by_code.get(h6, ("", ""))[0] if (code_len == 8 and h6 in raw_desc_by_code) else ""

            if code_len == 4:
                leaf_desc = full_desc
                sub6_desc = ""
                parent_code = ""
            elif code_len == 6:
                leaf_desc, sub6_parsed = self._extract_leaf_and_sub6(full_desc, h4_desc, "")
                if not leaf_desc and _has_alnum(full_desc):
                    leaf_desc = full_desc
                sub6_desc = leaf_desc
                parent_code = h4
            else:
                leaf_desc, sub6_desc = self._extract_leaf_and_sub6(full_desc, h4_desc, h6_raw_desc)
                parent_code = h6 if not missing_parent_subheading else h4

            is_residual = bool(code_len >= 6 and _is_residual_clause(leaf_desc))
            is_truncated = bool(len(full_desc) == 255)
            parent_heading_truncated = bool(len(h4_desc) == 255)
            missing_desc = not _has_alnum(full_desc)
            is_incomplete = bool(invalid_code_format or missing_desc or missing_parent_heading or is_truncated)

            gst_meta = gst_meta_map.get(h8 or hsn_code, {})
            effective_date = str(gst_meta.get("effective_date") or rec.get("effective_date") or self.default_effective_date or "")
            notification_ref = str(gst_meta.get("notification_ref") or self.default_notification_ref or "")

            ch_rules = legal_notes_by_ch.get(ch_code, [])
            legal_notes_count = len(ch_rules)
            legal_note_ids = "; ".join(str(r.get("rule_id") or "") for r in ch_rules if r.get("rule_id"))
            legal_note_status = (
                "PARTIAL_AUTHORITATIVE_NOTES_LOADED"
                if legal_notes_count > 0
                else "NO_AUTHORITATIVE_NOTES_LOADED"
            )

            flags: List[str] = []
            if is_truncated:
                flags.append("TRUNCATED_255")
            if parent_heading_truncated and code_len >= 6:
                flags.append("TRUNCATED_PARENT_HEADING")
            if is_residual:
                flags.append("RESIDUAL_OTHER")
            if missing_desc:
                flags.append("MISSING_DESCRIPTION")
            if missing_parent_heading:
                flags.append("MISSING_PARENT_HEADING")
            if missing_parent_subheading:
                flags.append("MISSING_PARENT_SUBHEADING")
            if invalid_code_format:
                flags.append("INVALID_CODE_FORMAT")
            if legal_notes_count == 0:
                flags.append("MISSING_LEGAL_NOTES")
            quality_flags = "|".join(flags) if flags else "CLEAN"

            art_kw = cur.get("article_keywords", "")
            mat_kw = cur.get("material_keywords", "")

            index_parts = [f"Section {sec_code}: {sec_title}" if sec_title else "", f"Chapter {ch_code}: {ch_title}"]
            if h4_desc:
                index_parts.append(f"Heading {h4}: {h4_desc}")
            if sub6_desc and h6 and code_len >= 6:
                index_parts.append(f"Subheading {h6}: {sub6_desc}")
            index_parts.append(f"Tariff Item {hsn_code}: {leaf_desc}")
            index_parts.append(f"Statutory: {full_desc}")
            if art_kw:
                index_parts.append(f"Articles: {art_kw}")
            if mat_kw:
                index_parts.append(f"Materials: {mat_kw}")

            row_dict = {
                "hsn_code": hsn_code,
                "code_length": int(code_len),
                "section_code": sec_code,
                "section_title": sec_title,
                "chapter_code": ch_code,
                "chapter_title": ch_title,
                "tariff_schedule": tariff_schedule,
                "parent_code": parent_code,
                "heading_4digit": h4,
                "heading_4digit_desc": h4_desc,
                "subheading_6digit": h6,
                "subheading_6digit_desc": sub6_desc,
                "tariff_item_8digit": h8 if h8 else None,
                "tariff_item_desc": leaf_desc,
                "statutory_description": full_desc,
                "consumer_synonyms": "",
                "article_keywords": art_kw,
                "material_keywords": mat_kw,
                "search_index_text": " | ".join(p for p in index_parts if p),
                "is_residual": bool(is_residual),
                "is_truncated": bool(is_truncated),
                "is_incomplete": bool(is_incomplete),
                "missing_parent_heading": bool(missing_parent_heading),
                "missing_parent_subheading": bool(missing_parent_subheading),
                "invalid_code_format": bool(invalid_code_format),
                "duplicate_code_in_sources": hsn_code in duplicate_codes,
                "quality_flags": quality_flags,
                "source_provenance": provenance,
                "source_authority": self.source_authority,
                "publication_version": self.publication_version,
                "effective_date": effective_date,
                "notification_ref": notification_ref,
                "igst_rate": float(gst_meta["igst_rate"]) if gst_meta.get("igst_rate") is not None else None,
                "cgst_rate": float(gst_meta["cgst_rate"]) if gst_meta.get("cgst_rate") is not None else None,
                "sgst_rate": float(gst_meta["sgst_rate"]) if gst_meta.get("sgst_rate") is not None else None,
                "cess_rate": float(gst_meta["cess_rate"]) if gst_meta.get("cess_rate") is not None else None,
                "gst_rate_source": str(gst_meta.get("gst_rate_source") or ""),
                "is_blocked_17_5": int(rec.get("is_blocked_17_5") or 0),
                "blocked_17_5_reason": str(rec.get("blocked_17_5_reason") or ""),
                "legal_notes_count": int(legal_notes_count),
                "legal_note_ids": legal_note_ids,
                "legal_note_coverage_status": legal_note_status,
            }
            if tariff_schedule == "SAC_SERVICES":
                sac_rows.append(row_dict)
            else:
                rows.append(row_dict)

        self.enriched_df = pd.DataFrame(rows)
        self.sac_df = pd.DataFrame(sac_rows)
        self.audit_stats = {
            "duplicate_codes_in_sources": sorted(duplicate_codes),
            "sac_rows_count": len(self.sac_df),
        }
        logger.info(
            f"[MasterHSNEnricher] Built HSN master ({len(self.enriched_df)} rows across "
            f"{self.enriched_df['chapter_code'].nunique()} goods chapters) + SAC master ({len(self.sac_df)} rows)."
        )
        return self.enriched_df

    def save(self, output_parquet_path: Optional[Path] = None) -> Path:
        if self.enriched_df is None:
            self.process()
        outputs = self.config.get("outputs", {})
        out_path = (
            Path(output_parquet_path)
            if output_parquet_path
            else _resolve_path(self.base_dir, outputs.get("enriched_hsn_parquet"), self.base_dir / "data" / "enriched_master_hsn.parquet")
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        assert self.enriched_df is not None
        self.enriched_df.to_parquet(out_path, index=False)

        if self.sac_df is not None and not self.sac_df.empty and output_parquet_path is None:
            sac_path = _resolve_path(
                self.base_dir, outputs.get("enriched_sac_parquet"), self.base_dir / "data" / "enriched_sac_master.parquet"
            )
            sac_path.parent.mkdir(parents=True, exist_ok=True)
            self.sac_df.to_parquet(sac_path, index=False)
        return out_path

    def write_coverage_report(
        self,
        json_path: Optional[Path] = None,
        md_path: Optional[Path] = None,
    ) -> Tuple[Path, Path]:
        if self.enriched_df is None:
            self.process()
        assert self.enriched_df is not None
        outputs = self.config.get("outputs", {})
        out_json = (
            Path(json_path)
            if json_path
            else _resolve_path(self.base_dir, outputs.get("coverage_report_json"), self.base_dir / "reports" / "phase1_statutory_master_coverage_report.json")
        )
        out_md = (
            Path(md_path)
            if md_path
            else _resolve_path(self.base_dir, outputs.get("coverage_report_md"), self.base_dir / "reports" / "phase1_statutory_master_coverage_report.md")
        )
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_md.parent.mkdir(parents=True, exist_ok=True)

        report = validate_enriched_master(self.enriched_df, sac_df=self.sac_df)
        out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")

        lines: List[str] = [
            "# Phase 1 — Statutory Master Coverage & Data Quality Report",
            "",
            f"- **Source Authority:** {report.get('source_authority')}",
            f"- **Publication Version:** {report.get('publication_version')}",
            f"- **Distinct Effective Dates:** {', '.join(report.get('distinct_effective_dates', []))}",
            f"- **Total Goods HSN Records:** {report['total_rows']} across {report['distinct_chapters']} chapters (Chapters 01–98; WCO-reserved Chapter 77 empty)",
            f"- **Total SAC Service Records (Chapter 99, separated):** {report['sac_total_rows']}",
            f"- **Invalid/Corrupted Format Codes:** {report['invalid_or_missing_codes']}",
            f"- **Duplicate Codes After Deduplication:** {report['duplicate_codes']}",
            f"- **Missing Statutory Descriptions:** {report['missing_statutory_descriptions']}",
            f"- **Remaining Truncated (255-char) Statutory Descriptions:** {report['truncated_255_count']}",
            f"- **Missing 4-digit Parent Heading Rows:** {report['missing_parent_heading_count']}",
            f"- **Direct-to-8d Rows Without Explicit 6-digit Row:** {report['missing_parent_subheading_count']}",
            f"- **Incomplete Records (flagged explicitly, never fabricated):** {report['incomplete_count']}",
            f"- **Residual (`OTHER`) Leaf Records:** {report['residual_other_count']}",
            f"- **Legal-Note Coverage:** {report['chapters_with_legal_notes']} / {report['distinct_chapters']} goods chapters have partial digitized rules loaded (`data/statutory_rules.json`); {report['chapters_without_legal_notes']} chapters are explicitly flagged `NO_AUTHORITATIVE_NOTES_LOADED`.",
            "",
            "## Chapter-Wise Coverage Table",
            "",
            "| Ch | Sec | Schedule | Total | 4d | 6d | 8d | Missing Desc | Trunc 255 | Missing 4d Parent | Incomplete | Residual | Notes Count | Note Status |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
        for row in report.get("chapter_breakdown", []):
            lines.append(
                f"| {row['chapter_code']} | {row['section_code']} | {row['tariff_schedule']} | "
                f"{row['total_rows']} | {row['count_4d']} | {row['count_6d']} | {row['count_8d']} | "
                f"{row['missing_desc_count']} | {row['truncated_255_count']} | "
                f"{row['missing_parent_heading_count']} | {row['incomplete_count']} | "
                f"{row['residual_count']} | {row['legal_notes_count']} | {row['legal_note_coverage_status']} |"
            )
        out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return out_json, out_md


def validate_enriched_master(df: pd.DataFrame, sac_df: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
    """Computes complete statutory coverage and data-quality audit metrics."""
    if df is None or df.empty:
        return {"total_rows": 0, "distinct_chapters": 0}

    codes = df["hsn_code"].astype(str).str.strip()
    stat_desc = df["statutory_description"].fillna("").astype(str)
    missing_desc_mask = ~stat_desc.apply(_has_alnum)
    invalid_codes = int((~codes.str.isdigit()).sum() + (~df["code_length"].isin([4, 6, 8])).sum())
    dup_codes = int(codes.duplicated().sum())
    trunc_255 = int((stat_desc.str.len() == 255).sum())

    missing_p4 = int(df["missing_parent_heading"].sum()) if "missing_parent_heading" in df.columns else 0
    missing_p6 = int(df["missing_parent_subheading"].sum()) if "missing_parent_subheading" in df.columns else 0
    incomplete_cnt = int(df["is_incomplete"].sum()) if "is_incomplete" in df.columns else 0
    residual_cnt = int(df["is_residual"].sum()) if "is_residual" in df.columns else 0

    ch_col = df["chapter_code"].astype(str).str.strip().str.zfill(2)
    distinct_dates = sorted({str(d).strip() for d in df.get("effective_date", pd.Series(dtype=str)).dropna() if str(d).strip()})
    authorities = sorted({str(a).strip() for a in df.get("source_authority", pd.Series(dtype=str)).dropna() if str(a).strip()})
    versions = sorted({str(v).strip() for v in df.get("publication_version", pd.Series(dtype=str)).dropna() if str(v).strip()})

    all_dfs = [df]
    if sac_df is not None and not sac_df.empty:
        all_dfs.append(sac_df)
    combined = pd.concat(all_dfs, ignore_index=True)

    chapter_breakdown: List[Dict[str, Any]] = []
    for ch, grp in combined.groupby(combined["chapter_code"].astype(str).str.strip().str.zfill(2)):
        g_desc = grp["statutory_description"].fillna("").astype(str)
        chapter_breakdown.append({
            "chapter_code": ch,
            "section_code": str(grp["section_code"].iloc[0]) if "section_code" in grp.columns else "",
            "chapter_title": str(grp["chapter_title"].iloc[0]) if "chapter_title" in grp.columns else "",
            "tariff_schedule": str(grp["tariff_schedule"].iloc[0]) if "tariff_schedule" in grp.columns else "HSN_GOODS",
            "total_rows": int(len(grp)),
            "count_4d": int((grp["code_length"] == 4).sum()),
            "count_6d": int((grp["code_length"] == 6).sum()),
            "count_8d": int((grp["code_length"] == 8).sum()),
            "missing_desc_count": int((~g_desc.apply(_has_alnum)).sum()),
            "truncated_255_count": int((g_desc.str.len() == 255).sum()),
            "missing_parent_heading_count": int(grp["missing_parent_heading"].sum()) if "missing_parent_heading" in grp.columns else 0,
            "incomplete_count": int(grp["is_incomplete"].sum()) if "is_incomplete" in grp.columns else 0,
            "residual_count": int(grp["is_residual"].sum()) if "is_residual" in grp.columns else 0,
            "legal_notes_count": int(grp["legal_notes_count"].max()) if "legal_notes_count" in grp.columns else 0,
            "legal_note_coverage_status": (
                str(grp["legal_note_coverage_status"].iloc[0])
                if "legal_note_coverage_status" in grp.columns
                else "NO_AUTHORITATIVE_NOTES_LOADED"
            ),
        })
    chapter_breakdown.sort(key=lambda r: r["chapter_code"])

    chapters_with_notes = sum(1 for r in chapter_breakdown if r["tariff_schedule"] != "SAC_SERVICES" and r["legal_notes_count"] > 0)
    goods_chapters_count = int(ch_col.nunique())

    return {
        "total_rows": int(len(df)),
        "sac_total_rows": int(len(sac_df)) if sac_df is not None else 0,
        "distinct_chapters": goods_chapters_count,
        "wco_reserved_empty_chapters": ["77"],
        "invalid_or_missing_codes": invalid_codes,
        "duplicate_codes": dup_codes,
        "missing_statutory_descriptions": int(missing_desc_mask.sum()),
        "truncated_255_count": trunc_255,
        "missing_parent_heading_count": missing_p4,
        "missing_parent_subheading_count": missing_p6,
        "incomplete_count": incomplete_cnt,
        "residual_other_count": residual_cnt,
        "chapters_with_legal_notes": int(chapters_with_notes),
        "chapters_without_legal_notes": int(goods_chapters_count - chapters_with_notes),
        "distinct_effective_dates": distinct_dates,
        "source_authority": authorities[0] if authorities else "",
        "publication_version": versions[0] if versions else "",
        "chapter_breakdown": chapter_breakdown,
    }
