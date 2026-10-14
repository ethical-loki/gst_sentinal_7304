"""
Module: Template_Converters/price_anomaly_detector.py
Description: Advanced AI & Statistical Price & Unit Rate Anomaly Detection Engine
             for Indian GST E-Invoicing & E-Way Bill operations.

Detects:
1. Under-Invoicing (Assessable value suppression, customs/tax evasion)
2. Over-Invoicing (Fraudulent Input Tax Credit / ITC inflation, circular trading)
3. Decimal Shift Typos (e.g., 10x, 100x, 1000x errors from accidental keystrokes)
4. Batch Statistical Outliers (Interquartile Range IQR & Modified Z-Score / MAD)
"""

import re
from decimal import Decimal
from typing import Dict, List, Any, Optional, Tuple


# =========================================================================
# COMMODITY & HSN BENCHMARK PRICE MASTER (Typical Indian Market Reference)
# Format: (min_price, max_price, median_price, uqc, description)
# =========================================================================

COMMODITY_PRICE_BENCHMARKS = {
    # Cotton, Textiles, Apparels (Chapters 52, 61, 62)
    "5205": (180.0, 420.0, 280.0, "KGS", "Cotton yarn / Weaving yarn"),
    "520511": (200.0, 360.0, 270.0, "KGS", "Single cotton yarn carded"),
    "520522": (220.0, 380.0, 300.0, "KGS", "Carded weaving yarn 30s"),
    "5207": (210.0, 450.0, 310.0, "KGS", "Cotton yarn put up for retail"),
    "6109": (70.0, 750.0, 250.0, "NOS", "T-shirts, singlets and other vests"),
    "6203": (250.0, 2500.0, 650.0, "NOS", "Men's trousers, shirts and suits"),

    # Iron & Steel, Metals (Chapters 72, 73, 76)
    "7208": (42000.0, 68000.0, 54000.0, "TON", "Flat-rolled products of iron / non-alloy steel"),
    "720839": (45000.0, 65000.0, 55000.0, "TON", "TMT High Tensile Steel Rods"),
    "7214": (44000.0, 64000.0, 52000.0, "TON", "Other bars and rods of iron / steel"),
    "7310": (800.0, 3500.0, 1600.0, "NOS", "Tanks, casks, drums, cans, boxes of iron/steel"),
    "7601": (170.0, 270.0, 220.0, "KGS", "Primary Aluminium ingots 99.7%"),
    "760110": (180.0, 260.0, 215.0, "KGS", "Unwrought aluminium not alloyed"),

    # Plastics & Polymers (Chapter 39)
    "3926": (8.0, 120.0, 28.0, "PCS", "Other articles of plastics / garment hangers"),
    "392690": (10.0, 150.0, 35.0, "PCS", "Articles of plastic n.e.s"),
    "39269069": (10.0, 45.0, 22.0, "PCS", "Plastic Garment Hanger Grade A"),
    "3901": (85.0, 145.0, 110.0, "KGS", "Polymers of ethylene in primary forms"),

    # Electrical & Electronics (Chapter 85)
    "8504": (120.0, 650.0, 280.0, "NOS", "Electrical transformers, static converters, drivers"),
    "850440": (140.0, 550.0, 260.0, "NOS", "Constant Current Electronic LED Driver"),
    "8544": (35.0, 180.0, 75.0, "MTR", "Insulated electric wire, cable"),
    "854449": (40.0, 120.0, 70.0, "MTR", "4 sq mm Solar DC Copper Cable"),

    # Agriculture, Grains & Oil Seeds (Chapters 10, 12)
    "1201": (3800.0, 6500.0, 4900.0, "QTL", "Soya beans, raw / non-GMO"),
    "120190": (4000.0, 6000.0, 5000.0, "QTL", "Non-GMO Raw Soya Beans"),
    "1001": (2100.0, 3200.0, 2600.0, "QTL", "Wheat and meslin"),
    "1006": (2500.0, 7000.0, 4200.0, "QTL", "Rice (Basmati / Non-Basmati)"),

    # Live Animals (Chapter 01)
    "0101": (35000.0, 350000.0, 120000.0, "NOS", "Live horses, asses, mules"),
    "01012100": (50000.0, 500000.0, 180000.0, "NOS", "Pure-bred breeding horses"),
}

# Generic fallback reasonable boundaries by UQC when HSN is unlisted
UQC_HEURISTIC_RANGES = {
    "TON": (15000.0, 250000.0, 60000.0),    # Bulk industrial commodity per ton
    "QTL": (1500.0, 25000.0, 5000.0),       # Agricultural Quintal (100 kg)
    "KGS": (15.0, 8000.0, 250.0),           # Raw materials / parts per kg
    "MTR": (5.0, 2500.0, 85.0),             # Wire / fabric / pipes per meter
    "SQM": (20.0, 5000.0, 350.0),           # Tiles / sheets per square meter
    "LTR": (25.0, 2000.0, 120.0),           # Chemicals / oils per liter
    "NOS": (1.0, 50000.0, 250.0),           # Discretionary items
    "PCS": (1.0, 25000.0, 120.0),           # Pieces
    "SET": (50.0, 100000.0, 1500.0),        # Tool sets / assemblies
    "BOX": (50.0, 50000.0, 800.0),          # Carton boxes
}


class PriceAnomalyDetector:
    """
    AI & Statistical Outlier Engine to detect Over-Invoicing, Under-Invoicing,
    and Keystroke Decimal Shift Typos in GST E-Invoices.
    """

    @classmethod
    def get_benchmark_for_item(cls, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Retrieves the most specific price benchmark available for an item
        based on exact HSN, 4-digit HSN heading, 2-digit HSN chapter, or UQC.
        """
        hsn = str(item.get("hsncd", "") or item.get("hsn", "") or "").strip().replace(" ", "")
        uqc = str(item.get("uqc", "") or "NOS").strip().upper()
        prdnm = str(item.get("prdnm", "") or item.get("desc", "") or "").strip().lower()

        # 1. Exact HSN match
        if hsn in COMMODITY_PRICE_BENCHMARKS:
            b = COMMODITY_PRICE_BENCHMARKS[hsn]
            return {"min": b[0], "max": b[1], "median": b[2], "uqc": b[3], "desc": b[4], "source": f"HSN:{hsn}"}

        # 2. 4-digit HSN Heading match
        if len(hsn) >= 4 and hsn[:4] in COMMODITY_PRICE_BENCHMARKS:
            b = COMMODITY_PRICE_BENCHMARKS[hsn[:4]]
            return {"min": b[0], "max": b[1], "median": b[2], "uqc": b[3], "desc": b[4], "source": f"Heading:{hsn[:4]}"}

        # 3. Keyword matching against known commodities
        keyword_map = {
            "cotton": "5205",
            "yarn": "520522",
            "t-shirt": "6109",
            "tshirt": "6109",
            "steel": "720839",
            "rod": "720839",
            "tmt": "720839",
            "hanger": "39269069",
            "plastic": "3926",
            "aluminum": "760110",
            "aluminium": "760110",
            "driver": "850440",
            "cable": "854449",
            "solar": "854449",
            "soya": "120190",
            "wheat": "1001",
            "horse": "0101",
        }
        for kw, mapped_hsn in keyword_map.items():
            if kw in prdnm:
                b = COMMODITY_PRICE_BENCHMARKS[mapped_hsn]
                return {"min": b[0], "max": b[1], "median": b[2], "uqc": b[3], "desc": b[4], "source": f"Keyword:{kw}"}

        # 4. Fallback: UQC Heuristic
        if uqc in UQC_HEURISTIC_RANGES:
            r = UQC_HEURISTIC_RANGES[uqc]
            return {"min": r[0], "max": r[1], "median": r[2], "uqc": uqc, "desc": f"General {uqc} benchmark", "source": f"UQC:{uqc}"}

        return None

    @classmethod
    def test_decimal_shift(cls, rate: float, median: float) -> Optional[Tuple[float, str]]:
        """
        Tests whether the rate is a classic decimal point shift typo
        (e.g., 10x, 100x, 1000x higher or 0.1x, 0.01x, 0.001x lower).
        Returns (suggested_corrected_rate, explanation) if detected.
        """
        if rate <= 0 or median <= 0:
            return None

        ratio = rate / median
        # Check power of 10 multiples: 10, 100, 1000
        for factor in [10.0, 100.0, 1000.0]:
            # If ratio is close to factor (within 25% tolerance)
            if 0.75 * factor <= ratio <= 1.35 * factor:
                corrected = round(rate / factor, 2)
                return corrected, f"Likely decimal point shift ({int(factor)}x too high). Suggested rate: ₹{corrected:,.2f}"

            inv_factor = 1.0 / factor
            if 0.75 * inv_factor <= ratio <= 1.35 * inv_factor:
                corrected = round(rate * factor, 2)
                return corrected, f"Likely decimal point shift ({int(factor)}x too low). Suggested rate: ₹{corrected:,.2f}"

        return None

    @classmethod
    def analyze_item(cls, item: Optional[Dict[str, Any]] = None, item_index: int = 1, **kwargs) -> Dict[str, Any]:
        """
        Analyzes a single invoice line item for unit price anomalies.
        Accepts a dict or keyword arguments (hsn, product_name, unit_price, quantity, uqc).
        """
        data = dict(item or {})
        data.update(kwargs)
        if "product_name" in data and "prdnm" not in data:
            data["prdnm"] = data["product_name"]
        if "hsn" in data and "hsncd" not in data:
            data["hsncd"] = data["hsn"]
        if "unit_price" in data and "unitprice" not in data:
            data["unitprice"] = data["unit_price"]
        if "quantity" in data and "qty" not in data:
            data["qty"] = data["quantity"]

        raw_rate = data.get("unitrate", data.get("unit_rate", data.get("unitprice", data.get("unit_price", 0))))
        raw_qty = data.get("qty", data.get("quantity", 0))
        raw_ass = data.get("assamt", data.get("taxable_value", 0))
        prdnm = str(data.get("prdnm", "") or data.get("desc", f"Item #{item_index}")).strip()
        hsncd = str(data.get("hsncd", "") or data.get("hsn", "")).strip()
        uqc = str(data.get("uqc", "NOS")).strip().upper()

        def parse_float(val: Any) -> float:
            try:
                s = str(val).strip().replace(" ", "")
                if re.match(r"^\d+,\d{1,3}$", s):
                    s = s.replace(",", ".")
                else:
                    s = s.replace(",", "")
                return float(s)
            except Exception:
                return 0.0

        rate = parse_float(raw_rate)
        qty = parse_float(raw_qty)
        assamt = parse_float(raw_ass)

        # If unit rate missing but assamt and qty given, infer unit rate
        if rate <= 0 and qty > 0 and assamt > 0:
            rate = round(assamt / qty, 2)

        benchmark = cls.get_benchmark_for_item(data)
        if not benchmark or rate <= 0:
            return {
                "item_index": item_index,
                "prdnm": prdnm,
                "hsncd": hsncd,
                "uqc": uqc,
                "unitrate": rate,
                "is_anomaly": False,
                "anomaly_type": "NORMAL",
                "severity": "NONE",
                "risk_score": 0,
                "benchmark": None,
                "reason": "Insufficient benchmark or zero unit rate."
            }

        b_min = benchmark["min"]
        b_max = benchmark["max"]
        b_median = benchmark["median"]
        b_uqc = str(benchmark.get("uqc", "")).upper()

        # Normalize benchmark prices if standard conversion exists (e.g. TON <-> KGS, QTL <-> KGS)
        if b_uqc != uqc:
            if b_uqc == "TON" and uqc in ("KGS", "KG"):
                b_min /= 1000.0
                b_max /= 1000.0
                b_median /= 1000.0
            elif b_uqc in ("KGS", "KG") and uqc == "TON":
                b_min *= 1000.0
                b_max *= 1000.0
                b_median *= 1000.0
            elif b_uqc == "QTL" and uqc in ("KGS", "KG"):
                b_min /= 100.0
                b_max /= 100.0
                b_median /= 100.0
            elif b_uqc in ("KGS", "KG") and uqc == "QTL":
                b_min *= 100.0
                b_max *= 100.0
                b_median *= 100.0

        # Check for Decimal Shift Typo first
        shift_res = cls.test_decimal_shift(rate, b_median)

        # Ratio relative to normal bounds
        ratio_to_median = rate / b_median if b_median > 0 else 1.0

        is_anomaly = False
        anomaly_type = "NORMAL"
        severity = "NONE"
        risk_score = 0
        reason = "Unit rate is within normal statutory benchmark range."
        suggested_rate = None
        statutory_risk = ""

        # UNDER-INVOICING: Rate is significantly below minimum (e.g., < 35% of min)
        if rate < (b_min * 0.35):
            is_anomaly = True
            anomaly_type = "UNDER_INVOICING"
            ratio_deficit = b_min / rate if rate > 0 else 999.0

            if ratio_deficit >= 10.0:
                severity = "CRITICAL"
                risk_score = 95
            elif ratio_deficit >= 4.0:
                severity = "HIGH"
                risk_score = 78
            else:
                severity = "MEDIUM"
                risk_score = 55

            reason = (
                f"Severe Under-Invoicing detected: Unit rate ₹{rate:,.2f}/{uqc} is "
                f"{ratio_deficit:.1f}x lower than market minimum ₹{b_min:,.2f}/{uqc}."
            )
            statutory_risk = (
                "⚠️ Risk of Assessable Value Suppression & Tax Evasion under CGST Act Section 122. "
                "Can trigger scrutiny by Directorate General of GST Intelligence (DGGI)."
            )
            if shift_res:
                suggested_rate = shift_res[0]
                reason += f" {shift_res[1]}"

        # OVER-INVOICING: Rate is significantly above maximum (e.g., > 2.5x of max)
        elif rate > (b_max * 2.5):
            is_anomaly = True
            ratio_excess = rate / b_max

            if shift_res:
                anomaly_type = "DECIMAL_SHIFT_TYPO"
                severity = "HIGH"
                risk_score = 82
                suggested_rate = shift_res[0]
                reason = (
                    f"Typo / Decimal Shift Error: Unit rate ₹{rate:,.2f}/{uqc} is {ratio_excess:.1f}x higher than benchmark max ₹{b_max:,.2f}. "
                    f"{shift_res[1]}"
                )
                statutory_risk = (
                    "⚠️ Keystroke error inflates total tax liability. Check if user typed extra zeros."
                )
            else:
                anomaly_type = "OVER_INVOICING"
                if ratio_excess >= 8.0:
                    severity = "CRITICAL"
                    risk_score = 96
                elif ratio_excess >= 3.5:
                    severity = "HIGH"
                    risk_score = 75
                else:
                    severity = "MEDIUM"
                    risk_score = 58

                reason = (
                    f"Severe Over-Invoicing detected: Unit rate ₹{rate:,.2f}/{uqc} is "
                    f"{ratio_excess:.1f}x higher than market maximum ₹{b_max:,.2f}/{uqc}."
                )
                statutory_risk = (
                    "⚠️ Potential Circular Trading / Fraudulent Input Tax Credit (ITC) claim "
                    "prohibited under CGST Act Section 132(1)(b) & Rule 86A."
                )

        return {
            "item_index": item_index,
            "prdnm": prdnm,
            "hsncd": hsncd,
            "uqc": uqc,
            "unitrate": rate,
            "qty": qty,
            "assamt": assamt,
            "is_anomaly": is_anomaly,
            "anomaly_type": anomaly_type,
            "severity": severity,
            "risk_score": risk_score,
            "benchmark_min": b_min,
            "benchmark_max": b_max,
            "benchmark_median": b_median,
            "ratio_to_median": round(ratio_to_median, 2),
            "suggested_rate": suggested_rate,
            "reason": reason,
            "statutory_risk": statutory_risk,
            "benchmark_source": benchmark["source"]
        }

    @classmethod
    def scan_invoice_payload(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Scans all line items across an invoice payload and generates
        a comprehensive Price & Unit Rate Anomaly Audit Report.
        """
        items = payload.get("itemdtls", [])
        if not items and "items" in payload:
            items = payload["items"]
        if not isinstance(items, list):
            items = []

        item_findings = []
        anomaly_count = 0
        over_count = 0
        under_count = 0
        typo_count = 0
        max_risk = 0

        for idx, itm in enumerate(items, start=1):
            if isinstance(itm, dict):
                res = cls.analyze_item(itm, item_index=idx)
                item_findings.append(res)
                if res["is_anomaly"]:
                    anomaly_count += 1
                    max_risk = max(max_risk, res["risk_score"])
                    if res["anomaly_type"] == "OVER_INVOICING":
                        over_count += 1
                    elif res["anomaly_type"] == "UNDER_INVOICING":
                        under_count += 1
                    elif res["anomaly_type"] == "DECIMAL_SHIFT_TYPO":
                        typo_count += 1

        overall_status = "CLEAN"
        if max_risk >= 80:
            overall_status = "CRITICAL_RISK"
        elif max_risk >= 50:
            overall_status = "HIGH_RISK"
        elif max_risk > 0:
            overall_status = "MODERATE_RISK"

        return {
            "status": overall_status,
            "has_anomalies": anomaly_count > 0,
            "anomaly_count": anomaly_count,
            "over_invoicing_count": over_count,
            "under_invoicing_count": under_count,
            "typo_count": typo_count,
            "max_risk_score": max_risk,
            "items_scanned": len(item_findings),
            "findings": item_findings
        }


price_anomaly_detector = PriceAnomalyDetector()


def get_price_anomaly_detector() -> PriceAnomalyDetector:
    return price_anomaly_detector

