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


def test_clarification_loop_trace(extractor):
    """Verifies clarification loop merges clarification and records audit trace in traces.jsonl."""
    res = extractor.extract_intent("water bottle", clarification="material: stainless steel")
    assert res.clarification_merged is True
    assert res.material is not None and "steel" in res.material.lower()
    assert "stainless steel" in (res.synthesized_search_string or "").lower()

    traces_file = Path(__file__).resolve().parent.parent / "data" / "intent_cache" / "traces.jsonl"
    assert traces_file.exists()
    with open(traces_file, "r", encoding="utf-8") as f:
        traces = [json.loads(line) for line in f if line.strip()]
    matching = [t for t in traces if t.get("prior_query") == "water bottle" or t.get("raw_query") == "water bottle"]
    assert len(matching) > 0
    assert matching[-1].get("clarification_merged") is True or matching[-1].get("event") == "clarification_loop_merge"


def test_all_terms_dropped_abstain(extractor):
    """Verifies that when all generated terms fail grounding, system marks UNRECOGNIZED without falling back to raw query."""
    fake_intent = LLMIntentOutput(
        physical_product="nonexistent_product_xyz",
        material=None,
        construction=None,
        intended_use=None,
        search_terms=["bogus term alpha", "synthetic phantom heading beta"],
        unstated_attributes=[],
        reading_confidence="clear"
    )
    g_terms, d_terms, _ = extractor.ground_intent(fake_intent)
    assert len(g_terms) == 0
    assert len(d_terms) == 2

    # Gibberish query test
    res = extractor.extract_intent("asdfghjk qwertyuiop")
    assert res.outcome_type == "UNRECOGNIZED"
    assert len(res.grounded_search_terms) == 0


def test_auto_lock_guardrails():
    """Verifies that auto-lock requires reranker score >= 0.85, margin >= 0.15, 8-digit leaf match, and no unstated ambiguity."""
    from src.search.ambiguity_controller import SmartAmbiguityController
    from src.search.hybrid_retrieval import SearchCandidate

    controller = SmartAmbiguityController()

    c1 = SearchCandidate(
        hsn_code="84713010",
        chapter_code="84",
        chapter_title="Nuclear reactors, boilers, machinery and mechanical appliances",
        heading_4digit="8471",
        heading_4digit_desc="Automatic data processing machines",
        subheading_6digit="847130",
        subheading_6digit_desc="Portable automatic data processing machines",
        tariff_item_desc="Personal computer (laptop, palmtop, etc.)",
        statutory_description="Personal computer (laptop, palmtop, etc.)",
        consumer_synonyms="laptop notebook",
        article_keywords="laptop notebook computer",
        material_keywords="",
        final_score=0.92
    )
    c2 = SearchCandidate(
        hsn_code="84713090",
        chapter_code="84",
        chapter_title="Nuclear reactors, boilers, machinery and mechanical appliances",
        heading_4digit="8471",
        heading_4digit_desc="Automatic data processing machines",
        subheading_6digit="847130",
        subheading_6digit_desc="Portable automatic data processing machines",
        tariff_item_desc="Other",
        statutory_description="Other",
        consumer_synonyms="other portable computer",
        article_keywords="portable computer",
        material_keywords="",
        final_score=0.65
    )

    card, flag = controller._evaluate_auto_lock("laptop computer", [c1, c2])
    assert flag is True
    assert card is not None
    assert card.hsn_code.replace(" ", "") == "84713010"

    # Negative test: margin too small (0.90 vs 0.85 -> margin 0.05 < 0.15)
    c2.final_score = 0.85
    card_fail, flag_fail = controller._evaluate_auto_lock("laptop computer", [c1, c2])
    assert flag_fail is False
    assert card_fail is None


def test_config_driven_thresholds():
    """Verifies that thresholds are read directly from config/intent_extraction_config.json."""
    config_file = Path(__file__).resolve().parent.parent / "config" / "intent_extraction_config.json"
    assert config_file.exists()
    with open(config_file, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    assert "thresholds" in cfg
    thresh = cfg["thresholds"]
    assert thresh.get("auto_lock_reranker_min") == 0.85
    assert thresh.get("auto_lock_margin_min") == 0.15
    assert thresh.get("statutory_chapter_threshold") == 0.50
    assert thresh.get("candidate_drop_threshold") == 0.45


def test_out_of_schedule_materials(extractor):
    """Verifies unindexed materials (glass, leather) return OUT_OF_SCHEDULE."""
    res_glass = extractor.extract_intent("glass water bottle")
    assert res_glass.outcome_type == "OUT_OF_SCHEDULE"
    assert "70" in (res_glass.error_message or "") or "schedule" in (res_glass.error_message or "").lower()

    res_leather = extractor.extract_intent("genuine leather wallet")
    assert res_leather.outcome_type == "OUT_OF_SCHEDULE"
    assert "42" in (res_leather.error_message or "") or "schedule" in (res_leather.error_message or "").lower()


