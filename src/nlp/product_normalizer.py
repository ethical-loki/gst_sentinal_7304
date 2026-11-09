"""
src/nlp/product_normalizer.py — Specification-Preserving Product Normalizer.

Day 6 Final Validation & Structured Attribute Categorization:
- Immutability: Original customer input is strictly preserved in original_description.
- Distinct Attribute Categorization:
  * dimensions: physical dimensions, cross-sectional areas (e.g. '2.5 sq mm', '1/2 inch', 'M12 x 50 mm')
  * electrical_configurations: phases, poles, cores (e.g. '3 phase', '3 core')
  * voltage_ratings: operational voltages (e.g. '415V', '230V')
  * power_ratings: electrical/mechanical power capacities (e.g. '10 KVA', '5kW')
  * quantities: counts and packaging units (e.g. '100 pcs', '10 nos')
  * grades: engineering grades and pressure classes (e.g. 'SS 304', 'SCH 40', 'Class 150', '8.8')
  * materials: physical materials (e.g. 'copper', 'stainless steel', 'pvc')
  * part_numbers: model & bearing codes (e.g. '6204-2RS')
- Technical Casing Preservation: Preserved attributes retain exact technical casing
  (e.g. '415V', '10 KVA', 'SCH 40', '6204-2RS') even when normalized_description is lowercased.
- No Fact Hallucination: Missing attributes are never inferred or fabricated.
"""

import re
from typing import Dict, List, Optional, Set, Any
from dataclasses import dataclass, field

from src.nlp.multilingual_processor import get_multilingual_processor, MultilingualResult


# ---------------------------------------------------------------------------
# STRUCTURED SPECIFICATION PATTERNS
# ---------------------------------------------------------------------------

# 1. Dimensions: Thread, Linear, Cross-sectional areas
DIMENSION_PATTERNS = [
    # Metric thread specs: M12 x 50 mm, M12x50, M8x30
    r"\b[mM]\d+\s*(?:[xX*]\s*\d+(?:\.\d+)?)?\s*(?:mm)?\b",
    # Fractional & decimal imperial/metric lengths: 1/2 inch, 1.5 in, 50mm, 100 meters
    r"\b\d+[/.]\d+\s*(?:inch|in|\"|mm|cm|meters?|mtrs?|m)\b",
    r"\b\d+\s*(?:inch|in|\"|mm|cm|meters?|mtrs?|m)\b",
    # Multi-dimensional specs e.g. 20x47x14 mm, 20 x 47 x 14 mm
    r"\b\d+(?:\.\d+)?\s*[xX*]\s*\d+(?:\.\d+)?\s*[xX*]\s*\d+(?:\.\d+)?\s*(?:mm|cm|in|inch)?\b",
    r"\b\d+(?:\.\d+)?\s*[xX*]\s*\d+(?:\.\d+)?\s*(?:mm|cm|in|inch)\b",
    # Wire/Cable cross-sectional area: 2.5 sq mm, 4 sqmm, 10 AWG
    r"\b\d+(?:\.\d+)?\s*(?:sq\s*mm|sqmm|awg)\b",
]

# 2. Electrical Configuration: Phases, Cores, Poles
CONFIG_PATTERNS = [
    r"\b\d+\s*(?:phase|core|pole|way)s?\b",
]

# 3. Voltage Rating: V, Volt, Volts, kV
VOLTAGE_PATTERNS = [
    r"\b\d+(?:\.\d+)?\s*(?:v|volt|volts|kv)\b",
]

# 4. Power Rating: KVA, kW, HP, MW
POWER_PATTERNS = [
    r"\b\d+(?:\.\d+)?\s*(?:kva|kw|hp|mw|w|watts?)\b",
]

# 5. Rotational Speed Rating: RPM
SPEED_PATTERNS = [
    r"\b\d+\s*(?:rpm|RPM)\b",
]

# 5. Material & Grade patterns (statutory trade identifiers)
GRADE_PATTERNS = [
    r"\bgrade\s*[0-9]\.[0-9]\b",
    r"\b(?:4\.6|4\.8|5\.6|5\.8|6\.8|8\.8|10\.9|12\.9)\b",
    r"\b[sS][sS]\s*(?:304|316|202|310)\b",   # Stainless steel grades
    r"\b[cC]lass\s*(?:150|300|600|800)\b",    # Flange / valve pressure classes
    r"\b[sS][cC][hH]\s*(?:40|80|160)\b",     # Pipe schedules
    r"\b(?:bsp|npt|metric)\b",               # Thread types
]

# 6. Alphanumeric part & bearing codes (e.g. 6204-2RS, SKF-6204)
PART_CODE_PATTERN = r"\b\d{4,}(?:-[0-9a-zA-Z]+)?\b|\b[A-Za-z]{1,4}[0-9]{3,}[A-Za-z0-9\-]*\b"

# 7. Commercial packaging / quantity units
QUANTITY_UNIT_PATTERN = re.compile(
    r"\b\d+\s*(?:pcs|pc|pieces|piece|nos|no|pkts?|packets?|boxes?|box|cartons?|rolls?|drums?|bags?|sets?)\b",
    re.IGNORECASE
)

# Known industrial material names for attribute tracking
KNOWN_MATERIALS = [
    "stainless steel", "copper", "brass", "mild steel", "cast iron",
    "pvc", "aluminum", "carbon steel", "galvanized iron"
]

# Known trade brands for attribute tracking & discrimination
KNOWN_BRANDS = [
    "lee cooper", "leecoper", "bata", "woodland", "nike", "adidas", "puma",
    "skf", "havells", "siemens", "schneider", "abb", "bosch", "crompton", "finolex", "polycab"
]

BRAND_CANONICAL_MAP = {
    "leecoper": "Lee Cooper",
    "lee cooper": "Lee Cooper",
    "bata": "Bata",
    "woodland": "Woodland",
    "nike": "Nike",
    "adidas": "Adidas",
    "puma": "Puma",
    "skf": "SKF",
    "havells": "Havells",
    "siemens": "Siemens",
    "schneider": "Schneider",
    "abb": "ABB",
    "bosch": "Bosch",
    "crompton": "Crompton",
    "finolex": "Finolex",
    "polycab": "Polycab",
}


@dataclass(frozen=True)
class ProductAttributes:
    """Immutable, distinctly categorized physical specifications."""
    dimensions: List[str] = field(default_factory=list)
    electrical_configurations: List[str] = field(default_factory=list)
    voltage_ratings: List[str] = field(default_factory=list)
    power_ratings: List[str] = field(default_factory=list)
    speed_ratings: List[str] = field(default_factory=list)
    quantities: List[str] = field(default_factory=list)
    grades: List[str] = field(default_factory=list)
    materials: List[str] = field(default_factory=list)
    part_numbers: List[str] = field(default_factory=list)
    units: List[str] = field(default_factory=list)
    brands: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dimensions": list(self.dimensions),
            "electrical_configurations": list(self.electrical_configurations),
            "voltage_ratings": list(self.voltage_ratings),
            "power_ratings": list(self.power_ratings),
            "speed_ratings": list(self.speed_ratings),
            "quantities": list(self.quantities),
            "grades": list(self.grades),
            "materials": list(self.materials),
            "part_numbers": list(self.part_numbers),
            "units": list(self.units),
            "brands": list(self.brands),
        }


@dataclass(frozen=True)
class NormalizedProductResult:
    """
    Immutable output container satisfying Day 6 specifications:
    - original_description: exact original customer input (never mutated).
    - normalized_description: cleaned, specification-preserving retrieval representation.
    - detected_language: heuristic language label (en, hi, hi-Latn, mr, ta).
    - detected_script: detected writing script (Latin, Devanagari, Tamil, Mixed).
    - language_confidence: heuristic confidence score.
    - preserved_attributes: extracted technical specifications dictionary (with preserved casing).
    - unresolved_tokens: terms that could not be safely normalized.
    - is_controlled_glossary_match: whether controlled glossary safely processed relevant terms.
    - canonical_description: alias for normalized_description (backwards compatibility).
    - clean_trade_name: alias for clean name (backwards compatibility).
    """
    original_description: str
    normalized_description: str
    canonical_description: str
    clean_trade_name: str
    detected_language: str
    detected_script: str
    language_confidence: float
    preserved_attributes: Dict[str, List[str]]
    attributes: ProductAttributes
    part_numbers: List[str]
    unresolved_tokens: List[str]
    is_controlled_glossary_match: bool
    has_specifications: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_description": self.original_description,
            "normalized_description": self.normalized_description,
            "canonical_description": self.canonical_description,
            "clean_trade_name": self.clean_trade_name,
            "detected_language": self.detected_language,
            "detected_script": self.detected_script,
            "language_confidence": self.language_confidence,
            "preserved_attributes": {k: list(v) for k, v in self.preserved_attributes.items()},
            "attributes": self.attributes.to_dict(),
            "part_numbers": list(self.part_numbers),
            "unresolved_tokens": list(self.unresolved_tokens),
            "is_controlled_glossary_match": self.is_controlled_glossary_match,
            "has_specifications": self.has_specifications,
        }


class ProductNormalizer:
    """
    Specification-preserving product description normalizer.
    Preserves exact dimensions, engineering grades, electrical ratings, part numbers,
    and quantities without data loss or fact hallucination.
    """

    def __init__(self):
        self._dim_regexes = [re.compile(p, re.IGNORECASE) for p in DIMENSION_PATTERNS]
        self._config_regexes = [re.compile(p, re.IGNORECASE) for p in CONFIG_PATTERNS]
        self._voltage_regexes = [re.compile(p, re.IGNORECASE) for p in VOLTAGE_PATTERNS]
        self._power_regexes = [re.compile(p, re.IGNORECASE) for p in POWER_PATTERNS]
        self._speed_regexes = [re.compile(p, re.IGNORECASE) for p in SPEED_PATTERNS]
        self._grade_regexes = [re.compile(p, re.IGNORECASE) for p in GRADE_PATTERNS]
        self._part_regex = re.compile(PART_CODE_PATTERN)

    def _extract_spans_with_casing(self, regexes: List[re.Pattern], text: str) -> List[str]:
        """Extracts matched substrings preserving original technical casing."""
        found: List[str] = []
        for r in regexes:
            for match in r.finditer(text):
                val = match.group().strip()
                # Deduplicate case-insensitively while preserving original casing
                if not any(val.lower() == existing.lower() or (val.lower() in existing.lower() and len(existing) > len(val)) for existing in found):
                    found = [e for e in found if e.lower() not in val.lower()]
                    found.append(val)
        return found

    def normalize(self, description: str) -> NormalizedProductResult:
        """
        Normalizes inbound customer text while preserving all commercial specifications.
        """
        orig = str(description or "").strip()
        if not orig:
            empty_attr = ProductAttributes()
            return NormalizedProductResult(
                original_description="",
                normalized_description="",
                canonical_description="",
                clean_trade_name="",
                detected_language="en",
                detected_script="Latin",
                language_confidence=1.0,
                preserved_attributes=empty_attr.to_dict(),
                attributes=empty_attr,
                part_numbers=[],
                unresolved_tokens=[],
                is_controlled_glossary_match=True,
                has_specifications=False,
            )

        # 1. Linguistic and Script Analysis (Controlled Glossary Delegation)
        multi_proc = get_multilingual_processor()
        multi_res = multi_proc.process(orig)

        # Target text: translated English representation if multilingual, else original
        target_text = multi_res.translated_text if multi_res.is_multilingual else orig

        # Text source for technical casing: prefer original if English/Latin, else target
        casing_source = orig if multi_res.detected_script == "Latin" else target_text

        # 2. Extract Dimensions (thread, linear, cross-sectional area)
        dimensions = self._extract_spans_with_casing(self._dim_regexes, casing_source)
        if multi_res.is_multilingual and not dimensions:
            dimensions = self._extract_spans_with_casing(self._dim_regexes, orig)

        # 3. Extract Electrical Configurations (phase, pole, core)
        configurations = self._extract_spans_with_casing(self._config_regexes, casing_source)

        # 4. Extract Voltage Ratings (415V, 230V)
        voltages = self._extract_spans_with_casing(self._voltage_regexes, casing_source)

        # 5. Extract Power Ratings (10 KVA, 5kW)
        powers = self._extract_spans_with_casing(self._power_regexes, casing_source)

        # 5b. Extract Rotational Speed Ratings (1400 rpm)
        speeds = self._extract_spans_with_casing(self._speed_regexes, casing_source)

        # 6. Extract Engineering Grades & Standards (preserve casing e.g. SCH 40, Class 150)
        grades: List[str] = []
        for r in self._grade_regexes:
            for match in r.finditer(casing_source):
                val = match.group().strip()
                # Standardize acronym casing cleanly
                upper_val = val.upper()
                if "CLASS" in upper_val:
                    canonical_val = upper_val.title()
                elif "SCH" in upper_val or "SS" in upper_val or "BSP" in upper_val or "NPT" in upper_val:
                    canonical_val = upper_val
                elif "GRADE" in upper_val:
                    canonical_val = val
                else:
                    canonical_val = val
                if not any(canonical_val.lower() == g.lower() for g in grades):
                    grades.append(canonical_val)

        # 7. Extract Part & Model Numbers (preserve original casing e.g. 6204-2RS)
        part_numbers: List[str] = []
        for match in self._part_regex.finditer(casing_source):
            val = match.group().strip()
            if any(c.isdigit() for c in val) and not any(val.lower() == p.lower() for p in part_numbers):
                part_numbers.append(val)

        # 8. Extract Materials
        materials: List[str] = []
        lower_target = target_text.lower()
        for mat in KNOWN_MATERIALS:
            if re.search(r"\b" + re.escape(mat) + r"\b", lower_target):
                if mat not in materials:
                    materials.append(mat)

        # 9. Extract Quantities / Pack Units (preserve casing e.g. 100 pcs)
        quantities: List[str] = []
        for match in QUANTITY_UNIT_PATTERN.finditer(casing_source):
            val = match.group().strip()
            if not any(val.lower() == q.lower() for q in quantities):
                quantities.append(val)

        # 10. Extract Measurement Units
        units: List[str] = []
        for d in dimensions:
            parts = d.split()
            if len(parts) > 1:
                u = parts[-1]
                if u not in units:
                    units.append(u)
        for v in voltages:
            u = re.sub(r"[\d.]", "", v).strip()
            if u and u not in units:
                units.append(u)
        for p in powers:
            u = re.sub(r"[\d.]", "", p).strip()
            if u and u not in units:
                units.append(u)
        for s in speeds:
            u = re.sub(r"[\d.]", "", s).strip()
            if u and u not in units:
                units.append(u)
        for q in quantities:
            u = re.sub(r"[\d.]", "", q).strip()
            if u and u not in units:
                units.append(u)

        # 10b. Extract Brands (e.g. Lee Cooper, Bata)
        brands: List[str] = []
        lower_target = target_text.lower()
        for b_name in KNOWN_BRANDS:
            if re.search(r"\b" + re.escape(b_name) + r"\b", lower_target):
                canon_b = BRAND_CANONICAL_MAP.get(b_name, b_name.title())
                if canon_b not in brands:
                    brands.append(canon_b)
                # Standardize brand spelling in target text (e.g. Leecoper -> Lee Cooper)
                target_text = re.sub(r"\b" + re.escape(b_name) + r"\b", canon_b, target_text, flags=re.IGNORECASE)

        # 11. Clean Syntax Noise for Normalized Description
        cleaned = target_text
        cleaned = re.sub(r"[#*_~\|\^<>{}\[\]\(\);:]", " ", cleaned)
        cleaned = re.sub(r"(?<!\d)/|/(?!\d)", " ", cleaned)
        cleaned = re.sub(r"[,\\+=]", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        # Canonical description: standard lowercase representation
        canonical = cleaned.lower()

        attr = ProductAttributes(
            dimensions=dimensions,
            electrical_configurations=configurations,
            voltage_ratings=voltages,
            power_ratings=powers,
            speed_ratings=speeds,
            quantities=quantities,
            grades=grades,
            materials=materials,
            part_numbers=part_numbers,
            units=units,
            brands=brands,
        )

        has_specs = bool(dimensions or configurations or voltages or powers or speeds or grades or part_numbers or materials or brands)

        return NormalizedProductResult(
            original_description=orig,
            normalized_description=canonical,
            canonical_description=canonical,
            clean_trade_name=cleaned,
            detected_language=multi_res.detected_language,
            detected_script=multi_res.detected_script,
            language_confidence=multi_res.language_confidence,
            preserved_attributes=attr.to_dict(),
            attributes=attr,
            part_numbers=part_numbers,
            unresolved_tokens=multi_res.unresolved_tokens,
            is_controlled_glossary_match=multi_res.is_controlled_glossary_match,
            has_specifications=has_specs,
        )


_NORMALIZER_INSTANCE: Optional[ProductNormalizer] = None


def get_product_normalizer() -> ProductNormalizer:
    global _NORMALIZER_INSTANCE
    if _NORMALIZER_INSTANCE is None:
        _NORMALIZER_INSTANCE = ProductNormalizer()
    return _NORMALIZER_INSTANCE
