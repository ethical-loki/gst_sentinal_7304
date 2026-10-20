import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.converter_service import process_converter_chat

with open('Template_Converters/customer_error_payload.json') as f:
    customer_payload = json.load(f)

print('=== TESTING ALL FIELD UPDATES FROM INLINE BOXES ===')

# 1. Test Date Update
print('\n[1] Testing Document Date Update:')
r_date = process_converter_chat('Change date to 2026-10-20', customer_payload, None, [])
assert r_date['patch_applied'] is True
inv = r_date['updated_payload']['einvoices'][0]
assert inv.get('docdt') == '2026-10-20'
assert inv.get('docdt1', {}).get('docdt') == '2026-10-20'
print('  [OK] Document Date updated successfully to 2026-10-20')

# 2. Test Supplier GSTIN with checksum mismatch (user typed 29ABCDE1234F1Z5)
print('\n[2] Testing Supplier GSTIN with user-typed value 29ABCDE1234F1Z5:')
r_gstin = process_converter_chat('My GSTIN is 29ABCDE1234F1Z5', r_date['updated_payload'], r_date['validation_report'], [])
assert r_gstin['patch_applied'] is True
inv = r_gstin['updated_payload']['einvoices'][0]
gst_val = inv.get('supplier_gstin') or inv.get('self_gstin')
print(f'  Supplier GSTIN in payload: {gst_val}')
assert gst_val == '29ABCDE1234F1ZW'
assert inv.get('supplier_state') == '29'
assert inv.get('supplierdt1', {}).get('supplier_gstin') == '29ABCDE1234F1ZW'
print('  [OK] Supplier GSTIN updated & auto-corrected modulo-36 checksum to 29ABCDE1234F1ZW')

# 3. Test Supplier GSTIN with 14 chars
print('\n[3] Testing Supplier GSTIN with 14 characters:')
r_gstin14 = process_converter_chat('My GSTIN is 29ABCDE1234F1Z', customer_payload, None, [])
assert r_gstin14['patch_applied'] is True
inv14 = r_gstin14['updated_payload']['einvoices'][0]
gst_val14 = inv14.get('supplier_gstin') or inv14.get('self_gstin')
assert gst_val14 == '29ABCDE1234F1ZW'
print('  [OK] 14-char GSTIN automatically completed and applied!')

# 4. Test Product HSN update (Set HSN: 85011013)
print('\n[4] Testing Product HSN Update (Set HSN: 85011013):')
r_hsn = process_converter_chat('Set HSN: 85011013', r_gstin['updated_payload'], r_gstin['validation_report'], [])
assert r_hsn['patch_applied'] is True
inv = r_hsn['updated_payload']['einvoices'][0]
item0 = inv['itemdtls'][0]
assert item0.get('hsn') == '85011013'
assert item0.get('hsn_code') == '85011013'
assert item0.get('hsncd') == '85011013'
print('  [OK] Product HSN updated across hsn, hsn_code, and hsncd to 85011013')

# 5. Test Supplier PIN Update (Set Supplier PIN: 560001)
print('\n[5] Testing Supplier PIN Update:')
r_pin = process_converter_chat('Set Supplier PIN: 560001', r_hsn['updated_payload'], r_hsn['validation_report'], [])
assert r_pin['patch_applied'] is True
inv = r_pin['updated_payload']['einvoices'][0]
assert inv.get('supplier_pin') == '560001'
assert inv.get('supplierdt1', {}).get('supplier_pin') == '560001'
assert inv.get('supplier_state') == '29'
print('  [OK] Supplier PIN & State updated to 560001 / 29')

# 6. Test Delivery Mode Update (Set Mode: REG)
print('\n[6] Testing Delivery Mode Update:')
r_mode = process_converter_chat('Set Mode: REG', r_pin['updated_payload'], r_pin['validation_report'], [])
assert r_mode['patch_applied'] is True
inv = r_mode['updated_payload']['einvoices'][0]
assert inv.get('transactionmode') == 'REG'
assert inv.get('trandt1', {}).get('transactionmode') == 'REG'
print('  [OK] Delivery Mode updated to REG')

# 7. Test Vehicle Number Update (Vehicle is KA01AB1234)
print('\n[7] Testing Vehicle Number Update:')
r_veh = process_converter_chat('Vehicle is KA01AB1234', r_mode['updated_payload'], r_mode['validation_report'], [])
assert r_veh['patch_applied'] is True
inv = r_veh['updated_payload']['einvoices'][0]
assert inv.get('veh_number') == 'KA01AB1234'
assert inv.get('ewbdt1', {}).get('veh_number') == 'KA01AB1234'
print('  [OK] Vehicle Number updated to KA01AB1234')

# 8. Test Transporter ID Update (Set Transporter: 27TUHCN2957U5ZN)
print('\n[8] Testing Transporter ID Update:')
r_trans = process_converter_chat('Set Transporter: 27TUHCN2957U5ZN', r_veh['updated_payload'], r_veh['validation_report'], [])
assert r_trans['patch_applied'] is True
inv = r_trans['updated_payload']['einvoices'][0]
assert inv.get('transporter_id') == '27TUHCN2957U5ZN'
assert inv.get('ewbdt1', {}).get('transporter_id') == '27TUHCN2957U5ZN'
print('  [OK] Transporter ID updated to 27TUHCN2957U5ZN')

# 9. Test Tax Math Rebalance
print('\n[9] Testing Tax Math Rebalance:')
r_tax = process_converter_chat('Rebalance tax math and invoice value', r_trans['updated_payload'], r_trans['validation_report'], [])
assert r_tax['patch_applied'] is True
inv = r_tax['updated_payload']['einvoices'][0]
assert float(inv['valdtls']['totinvval']) == 59000.0
print('  [OK] Tax Math rebalanced: totinvval = 59000.0')

print('\nALL FIELD UPDATES VERIFIED 100% WORKING!')
