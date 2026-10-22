import re

files = [
    'static/converter.html',
    'static/ingestion.html',
    'frontend/converter.html',
    'frontend/ingestion.html',
    'src/ui/ingestion.html',
    'gst_sentinal_7304/static/converter.html',
    'gst_sentinal_7304/static/ingestion.html',
    'gst_sentinal_7304/frontend/converter.html',
    'gst_sentinal_7304/frontend/ingestion.html',
    'gst_sentinal_7304/src/ui/ingestion.html'
]

unit_html_snippet = '''                            <div style="display: flex; flex-direction: column; gap: 2px;">
                                <label style="font-size: 0.70rem; color: #94a3b8; font-weight: 600;">UNIT</label>
                                <input type="text" data-field="unit" class="copilot-inline-unit-input" placeholder="e.g. NOS" value="${escapeHtml(defUqc)}" maxlength="5" onkeydown="if(event.key==='Enter'){event.preventDefault();submitCopilotHsnInput(this);}" style="background: #090e1a; color: #f8fafc; border: 1px solid #38bdf8; border-radius: 6px; padding: 5px 9px; font-size: 0.84rem; outline: none; font-family: 'JetBrains Mono', monospace; width: 65px; font-weight: 700; text-transform: uppercase;">
                            </div>'''

for fpath in files:
    with open(fpath, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Add defUqc definition if missing
    if 'const defUqc =' not in content:
        content = content.replace(
            "const defQty = (firstItm && firstItm.qty !== undefined) ? firstItm.qty : '1.0';",
            "const defQty = (firstItm && firstItm.qty !== undefined) ? firstItm.qty : '1.0';\n                const defUqc = (firstItm && (firstItm.uqc || firstItm.unit)) ? (firstItm.uqc || firstItm.unit) : 'NOS';"
        )
        content = content.replace(
            "const defQty = (firstItm && firstItm.qty !== undefined) ? firstItm.qty : '5.0';",
            "const defQty = (firstItm && firstItm.qty !== undefined) ? firstItm.qty : '5.0';\n                const defUqc = (firstItm && (firstItm.uqc || firstItm.unit)) ? (firstItm.uqc || firstItm.unit) : 'NOS';"
        )

    # 2. Add UNIT input block before TAXABLE VALUE block if data-field="unit" not present
    if 'data-field="unit"' not in content:
        # Match QTY block and insert UNIT block after it
        pattern = r'(<div style="display: flex; flex-direction: column; gap: 2px;">\s*<label style="font-size: 0\.70rem; color: #94a3b8; font-weight: 600;">QTY</label>[\s\S]*?</div>)'
        
        def repl(match):
            qty_block = match.group(1)
            return qty_block + '\n' + unit_html_snippet

        content = re.sub(pattern, repl, content)

    # 3. Update submitCopilotHsnInput to read unit and include in message
    if 'const unitInp =' not in content:
        # In converter.html
        old_inp_finder = 'const qtyInp = parentBar.querySelector(\'input[data-field="qty"]\') || parentBar.querySelector(\'input.copilot-inline-qty-input\');'
        new_inp_finder = 'const qtyInp = parentBar.querySelector(\'input[data-field="qty"]\') || parentBar.querySelector(\'input.copilot-inline-qty-input\');\n            const unitInp = parentBar.querySelector(\'input[data-field="unit"]\') || parentBar.querySelector(\'input.copilot-inline-unit-input\');'
        content = content.replace(old_inp_finder, new_inp_finder)

        old_val_finder = 'const qtyVal = (qtyInp ? qtyInp.value.trim() : \'\') || \'5.0\';'
        new_val_finder = 'const qtyVal = (qtyInp ? qtyInp.value.trim() : \'\') || \'5.0\';\n            const unitVal = (unitInp ? unitInp.value.trim().toUpperCase() : \'\') || \'NOS\';'
        content = content.replace(old_val_finder, new_val_finder)

        old_val_finder2 = 'const qtyVal = (qtyInp ? qtyInp.value.trim() : \'\') || \'1.0\';'
        new_val_finder2 = 'const qtyVal = (qtyInp ? qtyInp.value.trim() : \'\') || \'1.0\';\n            const unitVal = (unitInp ? unitInp.value.trim().toUpperCase() : \'\') || \'NOS\';'
        content = content.replace(old_val_finder2, new_val_finder2)

        # Update message
        content = content.replace(
            "sendCopilotQuickMessage(`Set HSN: ${hsnVal}, Rate: ${rateVal}, Qty: ${qtyVal}, Taxable Value: ${taxVal}`);",
            "sendCopilotQuickMessage(`Set HSN: ${hsnVal}, Rate: ${rateVal}, Qty: ${qtyVal}, Unit: ${unitVal}, Taxable Value: ${taxVal}`);"
        )
        
        # Ingestion direct patch
        content = content.replace(
            "itm0.qty = parseFloat(qtyVal).toFixed(3);",
            "itm0.qty = parseFloat(qtyVal).toFixed(3);\n                        itm0.uqc = unitVal;\n                        itm0.unit = unitVal;\n                        itm0.unitprice = parseFloat(rateVal).toFixed(2);"
        )

    with open(fpath, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Updated: {fpath}")
