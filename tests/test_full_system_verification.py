"""
Complete System Verification Test Suite for GST Sentinel.
Tests all endpoints, mappings, button actions, downloads, Copilot interactions,
and error cases across HSN search, Converter, and Ingestion Lakehouse modules.
"""

import os
import json
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from backend.main import app
from backend.converter_service import load_default_sample_dirty

client = TestClient(app)


def test_hsn_homepage_served():
    """Verify HSN search homepage is served with 200 OK and modern markup."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "HSN Code Intelligence" in resp.text
    assert "GST SENTINEL" in resp.text or "GST_Sentinel" in resp.text


def test_hsn_search_query_param():
    """Verify /api/hsn-search with ?query= returns relevant tariff items."""
    resp = client.get("/api/hsn-search?query=0101")
    assert resp.status_code == 200
    data = resp.json()
    assert "matches" in data
    assert len(data["matches"]) > 0
    first = data["matches"][0]
    assert "0101" in first["hsn_code"]
    assert "gst_rate" in first
    assert "cgst_rate" in first
    assert "sgst_rate" in first
    assert "igst_rate" in first


def test_hsn_search_q_alias_param():
    """Verify /api/hsn-search with ?q= alias parameter works identically."""
    resp = client.get("/api/hsn-search?q=horses")
    assert resp.status_code == 200
    data = resp.json()
    assert "matches" in data
    assert len(data["matches"]) > 0
    assert any("horse" in m["description"].lower() or "horse" in m["hsn_code"].lower() for m in data["matches"])


def test_hsn_search_empty_query():
    """Verify empty query returns empty matches list without error."""
    resp = client.get("/api/hsn-search?query=")
    assert resp.status_code == 200
    data = resp.json()
    assert data["matches"] == []


def test_converter_page_served():
    """Verify /converter dashboard HTML is served properly."""
    resp = client.get("/converter")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "E-Invoice & E-Way Bill Converter and Compliance Auditor" in resp.text


def test_ingestion_page_served():
    """Verify /ingestion and /lakehouse routes serve the ingestion dashboard."""
    resp1 = client.get("/ingestion")
    assert resp1.status_code == 200
    assert "text/html" in resp1.headers["content-type"]
    assert "Data Ingestion" in resp1.text or "Lakehouse" in resp1.text

    resp2 = client.get("/lakehouse")
    assert resp2.status_code == 200
    assert "text/html" in resp2.headers["content-type"]


def test_converter_sample_payload():
    """Verify /api/converter/sample returns sample dirty payload."""
    resp = client.get("/api/converter/sample")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "payload" in data
    payload = data["payload"]
    assert "einvoices" in payload or isinstance(payload, list) or "docdt1" in payload


def test_converter_generate_dirty():
    """Verify /api/converter/generate creates randomized dirty payload."""
    resp = client.post("/api/converter/generate", json={"count": 2})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["count"] == 2
    assert "payload" in data


def test_converter_process_pipeline():
    """Verify /api/converter/process runs audit and generates all 4 reports & metrics."""
    sample = load_default_sample_dirty()
    resp = client.post("/api/converter/process", json={"payload": sample})
    assert resp.status_code == 200
    data = resp.json()
    assert "metrics" in data
    assert "corrected_payload" in data
    assert "validation_report" in data
    assert "audit_records" in data
    assert "summary_text" in data
    assert "csv_content" in data
    assert data["metrics"]["total_invoices"] > 0


def test_converter_chat_copilot():
    """Verify /api/converter/chat handles compliance queries and interactive actions."""
    sample = load_default_sample_dirty()
    resp = client.post("/api/converter/chat", json={
        "message": "Why did my invoice fail?",
        "payload": sample,
        "chat_history": []
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "reply" in data
    assert len(data["reply"]) > 0
    assert "interactive_actions" in data


def test_converter_endpoints_metadata():
    """Verify /api/converter/endpoints returns configured API endpoints info."""
    resp = client.get("/api/converter/endpoints")
    assert resp.status_code == 200
    data = resp.json()
    assert "modules" in data
    assert len(data["modules"]) > 0


def test_converter_verify_gstin():
    """Verify /api/converter/verify-gstin/{gstin} validates checkum and state."""
    # Valid Modulo-36 GSTIN
    resp = client.get("/api/converter/verify-gstin/29AAACR4849R1ZH")
    assert resp.status_code == 200
    data = resp.json()
    assert "is_valid" in data
    assert data["state_code"] == "29"


def test_converter_verify_vehicle():
    """Verify /api/converter/verify-vehicle/{veh_num} validates MoRTH plate pattern."""
    resp = client.get("/api/converter/verify-vehicle/KA01AB1234")
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_valid"] is True
    assert data["state"] == "Karnataka"


def test_converter_downloads():
    """Verify /api/converter/download/{file_type} for all canonical outputs."""
    # Run process first to make sure disk outputs exist
    sample = load_default_sample_dirty()
    client.post("/api/converter/process", json={"payload": sample})

    for ftype in ["corrected", "report", "csv", "summary"]:
        resp = client.get(f"/api/converter/download/{ftype}")
        assert resp.status_code == 200, f"Download failed for {ftype}: {resp.status_code}"
        assert len(resp.content) > 0


def test_ingestion_dashboard_stats():
    """Verify /api/ingestion/stats returns top-level KPIs."""
    resp = client.get("/api/ingestion/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert "raw_files_count" in data
    assert "statutory_rules_enforced" in data
    assert data["statutory_rules_enforced"] == 28


def test_ingestion_raw_files_list():
    """Verify /api/ingestion/raw-files returns list of raw files with sizes."""
    resp = client.get("/api/ingestion/raw-files")
    assert resp.status_code == 200
    files = resp.json()
    assert isinstance(files, list)
    assert any(f["filename"] == "Final_hsn_sac_copy.xlsx" for f in files)


def test_ingestion_raw_data_content():
    """Verify /api/ingestion/raw-data returns paginated and searchable rows."""
    resp = client.get("/api/ingestion/raw-data?filename=Final_hsn_sac_copy.xlsx&page=1&page_size=10")
    assert resp.status_code == 200
    data = resp.json()
    assert data["filename"] == "Final_hsn_sac_copy.xlsx"
    assert data["page"] == 1
    assert len(data["records"]) <= 10
    assert "columns" in data


def test_ingestion_process_and_persist():
    """Verify /api/ingestion/process validates, converts, and persists to lakehouse."""
    sample = load_default_sample_dirty()
    resp = client.post("/api/ingestion/process", json={"payload": sample})
    assert resp.status_code == 200
    data = resp.json()
    assert "metrics" in data
    assert "corrected_payload" in data
    assert "validation_report" in data
    assert "lakehouse_rows_persisted" in data
    assert data["lakehouse_rows_persisted"] > 0


def test_ingestion_lakehouse_master():
    """Verify /api/ingestion/lakehouse-master returns paginated records from Parquet."""
    resp = client.get("/api/ingestion/lakehouse-master?page=1&page_size=10")
    assert resp.status_code == 200
    data = resp.json()
    assert "records" in data
    assert "total_records" in data


def test_ingestion_audit_trail():
    """Verify /api/ingestion/audit-trail returns audit trail records."""
    resp = client.get("/api/ingestion/audit-trail?page=1&page_size=25")
    assert resp.status_code == 200
    data = resp.json()
    assert "records" in data
    assert "categories" in data


def test_ingestion_downloads():
    """Verify /api/ingestion/download/{file_type} downloads files properly."""
    for ftype in ["corrected", "report", "csv", "summary", "parquet", "excel", "audit_csv"]:
        resp = client.get(f"/api/ingestion/download/{ftype}")
        assert resp.status_code == 200, f"Download failed for ingestion {ftype}: {resp.status_code}"
        assert len(resp.content) > 0
