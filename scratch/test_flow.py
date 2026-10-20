import sys
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from backend.converter_service import (
    load_default_sample_dirty,
    process_converter_pipeline,
    process_converter_chat
)

def run_test():
    print("=== STEP 1: Load Sample Dirty ===")
    sample = load_default_sample_dirty()
    print("Initial items count:", len(sample["einvoices"][0]["itemdtls"]))
    print("Initial HSN:", sample["einvoices"][0]["itemdtls"][0].get("hsncd"))
    print("Initial Vehicle:", sample["einvoices"][0].get("veh_number"))

    pipeline_res = process_converter_pipeline(sample)
    print("Initial Compliance Rate:", pipeline_res["metrics"]["compliance_rate"])
    rep = pipeline_res["validation_report"]
    errs = rep["results"][0]["errors"]
    print("Errors count:", len(errs))
    for e in errs:
        print(f"  - [{e['error_code']}] {e['field']}: {e['message']}")

    print("\n=== STEP 2: Chat: Apply & Recalculate Tax (HSN) ===")
    chat1_input = "Set HSN: 85011013, Rate: 10000.00, Qty: 5.0, Taxable Value: 50000.00"
    chat1_res = process_converter_chat(chat1_input, sample)
    print("Chat1 Patch Applied:", chat1_res.get("patch_applied"))
    print("Chat1 Patch Summary:", chat1_res.get("patch_summary"))
    print("Chat1 Interactive Actions:", chat1_res.get("interactive_actions"))
    
    # Check if HSN is in interactive actions
    hsn_in_actions = any("hsn" in a.lower() for a in chat1_res.get("interactive_actions", []))
    print("HSN in actions after fix?:", hsn_in_actions)
    assert not hsn_in_actions, "ERROR: HSN action should not be presented again!"

    # Check remaining errors
    rep1 = chat1_res.get("validation_report", {})
    errs1 = (rep1.get("results") or [{}])[0].get("errors", [])
    print("Remaining errors after HSN fix count:", len(errs1))
    for e in errs1:
        print(f"  - [{e['error_code']}] {e['field']}: {e['message']}")

    print("\n=== STEP 3: Chat: Vehicle Update in Editable Format ===")
    updated_payload = chat1_res["updated_payload"]
    chat2_input = "Vehicle is KA01AB1234, Type: R"
    chat2_res = process_converter_chat(chat2_input, updated_payload)
    print("Chat2 Patch Applied:", chat2_res.get("patch_applied"))
    print("Chat2 Patch Summary:", chat2_res.get("patch_summary"))
    print("Chat2 Interactive Actions:", chat2_res.get("interactive_actions"))

    rep2 = chat2_res.get("validation_report", {})
    errs2 = (rep2.get("results") or [{}])[0].get("errors", [])
    print("Remaining errors after Vehicle fix count:", len(errs2))
    for e in errs2:
        print(f"  - [{e['error_code']}] {e['field']}: {e['message']}")
    
    if len(errs2) == 0:
        print("\nSUCCESS! Invoice is now 100% compliant!")

if __name__ == "__main__":
    run_test()
