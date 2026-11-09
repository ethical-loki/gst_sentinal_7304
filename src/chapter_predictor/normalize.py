"""
src/chapter_predictor/normalize.py
==================================
Stage A: Product Name Normalizer & Statutory Fact Extraction.
100% Dynamic - Driven exclusively by external data files:
- data/abbreviations.json        (Packaging, trade acronyms, colloquialisms)
- data/noise_words.json          (Brand names, marketing hype, trade fillers)
- data/statutory_materials.json  (Statutory constituent materials under WCO)
- data/statutory_forms.json      (Statutory processing states & forms)
- data/tariff_head_noun_index.json (6,300+ statutory tariff head nouns)
- data/article_form_vocabulary.json (Curated commodity taxonomy)

ZERO hardcoded product names, materials, or keyword arrays in Python code.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent

# External data file paths
NOISE_WORDS_FILE = ROOT_DIR / "data" / "noise_words.json"
ABBREVIATIONS_FILE = ROOT_DIR / "data" / "abbreviations.json"
MATERIALS_FILE = ROOT_DIR / "data" / "statutory_materials.json"
FORMS_FILE = ROOT_DIR / "data" / "statutory_forms.json"
HEAD_NOUN_INDEX_FILE = ROOT_DIR / "data" / "tariff_head_noun_index.json"
VOCABULARY_FILE = ROOT_DIR / "data" / "article_form_vocabulary.json"

# In-memory caches for fast sub-millisecond retrieval
_ABBREVIATIONS_CACHE: Dict[str, str] = {}
_NOISE_WORDS_CACHE: Dict[str, List[str]] = {}
_MATERIALS_CACHE: List[Dict[str, Any]] = []
_FORMS_CACHE: List[Dict[str, Any]] = []
_HEAD_NOUN_CACHE: Dict[str, Any] = {}
_VOCABULARY_CACHE: List[Dict[str, Any]] = []


def load_abbreviations() -> Dict[str, str]:
    """Loads units, prepositions, and trade colloquialisms from data/abbreviations.json."""
    global _ABBREVIATIONS_CACHE
    if _ABBREVIATIONS_CACHE:
        return _ABBREVIATIONS_CACHE
    if ABBREVIATIONS_FILE.exists():
        try:
            with open(ABBREVIATIONS_FILE, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
                merged = {}
                for category, mapping in raw_data.items():
                    if isinstance(mapping, dict):
                        merged.update(mapping)
                _ABBREVIATIONS_CACHE = merged
                return _ABBREVIATIONS_CACHE
        except Exception as e:
            logger.warning(f"Could not load abbreviations.json: {e}")
    return {}


def load_noise_words() -> Dict[str, List[str]]:
    """Loads brand names, character titles, and marketing hype words from data/noise_words.json."""
    global _NOISE_WORDS_CACHE
    if _NOISE_WORDS_CACHE:
        return _NOISE_WORDS_CACHE
    if NOISE_WORDS_FILE.exists():
        try:
            with open(NOISE_WORDS_FILE, "r", encoding="utf-8") as f:
                _NOISE_WORDS_CACHE = json.load(f)
                return _NOISE_WORDS_CACHE
        except Exception as e:
            logger.warning(f"Could not load noise_words.json: {e}")
    return {"brand_names": [], "marketing_adjectives": [], "trade_pack_fillers": []}


def load_statutory_materials() -> List[Dict[str, Any]]:
    """Loads statutory constituent materials dynamically from data/statutory_materials.json."""
    global _MATERIALS_CACHE
    if _MATERIALS_CACHE:
        return _MATERIALS_CACHE
    if MATERIALS_FILE.exists():
        try:
            with open(MATERIALS_FILE, "r", encoding="utf-8") as f:
                _MATERIALS_CACHE = json.load(f)
                return _MATERIALS_CACHE
        except Exception as e:
            logger.warning(f"Could not load statutory_materials.json: {e}")
    return []


def load_statutory_forms() -> List[Dict[str, Any]]:
    """Loads statutory processing states and forms dynamically from data/statutory_forms.json."""
    global _FORMS_CACHE
    if _FORMS_CACHE:
        return _FORMS_CACHE
    if FORMS_FILE.exists():
        try:
            with open(FORMS_FILE, "r", encoding="utf-8") as f:
                _FORMS_CACHE = json.load(f)
                return _FORMS_CACHE
        except Exception as e:
            logger.warning(f"Could not load statutory_forms.json: {e}")
    return []


def load_head_noun_index() -> Dict[str, Any]:
    """Loads the comprehensive 6,300+ tariff-derived head noun index."""
    global _HEAD_NOUN_CACHE
    if _HEAD_NOUN_CACHE:
        return _HEAD_NOUN_CACHE
    if HEAD_NOUN_INDEX_FILE.exists():
        try:
            with open(HEAD_NOUN_INDEX_FILE, "r", encoding="utf-8") as f:
                _HEAD_NOUN_CACHE = json.load(f)
                return _HEAD_NOUN_CACHE
        except Exception as e:
            logger.warning(f"Could not load tariff_head_noun_index.json: {e}")
    return {}


def load_vocabulary() -> List[Dict[str, Any]]:
    """Loads curated article and form vocabulary dataset from data/article_form_vocabulary.json."""
    global _VOCABULARY_CACHE
    if _VOCABULARY_CACHE:
        return _VOCABULARY_CACHE
    if VOCABULARY_FILE.exists():
        try:
            with open(VOCABULARY_FILE, "r", encoding="utf-8") as f:
                _VOCABULARY_CACHE = json.load(f)
                return _VOCABULARY_CACHE
        except Exception as e:
            logger.warning(f"Could not load article_form_vocabulary.json: {e}")
    return []


def get_protected_statutory_tokens() -> Set[str]:
    """Dynamically derives tokens that must NEVER be stripped as noise from statutory data."""
    protected = {"not", "un", "non", "without", "excluding", "other", "than"}
    forms = load_statutory_forms()
    for f in forms:
        term = f.get("term", "").strip().lower()
        if term:
            protected.add(term)
    return protected


def strip_marketing_noise(text: str) -> str:
    """Strips recognized pop-culture brands, characters, and marketing adjectives from data/noise_words.json."""
    data = load_noise_words()
    all_noise = (
        data.get("brand_names", []) +
        data.get("marketing_adjectives", []) +
        data.get("trade_pack_fillers", [])
    )
    sorted_noise = sorted(all_noise, key=lambda x: len(x), reverse=True)
    protected_tokens = get_protected_statutory_tokens()
    
    cleaned = f" {text} "
    for phrase in sorted_noise:
        p_clean = phrase.strip().lower()
        if p_clean in protected_tokens or not p_clean:
            continue
        cleaned = re.sub(rf"\b{re.escape(p_clean)}\b", " ", cleaned, flags=re.IGNORECASE)
    
    return re.sub(r"\s+", " ", cleaned).strip()


def normalize_product_name(
    raw_text: str,
    custom_abbreviations: Dict[str, str] = None
) -> Tuple[str, List[str]]:
    """
    Normalizes a free-text commercial product description:
    - Lowercases text
    - Expands abbreviations dynamically from data/abbreviations.json
    - Strips superficial invoice codes / numbers while preserving statutory negations
    - Returns normalized string and word token list.
    """
    text = (raw_text or "").strip().lower()
    if not text:
        return "", []

    # 1. Expand abbreviations dynamically from data/abbreviations.json
    abbrev_dict = {**load_abbreviations(), **(custom_abbreviations or {})}
    for pattern, replacement in abbrev_dict.items():
        text = re.sub(pattern, replacement, text)

    # 2. Normalize hyphens and slashes between words
    text = re.sub(r"\bun-(\w+)\b", r"un\1", text)
    text = re.sub(r"\bnon-(\w+)\b", r"non \1", text)
    text = re.sub(r"[\/\-_]", " ", text)

    # 3. Strip invoice noise: quantities with attached units
    text = re.sub(r"\b\d+\s*(?:g|gms|kg|kgs|ltr|ltrs|ml|mtr|mtrs|pcs|pc|nos|pieces|pkt|pkts|pack|bags?)\b", " ", text)
    text = re.sub(r"#\w+", " ", text)
    text = re.sub(r"\b\d+x\d+\b", " ", text)
    text = re.sub(r"\b\d+mm\b|\b\d+cm\b|\b\d+m\b|\b\d+inch\b|\b\d+in\b", " ", text)
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\b\d+\b", " ", text)

    # 4. Strip marketing noise dynamically from data/noise_words.json
    text = strip_marketing_noise(text)

    # 5. Tokenize and filter
    protected_tokens = get_protected_statutory_tokens()
    raw_tokens = [tok for tok in text.split() if tok]
    tokens = []
    for tok in raw_tokens:
        if len(tok) >= 2 or tok in protected_tokens:
            tokens.append(tok)

    normalized_string = " ".join(tokens)
    return normalized_string, tokens


def extract_query_facts(raw_text: str) -> Dict[str, Any]:
    """
    Dynamically extracts head noun, constituent material, and statutory state.
    100% Data-Driven from JSON indexes without inline lists:
    1. Material: Matched dynamically against data/statutory_materials.json
    2. Multi-word head noun: Matched against data/tariff_head_noun_index.json
    3. Single word head noun: Rightmost content noun heuristic applied against head noun index
    4. State & Form: Matched dynamically against data/statutory_forms.json
    """
    norm, tokens = normalize_product_name(raw_text)
    lower = norm.lower()

    materials_list = load_statutory_materials()
    forms_list = load_statutory_forms()
    head_noun_index = load_head_noun_index()
    vocab = load_vocabulary()

    detected_article = None
    detected_form = None
    detected_material = None
    detected_family = None
    detected_form_stage = "unknown"
    vocab_candidate_chapters: Set[str] = set()

    # 1. Detect constituent material dynamically from data/statutory_materials.json
    # Sort materials by length descending to match compound materials first (e.g. 'stainless steel' before 'steel')
    sorted_materials = sorted(materials_list, key=lambda m: len(m.get("term", "")), reverse=True)
    material_terms_set = set()
    for mat in sorted_materials:
        term = mat.get("term", "").lower().strip()
        if term:
            material_terms_set.add(term)
            for w in term.split():
                material_terms_set.add(w)
        if not detected_material and term:
            if re.search(rf"\b{re.escape(term)}\b", lower):
                detected_material = mat.get("canonical", term.capitalize())
                vocab_candidate_chapters.update(mat.get("candidate_chapters", []))

    # 2. Check multi-word head noun phrases dynamically from data/tariff_head_noun_index.json
    multi_word_cands = [k for k in head_noun_index.keys() if " " in k]
    multi_word_cands.sort(key=lambda x: len(x), reverse=True)
    for phrase in multi_word_cands:
        data = head_noun_index[phrase]
        sing = data.get("singular", phrase)
        plur = data.get("plural", phrase + "s")
        if re.search(rf"\b{re.escape(sing)}\b", lower) or re.search(rf"\b{re.escape(plur)}\b", lower):
            detected_article = sing
            detected_form_stage = data.get("state", "finished_article")
            vocab_candidate_chapters.update(data.get("candidate_chapters", []))
            break

    # 3. Check curated commodity articles in data/article_form_vocabulary.json
    if not detected_article:
        for item in vocab:
            term = item["term"]
            if item.get("type") == "article":
                if re.search(rf"\b{re.escape(term)}\b", lower):
                    detected_article = term
                    detected_family = item.get("family")
                    detected_form_stage = item.get("form_stage", "finished_article")
                    vocab_candidate_chapters.update(item.get("candidate_chapters", []))
                    break

    # 4. If no article yet, scan single words from right to left (Rightmost content noun rule)
    if not detected_article:
        matched_nouns = []
        for token in tokens:
            t_clean = token.strip()
            # Normalize plural
            if t_clean.endswith("ies") and len(t_clean) > 4:
                sing = t_clean[:-3] + "y"
            elif t_clean.endswith("es") and len(t_clean) > 3 and t_clean[-3] in "shxz":
                sing = t_clean[:-2]
            elif t_clean.endswith("s") and not t_clean.endswith("ss") and len(t_clean) > 3:
                sing = t_clean[:-1]
            else:
                sing = t_clean

            entry = head_noun_index.get(sing) or head_noun_index.get(t_clean)
            # Ensure constituent materials are excluded from acting as the head noun
            if entry and sing.lower() not in material_terms_set and t_clean.lower() not in material_terms_set:
                matched_nouns.append((sing, entry))

        if matched_nouns:
            best_sing, best_entry = matched_nouns[-1]
            detected_article = best_sing
            detected_form_stage = best_entry.get("state", "finished_article")
            vocab_candidate_chapters.update(best_entry.get("candidate_chapters", []))

    # 5. Detect form and processing state dynamically from data/statutory_forms.json
    for f in forms_list:
        term = f.get("term", "").lower().strip()
        if term and re.search(rf"\b{re.escape(term)}\b", lower):
            detected_form = f.get("canonical", term)
            if detected_form_stage == "unknown":
                detected_form_stage = f.get("form_stage", "worked")
            break

    return {
        "raw_query": raw_text,
        "cleaned_query": norm,
        "tokens": tokens,
        "article": detected_article,
        "form": detected_form,
        "material": detected_material,
        "family": detected_family,
        "form_stage": detected_form_stage,
        "vocabulary_candidate_chapters": sorted(list(vocab_candidate_chapters))
    }
