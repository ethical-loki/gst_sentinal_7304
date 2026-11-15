"""
tests/test_stage1_product_intent.py
===================================
Tests for Stage 1: Universal Product Intent & Attribute Relationship Intelligence.
"""

from src.nlp.intent_extractor import IntentExtractor, LLMIntentOutput
from src.nlp.product_intent_analyzer import analyze_product_intent


def test_universal_composite_product_decomposition():
    noodles = analyze_product_intent(
        "instant noodles made from wheat flour with spices in retail packet"
    )
    assert "instant noodles" in noodles.finished_article.lower()
    assert any("wheat flour" in m.lower() for m in noodles.constituent_materials)
    assert any("spices" in i.lower() for i in noodles.ingredients_or_additives)
    assert noodles.packaging_or_presentation and "retail packet" in noodles.packaging_or_presentation.lower()
    assert noodles.processing_form and "instant" in noodles.processing_form.lower()
    assert noodles.article_search_query.lower().startswith("instant noodles")

    pump = analyze_product_intent(
        "electric centrifugal pump fitted with stainless steel impeller and copper winding for water supply"
    )
    assert "centrifugal pump" in pump.finished_article.lower()
    assert any("impeller" in c.lower() for c in pump.components_or_parts)
    assert any("copper winding" in c.lower() for c in pump.components_or_parts)
    assert pump.function_use and "water supply" in pump.function_use.lower()

    chair = analyze_product_intent("swivel office chair with leather upholstery and steel frame")
    assert "office chair" in chair.finished_article.lower()
    assert any("leather upholstery" in x.lower() for x in chair.ingredients_or_additives)

    tshirt = analyze_product_intent("knitted cotton t-shirt with plastic buttons in retail pouch")
    assert "t-shirt" in tshirt.finished_article.lower()
    assert tshirt.processing_form and "knitted" in tshirt.processing_form.lower()
    assert tshirt.packaging_or_presentation and "retail pouch" in tshirt.packaging_or_presentation.lower()

    roles = {r.role for r in noodles.attribute_relationships}
    assert "FINISHED_ARTICLE" in roles
    assert "INGREDIENT_OR_ADDITIVE" in roles
    assert "PACKAGING_OR_PRESENTATION" in roles


def test_stage1_context_aggregator_exposes_product_intent():
    from src.nlp.hsn_rag_layer import HSNRAGApplicationLayer

    layer = HSNRAGApplicationLayer()
    res = layer.stage1_context_aggregator(
        base_product="instant noodles made from wheat flour with spices in retail packet",
        user_clarification="",
    )
    assert "product_intent" in res
    pi = res["product_intent"]
    assert "instant noodles" in pi["finished_article"].lower()
    assert res["master_search_string"].lower().startswith("instant noodles")
    assert "spices" in [x.lower() for x in pi["ingredients_or_additives"]]


def test_intent_extractor_does_not_misclassify_ingredients_as_out_of_schedule():
    ext = IntentExtractor.__new__(IntentExtractor)
    ext.word_to_rows = {
        "noodles": {10, 11},
        "pasta": {10, 11},
        "chair": {50, 51},
        "chairs": {50, 51},
        "seats": {50},
        "bottle": {20},
        "bottles": {20},
    }

    # Case 1: Instant noodles with spices/wheat flour -> MUST NOT be OUT_OF_SCHEDULE
    noodle_intent = LLMIntentOutput(
        physical_product="instant noodles",
        finished_article="instant noodles",
        material="wheat flour",
        ingredients_or_additives=["spices"],
        packaging_or_presentation="retail packet",
        search_terms=["pasta", "noodles"],
        unstated_attributes=[],
        reading_confidence="clear",
    )
    outcome, reason = ext._determine_outcome_type(
        raw_query="instant noodles made from wheat flour with spices in retail packet",
        intent=noodle_intent,
        grounded_terms=["pasta", "noodles"],
        top_headings=["19 | Pasta, whether or not cooked or stuffed"],
        finished_article="instant noodles",
    )
    assert outcome == "SUCCESS", f"Unexpected outcome {outcome}: {reason}"

    # Case 2: Swivel office chair with leather upholstery -> MUST NOT be OUT_OF_SCHEDULE
    chair_intent = LLMIntentOutput(
        physical_product="office chair",
        finished_article="swivel office chair",
        material=None,
        ingredients_or_additives=["leather upholstery"],
        search_terms=["seats", "chairs"],
        unstated_attributes=[],
        reading_confidence="clear",
    )
    outcome_chair, reason_chair = ext._determine_outcome_type(
        raw_query="swivel office chair with leather upholstery",
        intent=chair_intent,
        grounded_terms=["seats", "chairs"],
        top_headings=["94 | Seats (other than those of heading 9402)"],
        finished_article="swivel office chair",
    )
    assert outcome_chair == "SUCCESS", f"Unexpected outcome {outcome_chair}: {reason_chair}"

    # Case 3: Actual out-of-schedule finished article -> MUST still be OUT_OF_SCHEDULE
    apple_intent = LLMIntentOutput(
        physical_product="fresh apples",
        finished_article="fresh apples",
        search_terms=[],
        unstated_attributes=[],
        reading_confidence="clear",
    )
    outcome_apple, _ = ext._determine_outcome_type(
        raw_query="fresh apples",
        intent=apple_intent,
        grounded_terms=[],
        top_headings=[],
        finished_article="fresh apples",
    )
    assert outcome_apple == "OUT_OF_SCHEDULE"


def test_ui_renders_stage1_product_intent_fields():
    from pathlib import Path

    for ui_rel in ("static/index.html", "frontend/index.html"):
        html = Path(ui_rel).read_text(encoding="utf-8")
        for token in (
            "data.product_intent",
            "Finished Commercial Article",
            "Ingredients / Additives",
            "Components / Parts",
            "Packaging / Presentation",
        ):
            assert token in html, f"Missing '{token}' in {ui_rel}"


def test_phase15_priority2_parenthesis_and_multi_noun_extraction():
    # Case 2: Must NOT truncate at "(" in "(FOR EXAMPLE, ...)"
    c2 = analyze_product_intent(
        "TUBES, PIPES AND HOSES, AND FITTINGS THEREFOR (FOR EXAMPLE, JOINTS, ELBOWS, FLANGES), "
        "OF PLASTICS - ARTIFICIAL GUTS (SAUSAGE CASINGS) OF HARDENED PROTEIN OR OF CELLULOSIC MATERIALS "
        "- OF ADDITION POLYMERISATION PRODUCTS (plasticised flexible polyvinyl chloride)"
    )
    assert not c2.finished_article.endswith("(")
    assert "TUBES" in c2.finished_article.upper() or "GUTS" in c2.finished_article.upper()
    assert any("for example" in r.value.lower() for r in c2.attribute_relationships)
    assert any("polyvinyl chloride" in m.lower() for m in c2.constituent_materials)

    # Case 9: Must NOT truncate at "(" in "(FOR EXAMPLE, RECTIFIERS)"
    c9 = analyze_product_intent(
        "ELECTRICAL TRANSFORMERS, STATIC CONVERTERS (FOR EXAMPLE, RECTIFIERS) AND INDUCTORS "
        "- DIP BRIDGE RECTIFIER (transformer core steel)"
    )
    assert not c9.finished_article.endswith("(")
    assert "DIP BRIDGE RECTIFIER" in c9.finished_article.upper() or "TRANSFORMERS" in c9.finished_article.upper()
    assert any("transformer core steel" in m.lower() for m in c9.constituent_materials)

    # Case 4: Multi-garment heading narrowed to specific finished article "SUITS"
    c4 = analyze_product_intent(
        "WOMEN'SOR GIRLS SUITS, ENSEMBLES, JACKETS, BLAZERS, DRESSES, SKIRTS, DIVIDED SKIRTS, "
        "TROUSERS, BIB AND BRACE OVERALLS, BREECHES AND SHORTS (OTHER THAN SWIMWEAR) - SUITS "
        "- OF OTHER TEXTILE MATERIALS - EMBROIDERED WITH LUCKNOW CHIKAN CRAFT (linen)"
    )
    assert c4.finished_article.upper() == "SUITS"
    assert "BLAZERS" not in c4.finished_article.upper()
    assert any(r.role == "STATUTORY_HEADING_CONTEXT" for r in c4.attribute_relationships)

    # Case 3: Preserves full head without breaking on "(ETHYLENE TEREPHTHALATE)"
    c3 = analyze_product_intent(
        "OTHER PLATES, SHEETS, FILM, FOIL AND STRIP, OF PLASTICS, NON-CELLULAR AND NOT REINFORCED, "
        "LAMINATED, SUPPORTED OR SIMILARLY COMBINED WITH OTHER MATERIALS - OF POLY (ETHYLENE TEREPHTHALATE) "
        "(non-cellular unreinforced plastic resin 39206210)"
    )
    assert "PLATES" in c3.finished_article.upper()
    assert not c3.finished_article.endswith("(")


