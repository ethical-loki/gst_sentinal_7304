"""
tests/test_gemini_extractor.py — Comprehensive Unit & Integration Tests for Gemini Multi-Head Extractor.

Verifies:
1. 4-Head Linguistic Intent Decomposition:
   - Head 1: Core Entity Noun
   - Head 2: Constituent Material Composition
   - Head 3: Manufacturing Form / Physical State
   - Head 4: Functional Application / End-Use Intent
2. 4-Stage Customs Taxonomy Hierarchy Navigation:
   - Stage 1: Chapter 01–99
   - Stage 2: 4-digit Heading
   - Stage 3: 6-digit Subheading
   - Stage 4: 8-digit CBIC Statutory Tariff Line
3. Zero Hardcoding Compliance:
   - All results evaluated dynamically over data/raw/HSN_SAC (1).xlsx
4. Statutory Tax Integrity:
   - GST tax rate strictly None / null
5. FastAPI REST API Endpoint:
   - POST & GET /api/v1/hsn-gemini/extract-and-predict
"""

import pytest
from fastapi.testclient import TestClient
from src.nlp.gemini_hsn_extractor import get_gemini_hsn_extractor, GeminiHSNExtractor
from backend.main import app

client = TestClient(app)


@pytest.fixture(scope="module")
def extractor() -> GeminiHSNExtractor:
    return get_gemini_hsn_extractor()


def test_gemini_aerospace_hex_bolt(extractor: GeminiHSNExtractor):
    """
    Case 1: User's Aerospace Fastener Query:
    'High-tensile stainless steel hex bolts for aerospace frames'
    Expected:
      - Chapter 73 (Articles of iron or steel)
      - Heading 7318 (Screws, bolts, nuts...)
      - Subheading 7318 15
      - Tariff 7318 15 00
      - GST Rate strictly None
    """
    q = "High-tensile stainless steel hex bolts for aerospace frames"
    res = extractor.extract_and_predict(q)

    # 1. Multi-head decomposition
    assert "Bolt" in res.multi_head.head1_core_entity or "Fastener" in res.multi_head.head1_core_entity
    assert "Stainless Steel" in res.multi_head.head2_material_composition
    assert "Threaded" in res.multi_head.head3_manufacturing_form or "Hexagonal" in res.multi_head.head3_manufacturing_form
    assert "Aerospace" in res.multi_head.head4_end_use_intent

    # 2. Taxonomy Hierarchy
    trace = res.taxonomy_trace
    assert trace.stage1_chapter == "73"
    assert trace.stage2_heading == "7318"
    assert trace.stage3_subheading.replace(" ", "").startswith("731815")
    assert trace.stage4_tariff_item == "7318 15 00"
    assert "SCREWS, BOLTS" in trace.stage4_tariff_description.upper()
    assert trace.gst_rate is None


def test_gemini_action_figure_stormtrooper(extractor: GeminiHSNExtractor):
    """
    Case 2: User's Action Figure Query:
    'Star Wars Imperial Stormtrooper 6-Inch Articulated Action Figure. Highly detailed,
    injection-molded PVC plastic scale model with 18 points of articulation and interchangeable accessories.'
    Expected:
      - Chapter 95 (Toys, games and sports requisites)
      - Heading 9503 (Tricycles, dolls, scale models, puzzles)
      - Tariff 9503 00 30 (Reduced-size scale models... of plastics)
      - GST Rate strictly None
    """
    q = (
        "Star Wars Imperial Stormtrooper 6-Inch Articulated Action Figure. "
        "Highly detailed, injection-molded PVC plastic scale model with 18 points of articulation "
        "and interchangeable accessories. A collector-grade display piece."
    )
    res = extractor.extract_and_predict(q)

    # 1. Multi-head decomposition
    assert "Scale Model" in res.multi_head.head1_core_entity or "Action Figure" in res.multi_head.head1_core_entity
    assert "Plastics" in res.multi_head.head2_material_composition or "Polymers" in res.multi_head.head2_material_composition
    assert "Scale Model" in res.multi_head.head3_manufacturing_form or "Injection-Molded" in res.multi_head.head3_manufacturing_form

    # 2. Taxonomy Hierarchy
    trace = res.taxonomy_trace
    assert trace.stage1_chapter == "95"
    assert trace.stage2_heading == "9503"
    assert trace.stage4_tariff_item in ("9503 00 30", "9503 49 30")
    assert "PLASTICS" in trace.stage4_tariff_description.upper()
    assert trace.gst_rate is None


def test_gemini_cotton_hoodie(extractor: GeminiHSNExtractor):
    """
    Case 3: Cosplay Apparel Query:
    'Genshin Impact Official Cosplay Oversized Cotton Hoodie'
    Expected:
      - Chapter 61 (Articles of apparel and clothing accessories, knitted or crocheted)
      - Heading 6110 (Jerseys, pullovers, cardigans... knitted or crocheted)
      - Tariff 6110 20 00 (Of cotton)
      - GST Rate strictly None
    """
    q = "Genshin Impact Official Cosplay Oversized Cotton Hoodie"
    res = extractor.extract_and_predict(q)

    assert "Hoodie" in res.multi_head.head1_core_entity or "Pullover" in res.multi_head.head1_core_entity
    assert "Cotton" in res.multi_head.head2_material_composition

    trace = res.taxonomy_trace
    assert trace.stage1_chapter == "61"
    assert trace.stage2_heading == "6110"
    assert trace.stage4_tariff_item == "6110 20 00"
    assert "COTTON" in trace.stage4_tariff_description.upper()
    assert trace.gst_rate is None


def test_gemini_chamomile_herbal_tea(extractor: GeminiHSNExtractor):
    """
    Case 4: Botanical / Herbal Query:
    'Dried chamomile blossoms packaged for herbal tea'
    Expected:
      - Chapter 12 (Industrial or medicinal plants)
      - Heading 1211 (Plants and parts of plants... dried)
      - GST Rate strictly None
    """
    q = "Dried chamomile blossoms packaged for herbal tea"
    res = extractor.extract_and_predict(q)

    assert "Tea" in res.multi_head.head1_core_entity or "Leaves" in res.multi_head.head1_core_entity
    trace = res.taxonomy_trace
    assert trace.stage1_chapter == "12"
    assert trace.stage2_heading == "1211"
    assert trace.gst_rate is None


def test_gemini_seamless_pipe_7304(extractor: GeminiHSNExtractor):
    """
    Case 5: Seamless Stainless Steel Pipe (Heading 7304 from Final_Copy_hsn_7304.xlsx):
    'Seamless stainless steel line pipe for high-pressure oil transmission pipelines'
    Expected:
      - Chapter 73 (Articles of iron or steel)
      - Heading 7304 (Tubes, pipes and hollow profiles, seamless)
      - Subheading 7304 11 (Of stainless steel)
      - Tariff 7304 11 10 (Line pipe... tubes and pipes)
      - GST Rate strictly None
    """
    q = "Seamless stainless steel line pipe for high-pressure oil transmission pipelines"
    res = extractor.extract_and_predict(q)

    assert "Pipe" in res.multi_head.head1_core_entity or "Tube" in res.multi_head.head1_core_entity
    assert "Stainless Steel" in res.multi_head.head2_material_composition
    assert "Seamless" in res.multi_head.head3_manufacturing_form

    trace = res.taxonomy_trace
    assert trace.stage1_chapter == "73"
    assert trace.stage2_heading == "7304"
    assert trace.stage3_subheading.replace(" ", "") == "730411"
    assert trace.stage4_tariff_item == "7304 11 10"
    assert "SEAMLESS" in trace.stage4_tariff_description.upper()
    assert trace.gst_rate is None


def test_gemini_rest_api_endpoint():
    """
    Case 5: Verification of FastAPI /api/v1/hsn-gemini/extract-and-predict endpoint
    """
    payload = {
        "product_description": "High-tensile stainless steel hex bolts for aerospace frames"
    }
    response = client.post("/api/v1/hsn-gemini/extract-and-predict", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["query"] == payload["product_description"]
    assert "multi_head" in data
    assert "taxonomy_trace" in data
    assert data["taxonomy_trace"]["stage1_chapter"] == "73"
    assert data["taxonomy_trace"]["stage2_heading"] == "7318"
    assert data["taxonomy_trace"]["stage4_tariff_item"] == "7318 15 00"
    assert data["taxonomy_trace"]["gst_rate"] is None

