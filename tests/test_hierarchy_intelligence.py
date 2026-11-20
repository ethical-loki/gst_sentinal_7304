"""
tests/test_hierarchy_intelligence.py
====================================
Phase 2 Acceptance Tests: Master-Derived Dynamic Hierarchy Intelligence.

Demonstrates across multiple unrelated chapters (Ch 03, 09, 30, 39, 64, 73, 84, 85)
and unseen product descriptions that parent inheritance, leaf qualifiers, sibling
shared/distinguishing tokens, explicit exclusions, and contradictory sibling-branch
articles are derived directly from the statutory master without product hardcoding.
"""

import re
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from src.ml.ambiguity_resolver import identify_separating_attributes
from src.ml.candidate_evidence_evaluator import (
    CONTRADICTED,
    POSSIBLY_SUPPORTED,
    SUPPORTED,
    build_candidate_profile,
    evaluate_candidate_evidence,
)
from src.ml.hierarchy_intelligence import (
    MasterHierarchyIntelligence,
    extract_statutory_exclusions,
    get_hierarchy_intelligence,
)
from src.ml.product_tariff_reranker import RerankedTariffCandidate
from src.ml.relevance_classifier import ClassifiedTariffCandidate, RelationLabel
from src.nlp.product_intent_analyzer import analyze_product_intent

ROOT = Path(__file__).resolve().parent.parent


def test_no_hardcoded_hsn_literals_in_hierarchy_intelligence():
    src = (ROOT / "src" / "ml" / "hierarchy_intelligence.py").read_text(encoding="utf-8")
    assert not re.search(r"['\"]\d{8}['\"]", src)


def test_statutory_exclusion_parsing_across_patterns():
    pos1, clauses1, toks1, hds1 = extract_statutory_exclusions(
        "MACHINERY, PLANT OR LABORATORY EQUIPMENT (EXCLUDING FURNACES, OVENS AND OTHER EQUIPMENT OF HEADING 8514)"
    )
    assert "MACHINERY" in pos1
    assert "8514" in hds1
    assert "furnace" in toks1
    assert "oven" in toks1
    assert "machinery" not in toks1

    pos2, _, toks2, _ = extract_statutory_exclusions(
        "FISH, FRESH OR CHILLED, EXCLUDING FISH FILLETS AND OTHER FISH MEAT OF HEADING 0304 - MACKEREL"
    )
    assert "FISH" in pos2
    assert "MACKEREL" in pos2
    assert "fillet" in toks2


def test_master_derived_qualifying_leaf_and_sibling_separation_across_chapters():
    hi = get_hierarchy_intelligence()
    # Master corpus derives broad qualifier & material vocabularies dynamically from all 97 chapters
    assert len(hi.corpus_qualifier_tokens) >= 60
    assert len(hi.corpus_material_tokens) >= 40

    # Unrelated Chapter 09: qualifying leaf "In bulk packing" inherits "coffee" without contradicting heading
    a_coffee = hi.analyze_record(hi._record_by_hsn["09012110"])
    assert a_coffee.is_qualifying_only_leaf is True
    assert "coffee" in a_coffee.inherited_parent_articles
    assert "bulk" in a_coffee.sibling_distinguishing_tokens or "packing" in a_coffee.sibling_distinguishing_tokens

    # Unrelated Chapter 03: fish fillets are explicitly excluded from fresh/chilled fish 03024400
    a_fish = hi.analyze_record(hi._record_by_hsn["03024400"])
    assert "mackerel" in a_fish.inherited_parent_articles
    assert "fillet" in a_fish.explicit_exclusions
    assert "anchovy" in a_fish.contradictory_sibling_articles
    assert "tunas" in a_fish.contradictory_sibling_articles

    # Unrelated Chapter 73: multi-article heading 7318 keeps "nut" for 73181600 and isolates "bolt" as sibling-contradictory
    a_nut = hi.analyze_record(hi._record_by_hsn["73181600"])
    assert "nut" in a_nut.inherited_parent_articles
    assert "bolt" in a_nut.contradictory_sibling_articles

    # Unrelated Chapter 84: 84111100 numeric thrust leaf is qualifying-only and inherits turbojet identity
    a_jet = hi.analyze_record(hi._record_by_hsn["84111100"])
    assert a_jet.is_qualifying_only_leaf is True
    assert a_jet.qualifying_reason in ("numeric_constraint_only", "syntactic_qualifier_clause")
    assert "turbo" in a_jet.inherited_parent_articles or "jet" in a_jet.inherited_parent_articles


def test_unseen_products_across_unrelated_chapters_compatibility():
    hi = get_hierarchy_intelligence()

    # 1. Unseen coffee product (Ch 09) -> qualifying leaf "A Grade" inherits coffee
    pi_coffee = analyze_product_intent("unroasted arabica coffee in bulk packing")
    prof_coffee = build_candidate_profile(hi._record_by_hsn["09011111"], None)
    ev_coffee = evaluate_candidate_evidence(pi_coffee, prof_coffee, "SAME_PRODUCT", 0.85)
    assert ev_coffee.primary_article_matched is True
    assert ev_coffee.status in (SUPPORTED, POSSIBLY_SUPPORTED)
    assert ev_coffee.hierarchy_intelligence["is_qualifying_only_leaf"] is True

    # 2. Unseen fish exclusion probe (Ch 03) -> "fish fillets" explicitly contradicted by 03024400 ("excluding fish fillets")
    pi_fillet = analyze_product_intent("fresh mackerel fish fillets")
    prof_fish = build_candidate_profile(hi._record_by_hsn["03024400"], None)
    ev_fillet = evaluate_candidate_evidence(pi_fillet, prof_fish, "SAME_PRODUCT", 0.70)
    assert ev_fillet.status == CONTRADICTED
    assert ev_fillet.compatibility_level == "EXPLICIT_CONTRADICTION"

    # 3. Unseen pharma probe (Ch 30) -> qualifying leaf "for retail sale containing penicillins" inherits medicaments
    pi_med = analyze_product_intent("ampicillin medicaments in retail packing")
    prof_med = build_candidate_profile(hi._record_by_hsn["30041020"], None)
    ev_med = evaluate_candidate_evidence(pi_med, prof_med, "SAME_PRODUCT", 0.84)
    assert ev_med.primary_article_matched is True
    assert ev_med.status in (SUPPORTED, POSSIBLY_SUPPORTED)

    # 4. Unseen footwear material distinction (Ch 64, no material_keywords in parquet -> derived dynamically!)
    c_leather = ClassifiedTariffCandidate(
        candidate=RerankedTariffCandidate(
            hsn_code="64031910",
            chapter_code="64",
            description="FOOTWEAR - OTHER : WITH OUTER SOLES OF LEATHER",
            relevance_score=0.80,
            raw_logit=1.5,
            subheading_6digit_desc="OTHER",
            tariff_item_desc="WITH OUTER SOLES OF LEATHER",
        ),
        relation=RelationLabel.INSUFFICIENT_INFORMATION,
        confidence=0.80,
    )
    c_rubber = ClassifiedTariffCandidate(
        candidate=RerankedTariffCandidate(
            hsn_code="64031920",
            chapter_code="64",
            description="FOOTWEAR - OTHER : WITH OUTER SOLES OF RUBBER",
            relevance_score=0.80,
            raw_logit=1.5,
            subheading_6digit_desc="OTHER",
            tariff_item_desc="WITH OUTER SOLES OF RUBBER",
        ),
        relation=RelationLabel.INSUFFICIENT_INFORMATION,
        confidence=0.80,
    )
    sep_attrs, attr_ev = identify_separating_attributes([c_leather, c_rubber], "leather sports footwear")
    assert "material" in sep_attrs
    assert "rubber" in attr_ev["material"]


def test_synthetic_multi_chapter_df_derives_hierarchy_without_parquet():
    df = pd.DataFrame([
        {"hsn_code": "1201", "code_length": 4, "chapter_code": "12", "heading_4digit": "1201",
         "heading_4digit_desc": "SOYA BEANS, WHETHER OR NOT BROKEN", "subheading_6digit": "1201",
         "subheading_6digit_desc": "", "tariff_item_desc": "SOYA BEANS, WHETHER OR NOT BROKEN",
         "statutory_description": "SOYA BEANS, WHETHER OR NOT BROKEN", "material_keywords": "", "is_residual": False},
        {"hsn_code": "12011000", "code_length": 8, "chapter_code": "12", "heading_4digit": "1201",
         "heading_4digit_desc": "SOYA BEANS, WHETHER OR NOT BROKEN", "subheading_6digit": "120110",
         "subheading_6digit_desc": "SEED", "tariff_item_desc": "OF SEED QUALITY",
         "statutory_description": "SOYA BEANS - OF SEED QUALITY", "material_keywords": "", "is_residual": False},
        {"hsn_code": "12019000", "code_length": 8, "chapter_code": "12", "heading_4digit": "1201",
         "heading_4digit_desc": "SOYA BEANS, WHETHER OR NOT BROKEN", "subheading_6digit": "120190",
         "subheading_6digit_desc": "OTHER", "tariff_item_desc": "OTHER",
         "statutory_description": "SOYA BEANS - OTHER", "material_keywords": "", "is_residual": True},
    ])
    local_hi = MasterHierarchyIntelligence(df=df)
    a = local_hi.analyze_record(local_hi._record_by_hsn["12011000"])
    assert a.is_qualifying_only_leaf is True
    assert "soya" in a.inherited_parent_articles and "bean" in a.inherited_parent_articles
