"""
Rate Slab Checker for Indian GST.
Cross-verifies declared invoice tax rates against statutory CBIC tariff rates (data/tariff_master.parquet).
Flags RATE_SLAB_MISMATCH whenever |declared_rate - statutory_rate| > 0.5%.
"""

import os
import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
TARIFF_PARQUET_PRIMARY = ROOT_DIR / "data" / "tariff_master.parquet"
TARIFF_PARQUET_FALLBACK = ROOT_DIR / "data" / "raw" / "tariff_master.parquet"

KNOWN_HSN_TITLES: Dict[str, str] = {
    "8703": "Motor cars & passenger vehicles",
    "8702": "Motor vehicles for transport of ten or more persons",
    "8708": "Parts and accessories of motor vehicles",
    "8471": "Automatic data processing machines & computers",
    "8517": "Telephone sets & smartphones",
    "9983": "Other professional, technical and business services",
    "9963": "Accommodation, food and beverage services",
    "1001": "Wheat and meslin",
    "1701": "Cane or beet sugar",
}

_TARIFF_CACHE: Optional[Dict[str, Tuple[float, str]]] = None


def _load_tariff_rates() -> Dict[str, Tuple[float, str]]:
    """
    Loads tariff master into an in-memory dictionary mapping sanitized HSN -> (standard_rate, description).
    """
    global _TARIFF_CACHE
    if _TARIFF_CACHE is not None:
        return _TARIFF_CACHE

    parquet_path = TARIFF_PARQUET_PRIMARY if TARIFF_PARQUET_PRIMARY.exists() else TARIFF_PARQUET_FALLBACK
    rates_map: Dict[str, Tuple[float, str]] = {}

    if parquet_path.exists():
        try:
            df = pd.read_parquet(parquet_path)
            hsn_col = "hsn_code" if "hsn_code" in df.columns else ("HSN_CD" if "HSN_CD" in df.columns else None)
            rate_col = "standard_rate" if "standard_rate" in df.columns else ("gst_rate" if "gst_rate" in df.columns else None)
            desc_col = "description" if "description" in df.columns else ("HSN_Description" if "HSN_Description" in df.columns else None)

            if hsn_col and rate_col:
                for _, row in df.iterrows():
                    code = str(row[hsn_col]).strip()
                    clean_code = re.sub(r"\D", "", code)
                    if not clean_code:
                        continue
                    try:
                        rate_val = float(row[rate_col])
                    except (ValueError, TypeError):
                        rate_val = 18.0
                    raw_desc = str(row.get(desc_col, "") or "") if desc_col else ""
                    rates_map[clean_code] = (rate_val, raw_desc)
                    # Also map original formatted code if different
                    if code != clean_code:
                        rates_map[code] = (rate_val, raw_desc)
        except Exception as ex:
            print(f"[WARN] Failed to load tariff master parquet: {ex}")

    _TARIFF_CACHE = rates_map
    return _TARIFF_CACHE


def _get_hsn_title(clean_hsn: str, raw_desc: str) -> str:
    """Returns a clean concise title for the HSN code."""
    if clean_hsn in KNOWN_HSN_TITLES:
        return KNOWN_HSN_TITLES[clean_hsn]
    if len(clean_hsn) >= 4 and clean_hsn[:4] in KNOWN_HSN_TITLES:
        return KNOWN_HSN_TITLES[clean_hsn[:4]]

    if not raw_desc:
        return ""

    # Clean description: strip "Heading \d+ - " or similar
    cleaned = re.sub(r"^Heading\s+\d+\s*[-:]\s*", "", raw_desc, flags=re.IGNORECASE).strip()
    if not cleaned:
        return ""
    # Capitalize cleanly if all uppercase
    if cleaned.isupper():
        cleaned = cleaned.title()
    # Truncate if too long
    if len(cleaned) > 40:
        cleaned = cleaned[:37] + "..."
    return cleaned


class RateSlabChecker:
    """
    Validates declared GST rates against the statutory tariff rate for an HSN code.
    Tolerance: 0.5% (to accommodate standard rounding differences).
    """

    def __init__(self, tolerance: float = 0.5):
        self.tolerance = tolerance

    def lookup_statutory_rate(self, resolved_hsn: Optional[Union[str, int]]) -> Tuple[Optional[float], str]:
        """
        Looks up standard statutory GST rate and description for the given HSN code.
        Tries exact code, then 6-digit prefix, then 4-digit heading.
        """
        if not resolved_hsn:
            return None, ""

        clean_hsn = re.sub(r"\D", "", str(resolved_hsn).strip())
        if not clean_hsn:
            return None, ""

        tariff_map = _load_tariff_rates()

        # 1. Exact match
        if clean_hsn in tariff_map:
            return tariff_map[clean_hsn]

        # 2. 6-digit prefix
        if len(clean_hsn) >= 6 and clean_hsn[:6] in tariff_map:
            return tariff_map[clean_hsn[:6]]

        # 3. 4-digit heading match
        if len(clean_hsn) >= 4 and clean_hsn[:4] in tariff_map:
            return tariff_map[clean_hsn[:4]]

        # 4. 2-digit chapter fallback (if available)
        if len(clean_hsn) >= 2 and clean_hsn[:2] in tariff_map:
            return tariff_map[clean_hsn[:2]]

        return None, ""

    def check(
        self,
        declared_rate: Optional[Union[float, int, str]],
        resolved_hsn: Optional[Union[str, int]],
    ) -> Dict[str, Any]:
        """
        Checks declared_rate against statutory rate for resolved_hsn.
        Returns a structured dict with verification details and flags.
        """
        # Handle missing HSN
        if not resolved_hsn or not str(resolved_hsn).strip():
            return {
                "flag": None,
                "hsn": "",
                "declared_rate": float(declared_rate) if declared_rate is not None and str(declared_rate).strip() != "" else None,
                "statutory_rate": None,
                "difference": 0.0,
                "severity": "LOW",
                "message": "HSN code is missing; skipping rate slab verification.",
            }

        clean_hsn = re.sub(r"\D", "", str(resolved_hsn).strip())
        statutory_rate, raw_desc = self.lookup_statutory_rate(clean_hsn)
        desc_title = _get_hsn_title(clean_hsn, raw_desc)

        # Handle missing or blank declared rate
        if declared_rate is None or (isinstance(declared_rate, str) and not declared_rate.strip()):
            return {
                "flag": None,
                "hsn": clean_hsn,
                "declared_rate": None,
                "statutory_rate": statutory_rate,
                "difference": 0.0,
                "severity": "LOW",
                "message": "Declared rate is missing or empty; skipping rate slab verification.",
            }

        try:
            dec_rate_float = float(declared_rate)
        except (ValueError, TypeError):
            return {
                "flag": None,
                "hsn": clean_hsn,
                "declared_rate": None,
                "statutory_rate": statutory_rate,
                "difference": 0.0,
                "severity": "LOW",
                "message": f"Invalid declared rate format '{declared_rate}'.",
            }

        # If HSN is unknown in statutory tariff master
        if statutory_rate is None:
            return {
                "flag": None,
                "hsn": clean_hsn,
                "declared_rate": dec_rate_float,
                "statutory_rate": None,
                "difference": 0.0,
                "severity": "LOW",
                "message": f"HSN {clean_hsn} not found in statutory tariff master; rate check skipped.",
            }

        difference = round(abs(dec_rate_float - statutory_rate), 4)

        if difference > self.tolerance:
            desc_part = f" ({desc_title})" if desc_title else ""
            msg = (
                f"Declared GST rate {dec_rate_float:g}% does not match statutory rate "
                f"{statutory_rate:g}% for HSN {clean_hsn}{desc_part}"
            )
            return {
                "flag": "RATE_SLAB_MISMATCH",
                "hsn": clean_hsn,
                "declared_rate": dec_rate_float,
                "statutory_rate": statutory_rate,
                "difference": difference,
                "severity": "CRITICAL",
                "message": msg,
            }

        # Rate matches within tolerance
        desc_part = f" ({desc_title})" if desc_title else ""
        return {
            "flag": None,
            "hsn": clean_hsn,
            "declared_rate": dec_rate_float,
            "statutory_rate": statutory_rate,
            "difference": difference,
            "severity": "LOW",
            "message": f"Declared GST rate {dec_rate_float:g}% matches statutory rate {statutory_rate:g}% for HSN {clean_hsn}{desc_part}",
        }


# Global singleton instance
rate_slab_checker = RateSlabChecker()


def check_rate_slab(
    declared_rate: Optional[Union[float, int, str]],
    resolved_hsn: Optional[Union[str, int]],
    tolerance: float = 0.5,
) -> Dict[str, Any]:
    """Convenience functional interface for rate slab checking."""
    checker = rate_slab_checker if tolerance == 0.5 else RateSlabChecker(tolerance=tolerance)
    return checker.check(declared_rate, resolved_hsn)


def check(
    declared_rate: Optional[Union[float, int, str]],
    resolved_hsn: Optional[Union[str, int]],
) -> Dict[str, Any]:
    """Module-level alias for rate_slab_checker.check(...)."""
    return rate_slab_checker.check(declared_rate, resolved_hsn)
