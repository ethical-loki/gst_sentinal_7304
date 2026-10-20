import sys, os, json
sys.path.insert(0, os.path.abspath('.'))
sys.stdout.reconfigure(encoding='utf-8')
from backend.converter_service import process_converter_chat, generate_random_dirty

print("==================================================")
print("RUNNING LIVE COMPLIANCE COPILOT STEP-BY-STEP TEST")
print("==================================================")

with open('dirty_customer_input.json', 'r', encoding='utf-8') as f:
    dirty = json.load(f)

# Step 0: User starts diagnosis
r0 = process_converter_chat("Why did my invoice fail?", raw_payload=dirty)
p0 = r0.get('updated_payload') or dirty
actions0 = r0.get('interactive_actions', [])
print("\n[STEP 0: INITIAL AUDIT]")
print("Actions returned:", actions0)
assert any('date' in a.lower() for a in actions0), "Step 0 must ask for date"

# Step 1: User changes date
r1 = process_converter_chat("Change date to Today (2026-10-20)", raw_payload=p0)
p1 = r1.get('updated_payload') or p0
actions1 = r1.get('interactive_actions', [])
print("\n[STEP 1: AFTER DATE FIX]")
print("Patch summary:", r1.get('patch_summary'))
print("Next Actions:", actions1)
assert r1.get('patch_applied'), "Date patch must be applied"

# Step 2: User asks for Vehicle number or next step
r2 = process_converter_chat("Add vehicle number for E-Way Bill", raw_payload=p1)
p2 = r2.get('updated_payload') or p1
actions2 = r2.get('interactive_actions', [])
print("\n[STEP 2: VEHICLE INQUIRY]")
print("Patch applied?:", r2.get('patch_applied'))
print("Next Actions:", actions2)
assert any('vehicle' in a.lower() for a in actions2), "Vehicle inquiry must return vehicle interactive actions"

# Step 3: User submits Vehicle in editable format
r3 = process_converter_chat("Vehicle is KA01AB1234, Type: R, Subsupply: 1", raw_payload=p2)
p3 = r3.get('updated_payload') or p2
actions3 = r3.get('interactive_actions', [])
print("\n[STEP 3: AFTER VEHICLE SUBMISSION]")
print("Patch summary:", r3.get('patch_summary'))
print("Next Actions:", actions3)
assert r3.get('patch_applied'), "Vehicle patch must be applied"
assert any('vehicle' in s.lower() for s in r3.get('patch_summary', [])), "Vehicle must be in patch summary"

# Step 4: User updates HSN & Recalculates Tax
r4 = process_converter_chat("Set HSN: 85011013, Rate: 10000.00, Qty: 5.0, Taxable Value: 50000.00", raw_payload=p3)
p4 = r4.get('updated_payload') or p3
actions4 = r4.get('interactive_actions', [])
print("\n[STEP 4: AFTER HSN & TAX RECALCULATION]")
print("Patch summary:", r4.get('patch_summary'))
print("Next Actions:", actions4)
assert r4.get('patch_applied'), "HSN patch must be applied"
assert any('hsn' in s.lower() for s in r4.get('patch_summary', [])), "HSN must be in patch summary"

print("\n==================================================")
print("ALL LIVE CHAT TESTS PASSED SUCCESSFULLY!")
print("==================================================")
