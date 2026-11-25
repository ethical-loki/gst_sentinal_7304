"""
System Verification Test Suite for GST Sentinel (Core Three-Stage HSN Engine).
Tests homepage serving, removed independent routes returning 404, and active
three-stage HSN API endpoints.
"""

from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_hsn_homepage_served():
    """Verify HSN homepage is served with 200 OK and modern markup."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "HSN Code Intelligence" in resp.text
    assert "GST SENTINEL" in resp.text or "GST_Sentinel" in resp.text
    assert "view-qwen" not in resp.text
    assert "DeepSeek-V4 Neural Verifier" not in resp.text


def test_removed_independent_routes_not_registered():
    """Verify legacy/independent supporting endpoints are removed from the API."""
    assert client.get("/api/hsn-search?query=horses").status_code == 404
    assert client.post("/api/v1/hsn-intelligence/deepseek-verify", json={"query": "steel pipe"}).status_code == 404
    assert client.post("/api/v1/audit-sentinel/audit-item", json={}).status_code == 404
    assert client.post("/api/chapter-predict", json={"product_name": "coffee"}).status_code == 404


def test_three_stage_step1_and_stage2_adaptive_endpoints():
    """Verify active Stage 1 context aggregator and Stage 2/3 adaptive endpoints work end-to-end."""
    s1_resp = client.post(
        "/api/v1/hsn-rag/step1-context-aggregator",
        json={"product": "stainless steel hexagonal bolts"},
    )
    assert s1_resp.status_code == 200
    s1_data = s1_resp.json()
    assert s1_data.get("status") == "success"
    assert "stage1_result" in s1_data

    s2_resp = client.post(
        "/api/v1/hsn-v2/classify-adaptive",
        json={"product": "stainless steel hexagonal bolts", "stage1_result": s1_data["stage1_result"]},
    )
    assert s2_resp.status_code == 200
    s2_data = s2_resp.json()
    assert "candidates" in s2_data
    assert len(s2_data["candidates"]) > 0


def test_empty_product_validation():
    """Verify empty product payload fails cleanly with 400."""
    assert client.post("/api/v1/hsn-rag/step1-context-aggregator", json={"product": ""}).status_code == 400
    assert client.post("/api/v1/hsn-v2/classify-adaptive", json={"product": ""}).status_code == 400
