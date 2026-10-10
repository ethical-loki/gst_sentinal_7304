import sys
import json

sys.stdout.reconfigure(encoding='utf-8')
from backend.converter_service import process_converter_pipeline, process_converter_chat
from scratch.test_agentic_flow import dirty_inv

# Step 1: Set category
c1 = process_converter_chat('Set Category: B2B', dirty_inv, None, [])
# Step 2: Set GSTIN
c2 = process_converter_chat('My GSTIN is 29ABCDE1234F1ZW', c1['updated_payload'], c1.get('validation_report'), [])
# Step 3: Align PIN
c3 = process_converter_chat('Fix state and pin code mismatch', c2['updated_payload'], c2.get('validation_report'), [])
# Step 4: Rebalance math
c4 = process_converter_chat('Rebalance tax math and invoice value', c3['updated_payload'], c3.get('validation_report'), [])
rep4 = process_converter_pipeline(c4['updated_payload'])
res4 = rep4['validation_report']['results'][0]
print(f"Step 4 Status: {res4['status']}, Errors: {len(res4['errors'])}")

# Step 5: User adds vehicle
c5 = process_converter_chat('Add vehicle MH12DE4567', c4['updated_payload'], rep4['validation_report'], [])
print("\nStep 5 Patches:", c5.get('patch_summary'))
rep5 = process_converter_pipeline(c5['updated_payload'])
res5 = rep5['validation_report']['results'][0]
print(f"Step 5 Status: {res5['status']}, Errors: {len(res5['errors'])}")
if len(res5['errors']) == 0:
    print(">>> SUCCESS! 100% COMPLIANT EVEN AFTER ADDING VEHICLE FOR E-WAY BILL! <<<")
else:
    for e in res5['errors']:
        print(f"  - Error [{e['error_code']}]: {e['field']} -> {e['message']}")

# Step 6: Test if user asks to Disable EWB
c6 = process_converter_chat('Disable E-Way Bill', c5['updated_payload'], rep5['validation_report'], [])
print("\nStep 6 Disable E-Way Bill Patches:", c6.get('patch_summary'))
rep6 = process_converter_pipeline(c6['updated_payload'])
res6 = rep6['validation_report']['results'][0]
print(f"Step 6 Status: {res6['status']}, Errors: {len(res6['errors'])}")
