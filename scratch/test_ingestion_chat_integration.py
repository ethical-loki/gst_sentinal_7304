import json
from backend.converter_service import process_converter_chat, load_default_sample_dirty
from src.ingestion.converter import convert_and_validate_in_memory, process_and_convert_payload

def test_ingestion_chat_integration():
    sample = load_default_sample_dirty()
    print("Sample loaded successfully, invoices count:", len(sample.get("einvoices", [])))
    
    # Test 1: Ask error question
    c1 = process_converter_chat("Why did my invoice fail?", sample, None, [])
    print("Q1 status:", c1.get("status"), "| Patch applied:", c1.get("patch_applied"))
    
    # Test 2: Apply patch via chat
    c2 = process_converter_chat("Set Category: B2B", sample, None, [])
    print("Q2 status:", c2.get("status"), "| Patch applied:", c2.get("patch_applied"))
    if c2.get("patch_applied"):
        updated = c2["updated_payload"]
        val_res = convert_and_validate_in_memory(updated)
        print("Ingestion converter status:", val_res["status"])
        print("Total invoices:", val_res["metrics"]["total_invoices"])
        print("Valid invoices:", val_res["metrics"]["valid_invoices"])
        print("Audit records:", len(val_res["audit_records"]))

if __name__ == "__main__":
    test_ingestion_chat_integration()
