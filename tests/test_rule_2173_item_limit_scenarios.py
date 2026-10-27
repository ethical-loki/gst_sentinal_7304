"""
Comprehensive test suite for Indian GST e-Invoicing (NIC / IRP) Error Code 2173:
"You have exceeded the limit of number of items (ItemList array maximum threshold)."

Validates all 4 statutory scenarios:
1. Exceeding Standard API Limit (> 1,000 items):
   ItemList contains 1,001 or more items via standard /Invoice endpoint.
   Fix: Cap ItemList at maximum 1,000 items or use the dedicated large invoice workflow.
   Reason: Standard IRP endpoints enforce a strict ceiling of 1,000 items per payload. Split into separate invoices if possible.

2. GSP / Middleware Restricted Threshold:
   Some ERP integrations or GSP connectors set a lower payload threshold (e.g., 250 or 500 items).
   Fix: Align payload chunking with the middleware's supported limit.
   Reason: If routing through an intermediate GSP wrapper, check if their payload buffer size is lower than NIC's native 1,000 limit.

3. Redundant Granularity / Non-Summarized Items:
   Same HSN, tax rate, and product description passed across hundreds of small sub-batches.
   Fix: Aggregate line items sharing the identical HsnCd, GstRt, and unit price into a single line item.
   Reason: Roll up line items at the ERP dispatch level to bring the overall count within permitted schema bounds.

4. Over-Limit Bulk Invoicing Edge Cases:
   Real business invoice genuinely exceeding 1,000 items that cannot be split into multiple invoices.
   Fix: Contact NIC/IRP Helpdesk or raise a support ticket with the signed invoice details.
   Reason: In exceptional cases where an invoice cannot legally be split, custom processing via NIC helpdesk approval is required.
"""

import copy
from decimal import Decimal
from typing import Dict, Any, List
import pytest
from pydantic import ValidationError

from src.ingestion.schemas import (
    InvoicePayload,
    LineItem,
    NICValidationError,
    classify_rule_2173_diagnostic,
    aggregate_redundant_line_items,
    split_invoice_payload_chunks,
)
from Template_Converters.payload_builder import PayloadBuilder
from Template_Converters.validator import GSTValidator
from src.rules.rules_engine import RulesEngine


def _make_item(slno: int, hsn: str = "84818030", prdnm: str = "Industrial Valve", qty: float = 1.0, unitprice: float = 100.0, gstrate: float = 18.0) -> Dict[str, Any]:
    gross = qty * unitprice
    assamt = gross
    cgst = round(assamt * (gstrate / 200.0), 2)
    sgst = round(assamt * (gstrate / 200.0), 2)
    tot = assamt + cgst + sgst
    return {
        "slno": str(slno),
        "prdnm": prdnm,
        "prddesc": f"{prdnm} Spec Sheet",
        "isservc": "N",
        "hsncd": hsn,
        "hsn": hsn,
        "qty": qty,
        "uqc": "NOS",
        "unit": "NOS",
        "unitrate": unitprice,
        "unitprice": unitprice,
        "grossamt": gross,
        "totamt": gross,
        "discount": 0.0,
        "pretaxval": assamt,
        "assamt": assamt,
        "assval": assamt,
        "gstrate": gstrate,
        "cgstrt": gstrate / 2.0,
        "cgstamt": cgst,
        "cgstval": cgst,
        "sgstrt": gstrate / 2.0,
        "sgstamt": sgst,
        "sgstval": sgst,
        "igstrt": 0.0,
        "igstamt": 0.0,
        "igstval": 0.0,
        "totitemval": tot,
    }


@pytest.fixture
def base_invoice_dict() -> Dict[str, Any]:
    return {
        "self_gstin": "29ABCDE1234F1Z5",
        "system_cd": "SAP_ERP",
        "branch_cd": "BLR01",
        "vertical_cd": "DOM",
        "irnreq": "Y",
        "trandt1": {
            "trancatg": "B2B",
            "reversecharge": "N",
            "transactionmode": "REG",
            "igstonintra": "N"
        },
        "docdt1": {
            "document_type": "INV",
            "docno": "INV-2026-ITM01",
            "docdt": "26-10-2026"
        },
        "supplierdt1": {
            "supplier_gstin": "29ABCDE1234F1Z5",
            "supplier_lglnm": "BHARAT TECH SOLUTIONS PVT LTD",
            "supplier_trdnm": "BHARAT TECH",
            "supplier_bno": "104",
            "supplier_bnm": "Cyber Towers",
            "supplier_flno": "4th Floor",
            "supplier_loc": "Bengaluru",
            "supplier_dst": "Bengaluru",
            "supplier_pin": "560001",
            "supplier_state": "29",
            "supplier_phone": "9876543210",
            "supplier_email": "accounts@bharattech.in"
        },
        "buyerdt1": {
            "buyer_gstin": "29XYZAB5678C1Z2",
            "buyer_lglnm": "APEX ENTERPRISES",
            "buyer_pos": "29",
            "buyer_bno": "55",
            "buyer_bnm": "Commercial Plaza",
            "buyer_loc": "Bengaluru",
            "buyer_dst": "Bengaluru",
            "buyer_pin": "560001",
            "buyer_state": "29"
        },
        "itemdtls": [_make_item(1)],
        "valdtls": {
            "assval": 100.0,
            "cgstval": 9.0,
            "sgstval": 9.0,
            "igstval": 0.0,
            "cesval": 0.0,
            "totinvval": 118.0
        }
    }


# ============================================================================
# 1. DIRECT UNIT TESTS FOR classify_rule_2173_diagnostic
# ============================================================================

def test_scenario_1_exceeding_standard_api_limit():
    """Verifies Scenario 1: Standard API Limit (> 1,000 items) is diagnosed with exact statutory fix."""
    diag = classify_rule_2173_diagnostic(item_count=1005, max_limit=1000)
    assert diag["scenario"] == "EXCEEDING_STANDARD_API_LIMIT"
    assert diag["scenario_name"] == "Exceeding Standard API Limit (> 1,000 items)"
    assert "Standard IRP endpoints enforce a strict ceiling of 1,000 items per payload" in diag["reason"]
    assert "Cap ItemList at maximum 1,000 items or use the dedicated large invoice workflow" in diag["fix"]
    assert diag["action"] == "CAP_ITEMLIST_OR_SPLIT_INVOICE"


def test_scenario_2_gsp_middleware_restricted_threshold():
    """Verifies Scenario 2: GSP / Middleware Restricted Threshold (e.g. 250 or 500 items)."""
    diag = classify_rule_2173_diagnostic(
        item_count=350,
        max_limit=1000,
        is_middleware_restricted=True,
        middleware_threshold=250
    )
    assert diag["scenario"] == "GSP_MIDDLEWARE_RESTRICTED_THRESHOLD"
    assert diag["scenario_name"] == "GSP / Middleware Restricted Threshold"
    assert "check if their payload buffer size is lower than NIC's native 1,000 limit" in diag["reason"]
    assert "Align payload chunking with the middleware's supported limit (250 items)" in diag["fix"]
    assert diag["action"] == "ALIGN_PAYLOAD_CHUNKING_TO_MIDDLEWARE"


def test_scenario_3_redundant_granularity_non_summarized():
    """Verifies Scenario 3: Redundant Granularity / Non-Summarized Items."""
    # 500 items composed of identical duplicates of 2 distinct products
    items = []
    for i in range(1, 501):
        p_name = "Ball Valve 1/2 Inch" if i % 2 == 0 else "Hex Nipple SS304"
        items.append(_make_item(i, prdnm=p_name, unitprice=50.0))

    diag = classify_rule_2173_diagnostic(
        item_count=500,
        items=items,
        max_limit=250,
        middleware_threshold=250
    )
    assert diag["scenario"] == "REDUNDANT_GRANULARITY_NON_SUMMARIZED"
    assert diag["scenario_name"] == "Redundant Granularity / Non-Summarized Items"
    assert "Roll up line items at the ERP dispatch level to bring the overall count within permitted schema bounds" in diag["reason"]
    assert "Aggregate line items sharing the identical HsnCd, GstRt, and unit price into a single line item" in diag["fix"]
    assert diag["action"] == "AGGREGATE_IDENTICAL_LINE_ITEMS"
    assert diag["consolidated_count"] == 2


def test_scenario_4_over_limit_bulk_invoicing_edge_case():
    """Verifies Scenario 4: Over-Limit Bulk Invoicing Edge Cases (Helpdesk escalation)."""
    diag = classify_rule_2173_diagnostic(
        item_count=1200,
        max_limit=1000,
        is_cannot_split_bulk=True
    )
    assert diag["scenario"] == "OVER_LIMIT_BULK_INVOICING_EDGE_CASE"
    assert diag["scenario_name"] == "Over-Limit Bulk Invoicing Edge Cases"
    assert "In exceptional cases where an invoice cannot legally be split, custom processing via NIC helpdesk approval is required" in diag["reason"]
    assert "Contact NIC/IRP Helpdesk or raise a support ticket with the signed invoice details" in diag["fix"]
    assert diag["action"] == "CONTACT_NIC_HELPDESK_SUPPORT"


# ============================================================================
# 2. UNIT TESTS FOR aggregate_redundant_line_items
# ============================================================================

def test_aggregate_redundant_line_items_math():
    """Verifies roll-up aggregation math for quantity, taxable amount, taxes, and sequential slno."""
    # 60 items: 30 of Product A, 30 of Product B
    items = []
    for i in range(1, 61):
        if i <= 30:
            items.append(_make_item(i, hsn="84818030", prdnm="Control Valve 2 Inch", qty=2.0, unitprice=100.0, gstrate=18.0))
        else:
            items.append(_make_item(i, hsn="73072100", prdnm="SS Nipple 1/2 Inch", qty=5.0, unitprice=20.0, gstrate=18.0))

    consolidated, red_count, totals = aggregate_redundant_line_items(items)
    assert len(consolidated) == 2
    assert red_count == 58

    # Product A totals: 30 * 2.0 = 60.0 qty, gross = 6000.0, cgst = 540.0, sgst = 540.0
    prod_a = consolidated[0]
    assert prod_a["slno"] == "1"
    assert prod_a["prdnm"] == "Control Valve 2 Inch"
    assert prod_a["qty"] == 60.0
    assert prod_a["totamt"] == 6000.0
    assert prod_a["assval"] == 6000.0
    assert prod_a["cgstval"] == 540.0
    assert prod_a["sgstval"] == 540.0
    assert prod_a["totitemval"] == 7080.0

    # Product B totals: 30 * 5.0 = 150.0 qty, gross = 3000.0, cgst = 270.0, sgst = 270.0
    prod_b = consolidated[1]
    assert prod_b["slno"] == "2"
    assert prod_b["prdnm"] == "SS Nipple 1/2 Inch"
    assert prod_b["qty"] == 150.0
    assert prod_b["totamt"] == 3000.0
    assert prod_b["assval"] == 3000.0
    assert prod_b["cgstval"] == 270.0
    assert prod_b["sgstval"] == 270.0
    assert prod_b["totitemval"] == 3540.0

    # Reconciled grand totals
    assert totals["assval"] == 9000.0
    assert totals["cgstval"] == 810.0
    assert totals["sgstval"] == 810.0
    assert totals["totinvval"] == 10620.0


# ============================================================================
# 3. UNIT TESTS FOR split_invoice_payload_chunks
# ============================================================================

def test_split_invoice_payload_chunks():
    """Verifies splitting an over-limit invoice into valid chunks with unique docno and balanced valdtls."""
    # 2,200 items split into chunks of 1,000
    items = [_make_item(i, prdnm=f"Item {i}", qty=1.0, unitprice=10.0) for i in range(1, 2201)]
    inv = {
        "docno": "INV-2026-BULK01",
        "docdt1": {"docno": "INV-2026-BULK01", "document_type": "INV", "docdt": "26-10-2026"},
        "itemdtls": items,
        "valdtls": {"assval": 22000.0, "totinvval": 25960.0}
    }

    chunks = split_invoice_payload_chunks(inv, chunk_size=1000)
    assert len(chunks) == 3

    # Chunk 1: 1,000 items
    assert len(chunks[0]["itemdtls"]) == 1000
    assert chunks[0]["docno"] == "INV-2026-BULK01/P1"
    assert chunks[0]["itemdtls"][0]["slno"] == "1"
    assert chunks[0]["itemdtls"][-1]["slno"] == "1000"
    assert chunks[0]["valdtls"]["assval"] == 10000.0

    # Chunk 2: 1,000 items
    assert len(chunks[1]["itemdtls"]) == 1000
    assert chunks[1]["docno"] == "INV-2026-BULK01/P2"
    assert chunks[1]["itemdtls"][0]["slno"] == "1"
    assert chunks[1]["valdtls"]["assval"] == 10000.0

    # Chunk 3: 200 items
    assert len(chunks[2]["itemdtls"]) == 200
    assert chunks[2]["docno"] == "INV-2026-BULK01/P3"
    assert chunks[2]["itemdtls"][0]["slno"] == "1"
    assert chunks[2]["itemdtls"][-1]["slno"] == "200"
    assert chunks[2]["valdtls"]["assval"] == 2000.0


# ============================================================================
# 4. INTEGRATION TESTS FOR InvoicePayload.model_validate & auto_correct_and_build
# ============================================================================

def test_invoice_payload_model_validate_rejects_over_limit(base_invoice_dict):
    """Verifies that InvoicePayload.model_validate raises NICValidationError 2173 when items > 1,000."""
    dirty = dict(base_invoice_dict)
    # Create 1,005 items
    dirty["itemdtls"] = [_make_item(i, prdnm=f"Distinct Part {i}") for i in range(1, 1006)]

    with pytest.raises((NICValidationError, ValidationError)) as exc_info:
        InvoicePayload.model_validate(dirty)

    err_str = str(exc_info.value)
    assert "2173" in err_str
    assert "exceeding the standard API limit of 1,000 items" in err_str
    assert "Standard IRP endpoints enforce a strict ceiling of 1,000 items per payload" in err_str


def test_invoice_payload_auto_correct_summarizes_redundant_items(base_invoice_dict):
    """Verifies InvoicePayload.auto_correct_and_build aggregates 1,200 redundant items to <= 1,000 items."""
    dirty = dict(base_invoice_dict)
    # 1,200 items composed of duplicates of 500 distinct items (so 2.4 duplicates per item)
    items = []
    for i in range(1, 1201):
        idx_mod = (i % 500) + 1
        items.append(_make_item(i, prdnm=f"Part Type {idx_mod}", unitprice=25.0))
    dirty["itemdtls"] = items

    model, audit_log = InvoicePayload.auto_correct_and_build(dirty)
    assert len(model.itemdtls) == 500
    assert len(model.itemdtls) <= 1000

    summarize_entry = next((l for l in audit_log if l.get("category") == "RULE_2173_ITEM_LIMIT_SUMMARIZATION"), None)
    assert summarize_entry is not None
    assert "Redundant Granularity / Non-Summarized Items" in summarize_entry["description"]
    assert "Aggregated 1200 line items into 500 summarized items" in summarize_entry["description"]


def test_invoice_payload_auto_correct_caps_excess_when_not_summarizable(base_invoice_dict):
    """Verifies InvoicePayload.auto_correct_and_build caps distinct unique items at 1,000 limit with audit log."""
    dirty = dict(base_invoice_dict)
    # 1,050 unique items that cannot be consolidated
    dirty["itemdtls"] = [_make_item(i, prdnm=f"Unique Component {i}", unitprice=float(i)) for i in range(1, 1051)]

    model, audit_log = InvoicePayload.auto_correct_and_build(dirty)
    assert len(model.itemdtls) == 1000

    exceeded_entry = next((l for l in audit_log if l.get("category") == "RULE_2173_ITEM_LIMIT_EXCEEDED"), None)
    assert exceeded_entry is not None
    assert "Exceeding Standard API Limit (> 1,000 items)" in exceeded_entry["description"]
    assert "Standard IRP endpoints enforce a strict ceiling of 1,000 items per payload" in exceeded_entry["description"]


# ============================================================================
# 5. INTEGRATION TESTS FOR PayloadBuilder.auto_correct_and_build
# ============================================================================

def test_payload_builder_auto_correct_summarizes_redundant_items(base_invoice_dict):
    """Verifies PayloadBuilder.auto_correct_and_build aggregates redundant items below threshold."""
    dirty = dict(base_invoice_dict)
    # 1,100 items with only 100 distinct products
    items = []
    for i in range(1, 1101):
        p_num = (i % 100) + 1
        items.append(_make_item(i, prdnm=f"Module Part {p_num}", unitprice=10.0))
    dirty["itemdtls"] = items

    clean_inv, audit_log = PayloadBuilder.auto_correct_and_build(dirty)
    assert len(clean_inv["itemdtls"]) == 100
    assert len(clean_inv["itemdtls"]) <= 1000

    summarize_entry = next((l for l in audit_log if l.get("category") == "RULE_2173_ITEM_LIMIT_SUMMARIZATION"), None)
    assert summarize_entry is not None
    assert "Redundant Granularity / Non-Summarized Items" in summarize_entry["description"]


def test_payload_builder_auto_correct_middleware_threshold(base_invoice_dict):
    """Verifies PayloadBuilder.auto_correct_and_build respects middleware threshold (e.g. 250 items)."""
    dirty = dict(base_invoice_dict)
    dirty["middleware_threshold"] = 250
    dirty["is_middleware_restricted"] = True
    # 300 unique items
    dirty["itemdtls"] = [_make_item(i, prdnm=f"GSP Item {i}", unitprice=float(i)) for i in range(1, 301)]

    clean_inv, audit_log = PayloadBuilder.auto_correct_and_build(dirty)
    assert len(clean_inv["itemdtls"]) == 250

    exceeded_entry = next((l for l in audit_log if l.get("category") == "RULE_2173_ITEM_LIMIT_EXCEEDED"), None)
    assert exceeded_entry is not None
    assert "GSP / Middleware Restricted Threshold" in exceeded_entry["description"]
    assert "Align payload chunking with the middleware's supported limit (250 items)" in exceeded_entry["description"]


# ============================================================================
# 6. INTEGRATION TESTS FOR GSTValidator & RulesEngine
# ============================================================================

def test_gst_validator_flags_rule_2173():
    """Verifies GSTValidator reports Error 2173 with scenario diagnostics when items > 1,000."""
    inv = {
        "docdt1": {"docno": "INV-001", "document_type": "INV", "docdt": "26-10-2026"},
        "supplierdt1": {"supplier_gstin": "29ABCDE1234F1Z5", "supplier_state": "29", "supplier_pin": "560001"},
        "buyerdt1": {"buyer_gstin": "29XYZAB5678C1Z2", "buyer_pos": "29", "buyer_state": "29", "buyer_pin": "560001"},
        "itemdtls": [_make_item(i, prdnm=f"Valve Model {i}") for i in range(1, 1005)]
    }

    errors = GSTValidator.validate_invoice(inv)
    err_2173 = next((e for e in errors if e.get("error_code") == 2173), None)
    assert err_2173 is not None
    assert "ItemList contains 1004 items, exceeding the maximum limit of 1000 items" in err_2173["message"]
    assert "Exceeding Standard API Limit (> 1,000 items)" in err_2173["message"]
    assert "Standard IRP endpoints enforce a strict ceiling of 1,000 items per payload" in err_2173["message"]


def test_rules_engine_flags_rule_2173():
    """Verifies RulesEngine reports Error 2173 with scenario diagnostics when items > 1,000."""
    inv = {
        "docdt1": {"docno": "INV-001", "document_type": "INV", "docdt": "26-10-2026"},
        "supplierdt1": {"supplier_gstin": "29ABCDE1234F1Z5", "supplier_state": "29", "supplier_pin": "560001"},
        "buyerdt1": {"buyer_gstin": "29XYZAB5678C1Z2", "buyer_pos": "29", "buyer_state": "29", "buyer_pin": "560001"},
        "itemdtls": [_make_item(i, prdnm=f"Valve Model {i}") for i in range(1, 1003)]
    }

    re = RulesEngine()
    errors = re.validate_invoice(inv)
    err_2173 = next((e for e in errors if e.get("error_code") == 2173), None)
    assert err_2173 is not None
    assert "ItemList contains 1002 items, exceeding the maximum limit of 1000 items" in err_2173["message"]
    assert "Exceeding Standard API Limit (> 1,000 items)" in err_2173["message"]
    assert "Standard IRP endpoints enforce a strict ceiling of 1,000 items per payload" in err_2173["message"]
