import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from backend.converter_service import (
    load_default_sample_dirty,
    process_converter_pipeline,
    process_converter_chat
)

def run_multi_error_test():
    print("=== Multi-Error Test: HSN then Vehicle ===")
    sample = load_default_sample_dirty()
    
    # Intentionally ensure both HSN and vehicle errors are present
    inv = sample["einvoices"][0]
    inv["itemdtls"][0]["hsncd"] = "8"  # invalid single-digit HSN (Code 2176)
    inv["ewayreq"] = "Y"
    inv["mode_of_transport"] = "1"
    inv["veh_number"] = "INVALID_PLATE_999"  # invalid vehicle plate
    if "ewbdt1" not in inv:
        inv["ewbdt1"] = {}
    inv["ewbdt1"]["ewayreq"] = "Y"
    inv["ewbdt1"]["mode_of_transport"] = "1"
    inv["ewbdt1"]["veh_number"] = "INVALID_PLATE_999"

    # Step 0: Pipeline validation
    pipe_res = process_converter_pipeline(sample)
    rep0 = pipe_res["validation_report"]
    errs0 = rep0["results"][0]["errors"]
    print(f"Step 0 Initial Errors ({len(errs0)}):")
    for e in errs0:
        print(f"  - [{e['error_code']}] {e['field']}: {e['message']}")
    
    has_hsn_err = any("hsn" in str(e['field']).lower() or str(e['error_code']) in ['2176', '2285'] for e in errs0)
    has_veh_err = any("veh" in str(e['field']).lower() or str(e['error_code']) in ['4011', '4014', '4020', '4022'] for e in errs0)
    print(f"Has HSN error initially: {has_hsn_err}")
    print(f"Has Vehicle error initially: {has_veh_err}")
    assert has_hsn_err and has_veh_err, "Both errors should be present!"

    # Step 1: User triggers Apply & Recalculate Tax
    print("\n--- Step 1: Submitting Apply & Recalculate Tax ---")
    chat1 = process_converter_chat("Set HSN: 85011013, Rate: 10000.00, Qty: 5.0, Taxable Value: 50000.00", sample)
    print("Chat1 Patch Applied:", chat1.get("patch_applied"))
    print("Chat1 Patch Summary:", chat1.get("patch_summary"))
    print("Chat1 Actions:", chat1.get("interactive_actions"))
    
    # Verify that HSN prompt is NOT in interactive_actions
    hsn_actions = [a for a in chat1.get("interactive_actions", []) if "hsn" in a.lower()]
    print("HSN actions remaining in Chat1 response:", hsn_actions)
    assert len(hsn_actions) == 0, f"HSN actions must NOT show again! Found: {hsn_actions}"
    
    # Verify that vehicle prompt IS present now
    veh_actions = [a for a in chat1.get("interactive_actions", []) if any(k in a.lower() for k in ["vehicle", "ka01", "eway"])]
    print("Vehicle actions offered in Chat1 response:", veh_actions)
    assert len(veh_actions) > 0, "Vehicle action should be offered as next step!"

    # Step 2: User provides Vehicle Number in editable format
    print("\n--- Step 2: Submitting Vehicle Number in Editable Format ---")
    p1 = chat1["updated_payload"]
    chat2 = process_converter_chat("Vehicle is KA01AB1234, Type: R", p1)
    print("Chat2 Patch Applied:", chat2.get("patch_applied"))
    print("Chat2 Patch Summary:", chat2.get("patch_summary"))
    print("Chat2 Actions:", chat2.get("interactive_actions"))
    
    # Check remaining errors after Vehicle update
    rep2 = chat2["validation_report"]
    errs2 = rep2["results"][0]["errors"]
    print(f"Errors after Vehicle update ({len(errs2)}):")
    for e in errs2:
        print(f"  - [{e['error_code']}] {e['field']}: {e['message']}")
    
    has_veh_err_after = any("veh" in str(e['field']).lower() or str(e['error_code']) in ['4011', '4014', '4020', '4022'] for e in errs2)
    assert not has_veh_err_after, "Vehicle error should be resolved!"
    print("\nSUCCESS! Both HSN and Vehicle error transitions verified cleanly!")

if __name__ == "__main__":
    run_multi_error_test()
