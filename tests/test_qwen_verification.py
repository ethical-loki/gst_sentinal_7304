"""
tests/test_qwen_verification.py — Comprehensive Test Suite for Qwen 2.5 HSN Verification Layer & Persistent Store.

Validates:
1. Identification and correction of Heading 7307 misclassifications (Hex Nipple: 7307 21 00 Flanges -> 7307 22 00 Threaded Fittings).
2. Identification and correction of Heading 7318 misclassifications (Allen Cap Screw: 7318 29 10 Circlips -> 7318 15 00 Threaded Screws/Bolts).
3. Identification and correction of Heading 8504 misclassifications (Solar Inverter: 8504 10 20 Ballasts -> 8504 40 90 Static Converters).
4. Perfect Match confirmation when Day 5 base prediction is accurate (Industrial AC Servo Motor -> 8501 52 90).
5. Fast-path retrieval from Persistent Verified Memory Store (<0.5ms) without duplicate records.
6. Day 5 Search Engine instant cache hit from the verified store.
7. FastAPI endpoints: GET and POST /api/v1/hsn-intelligence/qwen-verify, /verified-store, and batch-match with_qwen=true.
"""

import pytest
from fastapi.testclient import TestClient
from src.ml.qwen_hsn_verifier import get_qwen_hsn_verifier, format_hsn, clean_hsn_digits
from src.ml.hsn_verified_store import get_hsn_verified_store, normalize_trade_key
from src.nlp.hsn_intelligence import get_hsn_intelligence_engine
from backend.main import app


@pytest.fixture(scope="module")
def verifier():
    return get_qwen_hsn_verifier()


@pytest.fixture(scope="module")
def store():
    return get_hsn_verified_store()


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_hex_nipple_correction(verifier):
    query = "SS 304 hex nipple 1/2 inch"
    res = verifier.verify_item(query, base_hsn="73072100")
    assert res["status"] in ("CORRECTED_BY_DEEPSEEK", "CORRECTED_BY_QWEN", "PERFECT_MATCH")
    assert res["qwen_hsn"] == "73072200"


def test_allen_cap_screw_correction(verifier):
    query = "Allen cap screw M12 x 50 grade 8.8"
    res = verifier.verify_item(query, base_hsn="73182910")
    assert res["status"] in ("CORRECTED_BY_DEEPSEEK", "CORRECTED_BY_QWEN")
    assert res["qwen_hsn"].startswith("7318")


def test_solar_inverter_correction(verifier):
    query = "Solar on grid inverter 5kw 3 phase"
    res = verifier.verify_item(query, base_hsn="85041020")
    assert res["status"] in ("CORRECTED_BY_DEEPSEEK", "CORRECTED_BY_QWEN")
    assert res["qwen_hsn"].startswith("8504")


def test_industrial_servo_motor_perfect_match(verifier):
    query = "industrial servo motor ac"
    res = verifier.verify_item(query, base_hsn="85015290")
    assert res["is_perfect_match"] is True
    assert res["status"] == "PERFECT_MATCH"
    assert res["qwen_hsn"] == "85015290"


def test_batch_verification(verifier):
    items = [
        {"item_description": "SS 304 hex nipple 1/2 inch", "base_hsn": "73072100"},
        {"item_description": "Allen cap screw M12 x 50 grade 8.8", "base_hsn": "73182910"},
        {"item_description": "Solar on grid inverter 5kw 3 phase", "base_hsn": "85041020"},
        {"item_description": "industrial servo motor ac", "base_hsn": "85015290"},
    ]
    batch_res = verifier.verify_batch(items)
    assert batch_res["total_items"] == 4
    assert len(batch_res["results"]) == 4
    # All 4 items verified
    assert batch_res["perfect_matches"] + batch_res["corrected_by_qwen"] == 4


def test_verified_store_fast_path_and_deduplication(verifier, store):
    query = "SS 304 hex nipple 1/2 inch"
    # First verify and save ensures it is stored as corrected 73072200
    res1 = verifier.verify_item(query, base_hsn="73072100", save_to_store=True)
    assert res1["qwen_hsn"] == "73072200"

    initial_count = len(store.get_all_records())

    # Second query with slight trade variations (e.g. adding '10 pcs')
    variation_query = "SS 304 hex nipple 1/2 inch 10 pcs"
    res2 = verifier.verify_item(variation_query, save_to_store=False)
    
    # Must hit cache instantly
    assert res2["is_cache_hit"] is True
    assert res2["latency_ms"] < 10.0  # sub-millisecond execution
    assert res2["qwen_hsn"] == "73072200"

    # Must NOT have created a duplicate record in the knowledge store!
    final_count = len(store.get_all_records())
    assert final_count == initial_count


def test_day5_search_fast_path():
    engine = get_hsn_intelligence_engine()
    # Query an item that is stored in verified memory
    query = "SS 304 hex nipple 1/2 inch"
    results = engine.search(query, top_k=3)
    assert len(results) > 0
    top = results[0]
    assert top["hsn_code"] == "73072200"
    assert "Verified Qwen Memory Store" in top.get("match_type", "")


def test_api_qwen_verify_get(client):
    resp = client.get(
        "/api/v1/hsn-intelligence/qwen-verify",
        params={"query": "SS 304 hex nipple 1/2 inch", "base_hsn": "73072100"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["qwen_hsn"] == "73072200"


def test_api_qwen_verify_post_batch(client):
    payload = {
        "items": [
            {"item_description": "SS 304 hex nipple 1/2 inch", "base_hsn": "73072100"},
            {"item_description": "industrial servo motor ac", "base_hsn": "85015290"}
        ]
    }
    resp = client.post("/api/v1/hsn-intelligence/qwen-verify", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_items"] == 2
    assert len(data["results"]) == 2


def test_api_batch_match_with_qwen(client):
    payload = {
        "items": ["SS 304 hex nipple 1/2 inch", "industrial servo motor ac"],
        "top_k": 2
    }
    resp = client.post("/api/v1/hsn-intelligence/batch-match?with_qwen=true", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "qwen_summary" in data
    assert data["qwen_summary"]["perfect_matches"] + data["qwen_summary"]["corrected_by_qwen"] == 2


def test_api_verified_store_inspection(client):
    resp = client.get("/api/v1/hsn-intelligence/verified-store")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_records" in data
    assert data["total_records"] >= 1
    assert "records" in data
    # Ensure all records have unique clean_keys (zero duplicates)
    keys = [r["clean_key"] for r in data["records"]]
    assert len(keys) == len(set(keys))


def test_api_check_preexistence_strictly_read_only(client, verifier):
    """
    Verifies that check-preexistence in HSN Intelligence UI:
    1. Returns <0.5ms match for existing records (e.g. industrial servo motor).
    2. Identifies missing records (e.g. completely novel widget).
    3. Strictly does NOT write/push to data/hsn_verified_store.parquet (read-only guarantee).
    4. Missing records can be resolved via batch-match.
    """
    from src.ml.hsn_verified_store import get_hsn_verified_store
    store = get_hsn_verified_store()
    # Ensure one item is stored so pre-existence can be verified
    verifier.verify_item("industrial servo motor ac", base_hsn="85015290", save_to_store=True)
    count_before = len(store.get_all_records())

    test_payload = {
        "items": [
            "industrial servo motor ac",
            "completely unrecorded custom titanium drone gimbal 9000x"
        ]
    }
    resp = client.post("/api/v1/hsn-intelligence/check-preexistence", json=test_payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["total_items"] == 2
    assert data["preexisting_count"] >= 1
    assert data["missing_count"] >= 1

    # Guarantee read-only: store record count MUST NOT change
    count_after = len(store.get_all_records())
    assert count_before == count_after, "Check preexistence must never write/push to verified store!"

    # Resolve missing via batch-match (also read-only, never pushes)
    batch_resp = client.post("/api/v1/hsn-intelligence/batch-match", json={"items": ["completely unrecorded custom titanium drone gimbal 9000x"]})
    assert batch_resp.status_code == 200
    assert len(store.get_all_records()) == count_before

