"""
Statutory Rules Engine & Modulo-36 GSTIN Checksum Validation.
Implements deterministic statutory validation rules (RULE_01 through RULE_04):
- RULE_01: Mandatory Field Integrity
- RULE_02: Place of Supply (POS) Interstate / Intra-state Mismatch
- RULE_03: Tax Rate Arithmetic Variance Threshold (₹0.05)
- RULE_04: Modulo-36 GSTIN Checksum Verification
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml
except ImportError:
    yaml = None

CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
CHAR_MAP = {c: i for i, c in enumerate(CHARS)}


def calculate_gstin_checksum(gstin14: str) -> str:
    """Calculates official GSTN Modulo-36 Checksum for first 14 characters."""
    if not gstin14 or len(gstin14) < 14:
        return ""
    clean = gstin14[:14].upper()
    total = 0
    for idx in range(14):
        val = CHAR_MAP.get(clean[idx])
        if val is None:
            return ""
        factor = 2 if (idx % 2 == 1) else 1
        prod = val * factor
        total += (prod // 36) + (prod % 36)
    check_val = (36 - (total % 36)) % 36
    return CHARS[check_val]


def verify_gstin_checksum(gstin: str) -> bool:
    """Validates 15-character GSTIN against official GSTN Modulo-36 check character."""
    if not gstin or not isinstance(gstin, str):
        return False
    clean = gstin.strip().upper()
    if len(clean) != 15:
        return False
    expected = calculate_gstin_checksum(clean[:14])
    return expected == clean[14]


class StatutoryRulesEngine:
    """High-speed deterministic statutory rules engine for GST invoice and line-item validation."""

    DEFAULT_MANDATORY_FIELDS = [
        "invoice_id",
        "line_item_id",
        "supplier_gstin",
        "recipient_gstin",
        "supplier_state",
        "declared_pos",
        "declared_hsn",
        "quantity",
        "item_taxable_value",
        "declared_effective_rate",
    ]

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path
        self.mandatory_fields = list(self.DEFAULT_MANDATORY_FIELDS)
        self.variance_tolerance = 0.05
        self.rule_02_enabled = True
        self.rule_04_enabled = True

        if config_path:
            self._load_config(config_path)

    def _load_config(self, config_path: str) -> None:
        cfg_file = Path(config_path)
        if not cfg_file.is_file():
            return

        try:
            content = cfg_file.read_text(encoding="utf-8")
            data = None
            if yaml:
                data = yaml.safe_load(content)

            if isinstance(data, dict):
                rules = data.get("rules", {})
                r1 = rules.get("rule_01", {})
                if "mandatory_fields" in r1 and isinstance(r1["mandatory_fields"], list):
                    self.mandatory_fields = r1["mandatory_fields"]

                r2 = rules.get("rule_02", {})
                if "enabled" in r2:
                    self.rule_02_enabled = bool(r2["enabled"])

                r3 = rules.get("rule_03", {})
                if "tolerance" in r3:
                    self.variance_tolerance = float(r3["tolerance"])

                r4 = rules.get("rule_04", {})
                if "enabled" in r4:
                    self.rule_04_enabled = bool(r4["enabled"])
        except Exception:
            # Fall back to safe defaults if file parsing encounters an issue
            pass

    def evaluate(self, sample: Dict[str, Any]) -> List[str]:
        """
        Evaluates a line-item dictionary against statutory rules:
        - RULE_01: Missing Mandatory Field
        - RULE_02: Interstate / Intra-state POS Mismatch
        - RULE_03: Tax Rate Arithmetic Variance Exceeded
        - RULE_04: Invalid Modulo-36 GSTIN Checksum
        """
        violations: List[str] = []

        # -----------------------------------------------------------------
        # RULE_01: Missing Mandatory Fields
        # -----------------------------------------------------------------
        for field in self.mandatory_fields:
            val = sample.get(field)
            if val is None or (isinstance(val, str) and not val.strip()):
                violations.append(f"RULE_01_MISSING_{field.upper()}")

        # Extract values for downstream rules
        supp_st_raw = sample.get("supplier_state")
        pos_raw = sample.get("declared_pos")
        supp_st = str(supp_st_raw).strip().zfill(2) if supp_st_raw is not None and str(supp_st_raw).strip() else ""
        pos = str(pos_raw).strip().zfill(2) if pos_raw is not None and str(pos_raw).strip() else ""

        try:
            taxable_val = float(sample.get("item_taxable_value", 0.0) or 0.0)
        except (ValueError, TypeError):
            taxable_val = 0.0

        try:
            rate = float(sample.get("declared_effective_rate", 0.0) or 0.0)
        except (ValueError, TypeError):
            rate = 0.0

        try:
            cgst = float(sample.get("cgst_amount", 0.0) or 0.0)
        except (ValueError, TypeError):
            cgst = 0.0

        try:
            sgst = float(sample.get("sgst_amount", 0.0) or 0.0)
        except (ValueError, TypeError):
            sgst = 0.0

        try:
            igst = float(sample.get("igst_amount", 0.0) or 0.0)
        except (ValueError, TypeError):
            igst = 0.0

        # -----------------------------------------------------------------
        # RULE_02: POS Interstate Mismatch
        # -----------------------------------------------------------------
        if self.rule_02_enabled and supp_st and pos:
            if supp_st != pos:
                # Interstate: CGST & SGST must not be charged
                if cgst > 0.0 or sgst > 0.0:
                    violations.append("RULE_02_INTER_STATE_WITH_CGST_SGST")
            else:
                # Intra-state: IGST must not be charged
                if igst > 0.0:
                    violations.append("RULE_02_INTRA_STATE_WITH_IGST")

        # -----------------------------------------------------------------
        # RULE_03: Arithmetic Discrepancy > tolerance
        # -----------------------------------------------------------------
        if supp_st and pos and taxable_val > 0.0:
            tol = self.variance_tolerance
            if supp_st == pos:
                # Intra-state: CGST = SGST = (Rate / 2)%
                expected_half = round(taxable_val * (rate / 200.0), 2)
                if abs(cgst - expected_half) > tol or abs(sgst - expected_half) > tol:
                    violations.append("RULE_03_ARITHMETIC_VARIANCE_EXCEEDED")
            else:
                # Interstate: IGST = Rate%
                expected_igst = round(taxable_val * (rate / 100.0), 2)
                if abs(igst - expected_igst) > tol:
                    violations.append("RULE_03_ARITHMETIC_VARIANCE_EXCEEDED")

        # -----------------------------------------------------------------
        # RULE_04: Modulo-36 GSTIN Checksum
        # -----------------------------------------------------------------
        if self.rule_04_enabled:
            supplier_gstin = sample.get("supplier_gstin")
            if supplier_gstin and isinstance(supplier_gstin, str) and supplier_gstin.strip():
                if not verify_gstin_checksum(supplier_gstin):
                    violations.append("RULE_04_INVALID_GSTIN_CHECKSUM")

        return violations
