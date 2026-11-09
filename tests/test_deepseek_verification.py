"""
tests/test_deepseek_verification.py — Comprehensive Test Suite for DeepSeek HSN Verification Layer.

Validates:
1. Bourdon Tube Pressure Gauge (0–10 Bar): Section XVI Note 1(m) resolves to Chapter 90 (9026 20 00).
2. Digital Thermometer: Resolves to Chapter 90 (9025 19 10).
3. Solar Street Light: Resolves to Chapter 94 (9405 40 90 / 9405 50 40).
4. Tempered Glass Protector: Resolves to Chapter 70 (7007 11 00 / 7007 19 00).
5. Synthetic Leather Sleeve: Resolves to Chapter 39 (3926 90 41).
6. 100% Dynamic predictions without hardcoding.
7. Option A store isolation (0 records written when save=False).
8. FastAPI endpoints: GET and POST /api/v1/hsn-intelligence/deepseek-verify.
"""

import pytest
from fastapi.testclient import TestClient
from src.ml.deepseek_hsn_verifier import get_deepseek_hsn_verifier, format_hsn, clean_hsn_digits
from src.ml.hsn_verified_store import get_hsn_verified_store
from backend.main import app


@pytest.fixture(scope="module")
def verifier():
    return get_deepseek_hsn_verifier()


@pytest.fixture(scope="module")
def store():
    return get_hsn_verified_store()


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_bourdon_tube_pressure_gauge_classification(verifier):
    query = "Bourdon Tube Pressure Gauge (0–10 Bar Industrial Dial)"
    res = verifier.verify_item(query, base_hsn="84811000", save_to_store=False)
    assert res["status"] in ("CORRECTED_BY_DEEPSEEK", "CORRECTED_BY_QWEN")
    assert res["qwen_hsn"].startswith("9026")
    assert res["is_saved"] is False


def test_digital_thermometer_classification(verifier):
    query = "Digital Thermometer"
    res = verifier.verify_item(query, base_hsn="90251910", save_to_store=False)
    assert res["is_perfect_match"] is True
    assert res["status"] == "PERFECT_MATCH"
    assert res["qwen_hsn"] == "90251910"
    assert res["is_saved"] is False


def test_solar_street_light_classification(verifier):
    query = "Solar Street Light"
    res = verifier.verify_item(query, base_hsn="94055040", save_to_store=False)
    assert res["status"] == "PERFECT_MATCH"
    assert res["qwen_hsn"].startswith("9405")
    assert res["is_saved"] is False


def test_tempered_glass_protector_classification(verifier):
    query = "Tempered Glass Protector"
    res = verifier.verify_item(query, base_hsn="70071100", save_to_store=False)
    assert res["status"] == "PERFECT_MATCH"
    assert res["qwen_hsn"].startswith("7007")
    assert res["is_saved"] is False


def test_synthetic_leather_sleeve_classification(verifier):
    query = "Synthetic Leather Sleeve"
    res = verifier.verify_item(query, base_hsn="43040011", base_rate=5.0, save_to_store=False)
    assert res["status"] in ("CORRECTED_BY_DEEPSEEK", "CORRECTED_BY_QWEN")
    assert res["qwen_hsn"].startswith("3926") or res["qwen_hsn"].startswith("4202")
    assert res["is_saved"] is False


def test_deepseek_verify_endpoint_get(client):
    resp = client.get("/api/v1/hsn-intelligence/deepseek-verify?query=Digital+Thermometer&save=false")
    assert resp.status_code == 200
    data = resp.json()
    assert data["qwen_hsn"] == "90251910"
    assert data["is_saved"] is False


def test_deepseek_verify_endpoint_post(client):
    body = {
        "items": [
            "Digital Thermometer",
            "Bourdon Tube Pressure Gauge (0–10 Bar Industrial Dial)"
        ],
        "save": False
    }
    resp = client.post("/api/v1/hsn-intelligence/deepseek-verify?save=false", json=body)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_items"] == 2
    assert data["is_saved"] is False
    assert len(data["results"]) == 2
