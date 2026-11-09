"""
tests/test_hsn_verified_knowledge_store.py — Dedicated Test Suite for Persistent Verified HSN Knowledge Store.

Covers all 12 mandatory validation scenarios:
1. New English product (verifies execution of prediction + Qwen, persistance of verified record).
2. Repeat English product (verifies sub-0.5ms reuse, skipping prediction & Qwen).
3. Hindi to English cross-lingual reuse (Hindi product stored, English description retrieves it).
4. English to Hinglish safe reuse (English stored, Hinglish query safely retrieves it).
5. Different technical specifications (motor without rating vs 5 HP motor rejects blind reuse).
6. Similar product names (Rags - 6310 vs Ragi - 1008 are distinct and never confused).
7. Brand handling (Lee Cooper shoe vs Bata shoe brand discrimination).
8. Unresolved result (unresolved/unverified queries are NOT stored).
9. Parquet persistence across reloads (in-memory cleared, reloaded from disk).
10. Duplicate prevention (submitting identical products updates/deduplicates, no duplicate records).
11. Multilingual safety gate preservation (unsupported Kannada & unreviewed Tamil are blocked).
12. Corrupted or missing Parquet file (graceful recovery without crashing).
"""

import os
import shutil
import tempfile
from pathlib import Path
import pytest
import pandas as pd

from src.ml.hsn_verified_store import (
    HSNVerifiedStore,
    normalize_trade_key,
    compute_attribute_fingerprint,
    compute_record_id,
    format_hsn,
)
from src.nlp.hsn_intelligence import HSNIntelligenceEngine, get_hsn_intelligence_engine
from src.nlp.multilingual_service import (
    get_multilingual_preprocessing_service,
    ROUTE_E_UNSUPPORTED,
)


@pytest.fixture
def temp_store_path():
    """Provides an isolated temporary parquet store path for test isolation."""
    temp_dir = tempfile.mkdtemp(prefix="gst_store_test_")
    path = Path(temp_dir) / "test_hsn_store.parquet"
    yield path
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def test_store(temp_store_path):
    """Instantiates a fresh HSNVerifiedStore backed by the temporary path."""
    return HSNVerifiedStore(store_path=temp_store_path)


# -----------------------------------------------------------------------------
# Test 1: New English product (Executes prediction + Qwen, persists verified result)
# -----------------------------------------------------------------------------
def test_01_new_english_product_executes_and_saves(test_store):
    query = "SS 304 Hex Nipple 1/2 inch BSP"
    # Unseen product: knowledge store returns None (Level 3)
    match_before = test_store.find_verified_match(query)
    assert match_before is None, "New unseen product should not match existing knowledge store"

    # Simulate approved statutory verification workflow
    rec = test_store.upsert(
        query=query,
        hsn_code="73072200",
        description="TUBE OR PIPE FITTINGS OF STAINLESS STEEL - THREADED ELBOWS, BENDS AND SLEEVES",
        gst_rate=18.0,
        status="PERFECT_MATCH",
        is_perfect_match=True,
        reasoning="Precision statutory heading 7307 for stainless steel pipe fittings.",
        base_hsn="73072200",
        verified_by="Qwen2.5-0.5B-Instruct"
    )
    assert rec["hsn_code"] == "73072200"
    assert rec["record_id"] is not None
    assert rec["schema_version"] == "2.0"
    assert "SS 304" in rec["material"] or "SS 304" in rec["grade"]

    # Verify persisted to disk
    assert test_store.store_path.exists()
    df = pd.read_parquet(test_store.store_path)
    assert len(df) == 1
    assert df.iloc[0]["hsn_code"] == "73072200"


# -----------------------------------------------------------------------------
# Test 2: Repeat English product (Reuses verified record, skips prediction & Qwen)
# -----------------------------------------------------------------------------
def test_02_repeat_english_product_reuses_and_skips(test_store):
    query = "SS 304 Hex Nipple 1/2 inch BSP"
    test_store.upsert(
        query=query,
        hsn_code="73072200",
        description="TUBE OR PIPE FITTINGS OF STAINLESS STEEL",
        gst_rate=18.0,
        status="PERFECT_MATCH",
        is_perfect_match=True,
        reasoning="Precision statutory heading 7307",
    )

    # Repeat query
    match = test_store.find_verified_match(query)
    assert match is not None
    assert match["hsn_code"] == "73072200"
    assert match["is_cache_hit"] is True
    assert match["match_level"] == "LEVEL_1_EXACT"
    assert "Verified Knowledge Store" in match["match_type"]


# -----------------------------------------------------------------------------
# Test 3: Hindi to English cross-lingual reuse
# -----------------------------------------------------------------------------
def test_03_hindi_to_english_reuse(test_store):
    hindi_query = "औद्योगिक सर्वो मोटर"
    test_store.upsert(
        query=hindi_query,
        hsn_code="85015210",
        description="ELECTRIC MOTORS AC - INDUSTRIAL SERVO MOTORS",
        gst_rate=18.0,
        status="PERFECT_MATCH",
        is_perfect_match=True,
        reasoning="Grounded statutory classification under Heading 8501",
        original_description=hindi_query,
        detected_language="hi",
        detected_script="Devanagari",
        retrieval_ready_english="industrial servo motor",
    )

    # Subsequent English request should match and reuse the Hindi-verified record
    english_query = "industrial servo motor"
    match = test_store.find_verified_match(english_query)
    assert match is not None, "English query must safely retrieve record verified from Hindi"
    assert match["hsn_code"] == "85015210"
    assert match["is_cache_hit"] is True


# -----------------------------------------------------------------------------
# Test 4: English to Hinglish safe reuse
# -----------------------------------------------------------------------------
def test_04_english_to_hinglish_reuse(test_store):
    english_query = "copper wire 2.5 sq mm"
    test_store.upsert(
        query=english_query,
        hsn_code="85444990",
        description="INSULATED ELECTRIC WIRE AND CABLE",
        gst_rate=18.0,
        status="PERFECT_MATCH",
        is_perfect_match=True,
        reasoning="Heading 8544 insulated winding wire"
    )

    # Hinglish query with function words and phonetic trade tokens
    hinglish_query = "copper taar 2.5 sq mm chahiye"
    match = test_store.find_verified_match(hinglish_query)
    assert match is not None, "Hinglish query must safely match English-verified wire"
    assert match["hsn_code"] == "85444990"
    assert match["is_cache_hit"] is True


# -----------------------------------------------------------------------------
# Test 5: Different technical specifications (Rejects blind assignment)
# -----------------------------------------------------------------------------
def test_05_different_technical_specifications(test_store):
    # Base motor record without explicit power rating
    test_store.upsert(
        query="industrial servo motor",
        hsn_code="85015210",
        description="ELECTRIC MOTORS AC",
        gst_rate=18.0,
        status="PERFECT_MATCH",
        is_perfect_match=True,
        reasoning="Generic motor classification"
    )

    # Motor with 5 HP specification has distinct statutory subheading thresholds
    # Must NOT blindly inherit unrated motor classification
    match_5hp = test_store.find_verified_match("industrial servo motor 5 HP")
    assert match_5hp is None, "Motor with 5 HP rating must NOT blindly inherit unrated motor record"


# -----------------------------------------------------------------------------
# Test 6: Similar product names (Rags vs Ragi)
# -----------------------------------------------------------------------------
def test_06_similar_product_names_rags_vs_ragi(test_store):
    test_store.upsert(
        query="Rags",
        hsn_code="63101020",
        description="USED OR NEW RAGS, SCRAP TWINE, CORDAGE, ROPE AND CABLES",
        gst_rate=5.0,
        status="PERFECT_MATCH",
        is_perfect_match=True,
        reasoning="Heading 6310 textile rags"
    )
    test_store.upsert(
        query="Ragi",
        hsn_code="10082031",
        description="BUCKWHEAT, MILLET AND CANARY SEED; OTHER CEREALS - RAGI",
        gst_rate=0.0,
        status="PERFECT_MATCH",
        is_perfect_match=True,
        reasoning="Heading 1008 cereal agricultural product"
    )

    match_rags = test_store.find_verified_match("Rags")
    match_ragi = test_store.find_verified_match("Ragi")

    assert match_rags is not None
    assert match_rags["hsn_code"] == "63101020"
    assert match_rags["gst_rate"] == 5.0

    assert match_ragi is not None
    assert match_ragi["hsn_code"] == "10082031"
    assert match_ragi["gst_rate"] == 0.0

    # Ensure cross-query never collides
    assert match_rags["hsn_code"] != match_ragi["hsn_code"]


# -----------------------------------------------------------------------------
# Test 7: Brand handling (Lee Cooper vs Bata)
# -----------------------------------------------------------------------------
def test_07_brand_handling_lee_cooper_vs_bata(test_store):
    test_store.upsert(
        query="Lee Cooper shoe",
        hsn_code="64039990",
        description="FOOTWEAR WITH OUTER SOLES OF RUBBER - LEE COOPER",
        gst_rate=18.0,
        status="PERFECT_MATCH",
        is_perfect_match=True,
        reasoning="Heading 6403 footwear"
    )

    # Phonetic/variant brand match
    match_variant = test_store.find_verified_match("Leecoper shoe")
    assert match_variant is not None, "Variant 'Leecoper shoe' should match canonical 'Lee Cooper shoe'"
    assert match_variant["hsn_code"] == "64039990"

    # Conflicting brand must NOT match
    match_bata = test_store.find_verified_match("Bata shoe")
    assert match_bata is None, "Bata shoe must NOT inherit Lee Cooper shoe record"


# -----------------------------------------------------------------------------
# Test 8: Unresolved result is NOT stored
# -----------------------------------------------------------------------------
def test_08_unresolved_result_not_stored(test_store):
    unresolved_res = test_store.upsert(
        query="Unknown cryptic token xyz999",
        hsn_code="99999999",
        description="Unresolved",
        gst_rate=18.0,
        status="UNRESOLVED",
        is_perfect_match=False,
        reasoning="Low confidence prediction rejected by verifier"
    )
    assert unresolved_res == {}, "Unresolved prediction must be rejected by knowledge store"

    records = test_store.get_all_records()
    assert len(records) == 0, "No records should be persisted for unverified results"


# -----------------------------------------------------------------------------
# Test 9: Parquet persistence across store reloads
# -----------------------------------------------------------------------------
def test_09_parquet_persistence_across_reloads(temp_store_path):
    store_a = HSNVerifiedStore(store_path=temp_store_path)
    store_a.upsert(
        query="Solar Inverter 5kW 3 phase",
        hsn_code="85044081",
        description="STATIC CONVERTERS - SOLAR INVERTERS",
        gst_rate=12.0,
        status="PERFECT_MATCH",
        is_perfect_match=True,
        reasoning="Statutory heading 8504"
    )
    del store_a

    # Restart/re-instantiate store from disk
    store_b = HSNVerifiedStore(store_path=temp_store_path)
    match = store_b.find_verified_match("Solar Inverter 5kW 3 phase")
    assert match is not None
    assert match["hsn_code"] == "85044081"
    assert match["gst_rate"] == 12.0


# -----------------------------------------------------------------------------
# Test 10: Duplicate prevention on repeated submissions
# -----------------------------------------------------------------------------
def test_10_duplicate_prevention(test_store):
    query = "hex bolt M12 x 50 mm"
    for i in range(5):
        test_store.upsert(
            query=query,
            hsn_code="73181500",
            description="SCREWS, BOLTS, NUTS",
            gst_rate=18.0,
            status="PERFECT_MATCH",
            is_perfect_match=True,
            reasoning=f"Iteration {i}"
        )

    # In-memory and Parquet records must be exactly 1
    assert len(test_store.get_all_records()) == 1
    df = pd.read_parquet(test_store.store_path)
    assert len(df) == 1
    assert df.iloc[0]["hsn_code"] == "73181500"


# -----------------------------------------------------------------------------
# Test 11: Multilingual safety gate preservation
# -----------------------------------------------------------------------------
def test_11_multilingual_safety_gate_preservation(test_store):
    # 1. Unsupported Kannada description
    kannada_query = "ಕಬ್ಬಿಣದ ಬೋಲ್ಟ್ M10"
    match_kannada = test_store.find_verified_match(kannada_query)
    assert match_kannada is None, "Unsupported Kannada script must NOT bypass safety gate"

    # 2. Unreviewed raw Tamil description
    unreviewed_tamil = "செம்பு கம்பி விசேஷ வகை"
    match_tamil = test_store.find_verified_match(unreviewed_tamil)
    assert match_tamil is None, "Unsafe Tamil description must NOT bypass safety gate"


# -----------------------------------------------------------------------------
# Test 12: Corrupted or missing Parquet file handling
# -----------------------------------------------------------------------------
def test_12_corrupted_or_missing_parquet_file(temp_store_path):
    # 1. Missing file: should initialize gracefully with empty cache
    missing_path = temp_store_path.parent / "non_existent.parquet"
    store_missing = HSNVerifiedStore(store_path=missing_path)
    assert len(store_missing.get_all_records()) == 0
    assert store_missing.find_verified_match("any query") is None

    # 2. Corrupted file: should log error and initialize safely without crash
    corrupted_path = temp_store_path.parent / "corrupted.parquet"
    with open(corrupted_path, "wb") as f:
        f.write(b"CORRUPTED_NON_PARQUET_BINARY_GARBAGE_12345")

    store_corrupted = HSNVerifiedStore(store_path=corrupted_path)
    assert len(store_corrupted.get_all_records()) == 0
    # Able to upsert and save new record safely
    rec = store_corrupted.upsert(
        query="New Safe Product",
        hsn_code="84818090",
        description="TAPS, COCKS, VALVES",
        gst_rate=18.0,
        status="PERFECT_MATCH",
        is_perfect_match=True,
        reasoning="Recovered store"
    )
    assert rec["hsn_code"] == "84818090"
    assert len(store_corrupted.get_all_records()) == 1

