"""
Section 17(5) Ineligible Input Tax Credit (ITC) Detector for Indian GST.
Scans product descriptions, names, and HSN codes for blocked credit restrictions under:
- Section 17(5)(a): Motor vehicles & passenger transport conveyances
- Section 17(5)(b)(i): Food & beverages, outdoor catering, catering services
- Section 17(5)(b)(ii): Club membership, health and fitness centres
- Section 17(5)(b)(iii): Rent-a-cab services
- Section 17(5)(b)(iv): Life & health insurance
- Section 17(5)(b)(v): Travel benefits, vacation, leave travel
- Section 17(5)(c): Works contract services for construction of immovable property
- Section 17(5)(d): Goods or services for personal consumption / non-business use
"""

import re
from typing import Any, Dict, List, Optional, Tuple, Union

SECTION_17_5_RULES: List[Dict[str, Any]] = [
    {
        "sub_clause": "17(5)(a)",
        "full_tag": "ITC Blocked: CGST Act Section 17(5)(a)",
        "terms": [
            r"\b(passenger\s+vehicles?)\b",
            r"\b(motor\s+cars?)\b",
            r"\b(motor\s+cabs?)\b",
            r"\b(dumpers?)\b",
            r"\b(works\s+trucks?)\b",
        ],
        "hsn_prefixes": ["8703"],
        "hsn_label": "HSN 8703 (Motor cars & passenger vehicles)",
    },
    {
        "sub_clause": "17(5)(b)(i)",
        "full_tag": "ITC Blocked: CGST Act Section 17(5)(b)(i)",
        "terms": [
            r"\b(food\s+(?:and|&)\s+beverages?)\b",
            r"\b(outdoor\s+catering)\b",
            r"\b(catering\s+services?)\b",
            r"\b(food\s+services?)\b",
        ],
        "hsn_prefixes": [],
        "hsn_label": "Food & catering services",
    },
    {
        "sub_clause": "17(5)(b)(ii)",
        "full_tag": "ITC Blocked: CGST Act Section 17(5)(b)(ii)",
        "terms": [
            r"\b(club\s+memberships?)\b",
            r"\b(health\s+clubs?)\b",
            r"\b(fitness\s+cent(?:re|er)s?)\b",
        ],
        "hsn_prefixes": [],
        "hsn_label": "Club & fitness memberships",
    },
    {
        "sub_clause": "17(5)(b)(iii)",
        "full_tag": "ITC Blocked: CGST Act Section 17(5)(b)(iii)",
        "terms": [
            r"\b(rent(?:ing)?(?:\s+of|-|\s+)a(?:\s+|-)?cabs?)\b",
            r"\b(cab\s+rentals?)\b",
        ],
        "hsn_prefixes": [],
        "hsn_label": "Rent-a-cab services",
    },
    {
        "sub_clause": "17(5)(b)(iv)",
        "full_tag": "ITC Blocked: CGST Act Section 17(5)(b)(iv)",
        "terms": [
            r"\b(life\s+insurance)\b",
            r"\b(health\s+insurance)\b",
            r"\b(medical\s+insurance)\b",
        ],
        "hsn_prefixes": [],
        "hsn_label": "Life / Health insurance",
    },
    {
        "sub_clause": "17(5)(b)(v)",
        "full_tag": "ITC Blocked: CGST Act Section 17(5)(b)(v)",
        "terms": [
            r"\b(travel\s+benefits?)\b",
            r"\b(vacations?(?:\s+packages?)?)\b",
            r"\b(leave\s+travel(?:\s+(?:concessions?|allowance))?)\b",
            r"\b(ltc|lta)\b",
        ],
        "hsn_prefixes": [],
        "hsn_label": "Travel benefits & leave travel",
    },
    {
        "sub_clause": "17(5)(c)",
        "full_tag": "ITC Blocked: CGST Act Section 17(5)(c)",
        "terms": [
            r"\b(works\s+contracts?)\b",
            r"\b(immovable\s+propert(?:y|ies))\b",
            r"\b(construction(?:\s+of\s+buildings?|\s+services?)?)\b",
        ],
        "hsn_prefixes": [],
        "hsn_label": "Works contract & construction",
    },
    {
        "sub_clause": "17(5)(d)",
        "full_tag": "ITC Blocked: CGST Act Section 17(5)(d)",
        "terms": [
            r"\b(personal\s+consumption)\b",
            r"\b(non-?business\s+use)\b",
            r"\b(personal\s+use)\b",
        ],
        "hsn_prefixes": [],
        "hsn_label": "Personal consumption",
    },
]


class Section175Detector:
    """
    Regex rules engine scanning free-text product names, descriptions, and HSN codes
    to identify statutory Section 17(5) Input Tax Credit (ITC) blocks.
    """

    def __init__(self):
        # Precompile regexes
        self.compiled_rules = []
        for rule in SECTION_17_5_RULES:
            compiled_patterns = [
                (term, re.compile(term, re.IGNORECASE)) for term in rule["terms"]
            ]
            self.compiled_rules.append({
                "sub_clause": rule["sub_clause"],
                "full_tag": rule["full_tag"],
                "compiled_patterns": compiled_patterns,
                "hsn_prefixes": rule.get("hsn_prefixes", []),
                "hsn_label": rule.get("hsn_label", ""),
            })

    def scan(
        self,
        product_text: Optional[str],
        hsn: Optional[Union[str, int]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Scans product text and optional HSN code against Section 17(5) clauses.
        Returns structured dict if blocked, else None.
        """
        text = str(product_text or "").strip()
        clean_hsn = re.sub(r"\D", "", str(hsn or "").strip()) if hsn else ""

        # 1. Text Regex Scanning
        if text:
            for rule in self.compiled_rules:
                for term_raw, pattern in rule["compiled_patterns"]:
                    match = pattern.search(text)
                    if match:
                        matched_term = match.group(0).lower()
                        return {
                            "flag": "ITC_BLOCKED_SECTION_17_5",
                            "sub_clause": rule["sub_clause"],
                            "full_tag": rule["full_tag"],
                            "matched_term": matched_term,
                            "product_text": text,
                            "severity": "HIGH",
                        }

        # 2. HSN-based Statutory Fallback
        if clean_hsn:
            for rule in self.compiled_rules:
                for prefix in rule["hsn_prefixes"]:
                    if clean_hsn.startswith(prefix):
                        return {
                            "flag": "ITC_BLOCKED_SECTION_17_5",
                            "sub_clause": rule["sub_clause"],
                            "full_tag": rule["full_tag"],
                            "matched_term": rule["hsn_label"],
                            "product_text": text or f"HSN {clean_hsn}",
                            "severity": "HIGH",
                        }

        return None

    def scan_all(
        self,
        product_text: Optional[str],
        hsn: Optional[Union[str, int]] = None,
    ) -> List[Dict[str, Any]]:
        """Scans and returns all matching Section 17(5) clauses."""
        text = str(product_text or "").strip()
        clean_hsn = re.sub(r"\D", "", str(hsn or "").strip()) if hsn else ""
        matches = []
        matched_clauses = set()

        if text:
            for rule in self.compiled_rules:
                for _, pattern in rule["compiled_patterns"]:
                    match = pattern.search(text)
                    if match and rule["sub_clause"] not in matched_clauses:
                        matched_clauses.add(rule["sub_clause"])
                        matches.append({
                            "flag": "ITC_BLOCKED_SECTION_17_5",
                            "sub_clause": rule["sub_clause"],
                            "full_tag": rule["full_tag"],
                            "matched_term": match.group(0).lower(),
                            "product_text": text,
                            "severity": "HIGH",
                        })
                        break

        if clean_hsn:
            for rule in self.compiled_rules:
                if rule["sub_clause"] not in matched_clauses:
                    for prefix in rule["hsn_prefixes"]:
                        if clean_hsn.startswith(prefix):
                            matched_clauses.add(rule["sub_clause"])
                            matches.append({
                                "flag": "ITC_BLOCKED_SECTION_17_5",
                                "sub_clause": rule["sub_clause"],
                                "full_tag": rule["full_tag"],
                                "matched_term": rule["hsn_label"],
                                "product_text": text or f"HSN {clean_hsn}",
                                "severity": "HIGH",
                            })
                            break

        return matches


# Global singleton instance
section_17_5_detector = Section175Detector()


def scan(
    product_text: Optional[str],
    hsn: Optional[Union[str, int]] = None,
) -> Optional[Dict[str, Any]]:
    """Module-level scan alias."""
    return section_17_5_detector.scan(product_text, hsn=hsn)
