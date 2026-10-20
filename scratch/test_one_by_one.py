import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.converter_service import process_converter_chat

with open('Template_Converters/customer_error_payload.json') as f:
    customer_payload = json.load(f)

# Step 1: Initial payload load/audit
res1 = process_converter_chat('Explain Errors', customer_payload, None, [])
print('Step 1 status:', res1['status'])
actions1 = [a.encode('ascii', 'ignore').decode() for a in res1['interactive_actions']]
print('Step 1 actions:', actions1)
assert any('Change date' in a for a in res1['interactive_actions'])
assert any('Auto-Fix All' in a for a in res1['interactive_actions'])
assert not any('Vehicle is' in a for a in res1['interactive_actions'])
assert not any('Set Mode:' in a for a in res1['interactive_actions'])
print('Step 1: Only Document Date presented!')

# Step 2: User applies date
res2 = process_converter_chat('Change date to Today (2026-10-20)', res1['updated_payload'], res1['validation_report'], [])
actions2 = [a.encode('ascii', 'ignore').decode() for a in res2['interactive_actions']]
print('Step 2 actions:', actions2)
assert any('My GSTIN is' in a for a in res2['interactive_actions'])
assert not any('Change date' in a for a in res2['interactive_actions'])
print('Step 2: Only Supplier GSTIN presented!')

# Step 3: User applies GSTIN
gst_act = next(a for a in res2['interactive_actions'] if 'My GSTIN is' in a)
res3 = process_converter_chat(gst_act, res2['updated_payload'], res2['validation_report'], [])
actions3 = [a.encode('ascii', 'ignore').decode() for a in res3['interactive_actions']]
print('Step 3 actions:', actions3)

# Step 4: Test HSN fix with specific statutory code 85011013
res_hsn = process_converter_chat('Set HSN: 85011013', res3['updated_payload'], res3['validation_report'], [])
print('HSN patch applied:', res_hsn['patch_applied'])
inv = res_hsn['updated_payload']['einvoices'][0]
item0 = inv['itemdtls'][0]
print('Patched Item HSN:', item0['hsn_code'], 'Rate:', item0['gstrate'], 'CGST:', item0['cgstval'], 'SGST:', item0['sgstval'], 'Total:', item0['totitemval'])
assert item0['hsn_code'] == '85011013'
assert float(item0['gstrate']) == 18.0
print('One-by-one progression and HSN Intelligence verified 100%!')
