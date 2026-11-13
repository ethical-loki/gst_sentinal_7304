"""
tests/test_intent_extractor.py
==============================
Tests for LLM-based Intent Extraction Stage.
Verifies:
1. Zero HSN Code Policy (no digit codes in LLM output).
2. Grounding against Master_copy_hsn.xlsx (4 source columns).
3. Resolution of commercial/slang queries to physical products.
4. Identification of unstated attributes without guessing.
5. Vague query handling (reading_confidence == 'unclear').
6. Intent accuracy reporting separated from retrieval accuracy.
"""

import pytest
import json
from pathlib import Path
from src.nlp.intent_extractor import IntentExtractor, DeterministicLLMClient, LLMIntentOutput


@pytest.fixture(scope="module")
def extractor():
    """Initializes IntentExtractor in deterministic mode for instant CI evaluation."""
    ext = IntentExtractor()
    ext._llm_client = DeterministicLLMClient()
    return ext


def test_zero_tariff_code_policy(extractor):
    """Ensures LLM output containing tariff codes is detected and rejected."""
    bad_raw_json = json.dumps({
        "physical_product": "laptop",
        "material": None,
        "construction": None,
        "intended_use": None,
        "search_terms": ["automatic data processing machines 8471"],
        "unstated_attributes": [],
        "reading_confidence": "clear"
    })
    parsed, err = extractor._validate_raw_response(bad_raw_json)
    assert parsed is None
    assert "Forbidden tariff code sequence detected" in err
    assert "8471" in err


def test_schema_extra_fields_rejection(extractor):
    """Ensures schema rejects unauthorized extra fields."""
    bad_extra_json = json.dumps({
        "physical_product": "laptop",
        "material": None,
        "construction": None,
        "intended_use": None,
        "search_terms": ["computer"],
        "unstated_attributes": [],
        "reading_confidence": "clear",
        "hsn_code": "8471"  # Illegal extra field
    })
    parsed, err = extractor._validate_raw_response(bad_extra_json)
    assert parsed is None
    assert "Schema validation error" in err or "Forbidden tariff code sequence" in err


def test_laptop_intent_extraction(extractor):
    """Ensures 'laptop' maps to statutory automatic data processing terms and identifies unstated attributes."""
    res = extractor.extract_intent("laptop")
    assert res.is_valid is True
    assert res.reading_confidence in ("clear", "partial")
    assert any("data processing" in t.lower() or "computer" in t.lower() or "laptop" in t.lower() for t in res.grounded_search_terms)
    assert len(res.unstated_attributes) > 0
    # Zero tariff codes in grounded terms
    for term in res.grounded_search_terms:
        assert not any(c.isdigit() for c in term)


def test_water_bottle_unstated_attributes(extractor):
    """Ensures 'water bottle' flags material and insulation as unstated attributes."""
    res = extractor.extract_intent("water bottle")
    assert res.is_valid is True
    assert "bottle" in res.physical_product.lower()
    # User did not state material or insulation, so model must list them in unstated_attributes
    unstated_str = " ".join(res.unstated_attributes).lower()
    assert "material" in unstated_str
    assert "insulation" in unstated_str or "insulated" in unstated_str


def test_stainless_steel_water_bottle(extractor):
    """Ensures 'stainless steel water bottle' grounds material to steel/stainless steel."""
    res = extractor.extract_intent("stainless steel water bottle")
    assert res.is_valid is True
    assert res.reading_confidence == "clear"
    assert res.material is not None
    assert "steel" in res.material.lower()


def test_cotton_tshirt_unstated_construction(extractor):
    """Ensures 'cotton t-shirt' flags knitted vs woven construction in unstated attributes."""
    res = extractor.extract_intent("cotton t-shirt")
    assert res.is_valid is True
    assert "cotton" in (res.material or "").lower()
    unstated_str = " ".join(res.unstated_attributes).lower()
    assert "knitted" in unstated_str or "construction" in unstated_str or "woven" in unstated_str


def test_vague_unrecognized_query(extractor):
    """Ensures vague queries ('gadget', 'aunty') are tagged reading_confidence == 'unclear'."""
    res_gadget = extractor.extract_intent("gadget")
    assert res_gadget.reading_confidence == "unclear"
    assert len(res_gadget.grounded_search_terms) == 0

    res_aunty = extractor.extract_intent("aunty")
    assert res_aunty.reading_confidence == "unclear"
    assert len(res_aunty.grounded_search_terms) == 0


def test_grounding_drops_fictional_terms(extractor):
    """Ensures terms not present in the Master file's 4 source columns are dropped."""
    fictional_intent = LLMIntentOutput(
        physical_product="vibranium quantum hyperdrive shield",
        material="unobtainium alloy",
        construction="antigravity warp",
        intended_use="interstellar teleportation",
        search_terms=["vibranium shield", "quantum hyperdrive", "unobtainium"],
        unstated_attributes=[],
        reading_confidence="clear"
    )
    grounded_terms, dropped_terms, grounded_fields = extractor.ground_intent(fictional_intent)
    assert len(grounded_terms) == 0
    assert len(dropped_terms) >= 3
    assert all("missing_words" in d.reason or "not_in_tariff" in d.reason for d in dropped_terms)


def test_intent_accuracy_benchmark_report(extractor):
    """
    Evaluates the 120-query golden benchmark dataset and calculates:
    1. Intent-Level Extraction Accuracy
    2. Retrieval Grounding Precision
    Outputs a formal evaluation report.
    """
    benchmark_file = Path(__file__).resolve().parent.parent / "data" / "golden_intent_benchmarks.json"
    with open(benchmark_file, "r", encoding="utf-8") as f:
        test_cases = json.load(f)

    intent_correct = 0
    grounding_valid = 0
    total = len(test_cases)

    for tc in test_cases:
        res = extractor.extract_intent(tc["query"])
        exp_outcome = tc.get("expected_outcome")
        exp_concept = tc.get("expected_concept")

        if exp_outcome == "UNRECOGNIZED":
            if res.reading_confidence == "unclear" or res.outcome_type == "UNRECOGNIZED":
                intent_correct += 1
                grounding_valid += 1
        elif exp_outcome == "OUT_OF_SCHEDULE":
            if res.outcome_type == "OUT_OF_SCHEDULE":
                intent_correct += 1
                grounding_valid += 1
        elif exp_outcome == "AMBIGUOUS_MATERIAL":
            if res.outcome_type == "AMBIGUOUS_MATERIAL":
                intent_correct += 1
                grounding_valid += 1
        else:
            concept_matched = True
            if exp_concept:
                concept_matched = (
                    exp_concept.lower() in res.physical_product.lower()
                    or any(exp_concept.lower() in t.lower() for t in res.grounded_search_terms)
                    or (res.material and exp_concept.lower() in res.material.lower())
                )
            if concept_matched and res.reading_confidence in ("clear", "partial") and res.outcome_type == "SUCCESS":
                intent_correct += 1
            if len(res.grounded_search_terms) > 0 or res.material:
                grounding_valid += 1

    intent_acc = (intent_correct / total) * 100
    ground_prec = (grounding_valid / total) * 100

    print("\n" + "=" * 50)
    print("INTENT EXTRACTION 120-QUERY BENCHMARK REPORT")
    print("=" * 50)
    print(f"Total Test Cases:               {total}")
    print(f"Intent Extraction Accuracy:     {intent_acc:.1f}% ({intent_correct}/{total})")
    print(f"Grounding Precision (Master):   {ground_prec:.1f}% ({grounding_valid}/{total})")
    print("=" * 50)

    assert intent_acc >= 90.0
    assert ground_prec >= 95.0

