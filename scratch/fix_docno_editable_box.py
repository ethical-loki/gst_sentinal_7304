import re

converter_files = [
    'static/converter.html',
    'frontend/converter.html',
    'gst_sentinal_7304/static/converter.html',
    'gst_sentinal_7304/frontend/converter.html'
]

variable_block = '''        // Check if doc date in payload is ALREADY valid (within 2 days of today or compliant)
        const rawDocDt = (targetInv.docdt1 && (targetInv.docdt1.docdt || targetInv.docdt1.doc_date)) || targetInv.docdt || targetInv.doc_date || '';
        let isDateValid = false;
        if (rawDocDt) {
            try {
                let pDate = null;
                if (/^\\d{2}[\\/\\-.]\\d{2}[\\/\\-.]\\d{4}$/.test(rawDocDt)) {
                    const parts = rawDocDt.split(/[\\/\\-.]/);
                    pDate = new Date(`${parts[2]}-${parts[1]}-${parts[0]}`);
                } else if (/^\\d{4}[\\/\\-.]\\d{2}[\\/\\-.]\\d{2}$/.test(rawDocDt)) {
                    pDate = new Date(rawDocDt);
                }
                if (pDate && !isNaN(pDate.getTime())) {
                    const now = new Date();
                    const diffDays = Math.abs((now - pDate) / (1000 * 60 * 60 * 24));
                    if (diffDays <= 2.1) {
                        isDateValid = true;
                    }
                }
            } catch (e) {}
        }
        if (isDateJustPatched) {
            handledTypes.add('date');
        }

        // Check if invoice number (docno) in payload is ALREADY valid per NIC Rule 2144
        const rawDocNo = (targetInv.docdt1 && (targetInv.docdt1.docno || targetInv.docdt1.document_number)) || targetInv.docno || targetInv.document_number || '';
        const cleanDocNo = String(rawDocNo).trim();
        const isDocNoValid = cleanDocNo.length > 0 && cleanDocNo.length <= 16 && /^[A-Za-z1-9][A-Za-z0-9/-]*$/.test(cleanDocNo);
        if (isDocnoJustPatched) {
            handledTypes.add('docno');
        }'''

for fpath in converter_files:
    with open(fpath, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Insert variable declarations right after isVehFormatValid
    if 'const cleanDocNo =' not in content:
        content = content.replace(
            "const isVehFormatValid = /^[A-Z]{2}[0-9]{1,2}[A-Z0-9]{1,4}[0-9]{4}$/.test(cleanVeh);",
            "const isVehFormatValid = /^[A-Z]{2}[0-9]{1,2}[A-Z0-9]{1,4}[0-9]{4}$/.test(cleanVeh);\n\n" + variable_block
        )

    # 2. Add activeTopic === 'docno' in Priority 1
    if "else if (!isDocnoJustPatched && actions.some(a => /set invoice no|invoice number|docno/i.test(a))) {\n            activeTopic = 'docno';" not in content:
        content = content.replace(
            "} else if (!isBuyerGstJustPatched && actions.some(a => /buyer gstin is|buyer is urp|set buyer gstin/i.test(a))) {\n            activeTopic = 'buyer_gstin';",
            "} else if (!isBuyerGstJustPatched && actions.some(a => /buyer gstin is|buyer is urp|set buyer gstin/i.test(a))) {\n            activeTopic = 'buyer_gstin';\n        } else if (!isDocnoJustPatched && actions.some(a => /set invoice no|invoice number|docno/i.test(a))) {\n            activeTopic = 'docno';"
        )

    # 3. Add activeTopic === 'docno' in Priority 2
    if "else if (!isDocnoJustPatched && (tailPrompt.includes('invoice number') || tailPrompt.includes('valid invoice number') || tailPrompt.includes('docno') || tailPrompt.includes('document number'))) {\n                activeTopic = 'docno';" not in content:
        content = content.replace(
            "} else if (!isBuyerGstJustPatched && (tailPrompt.includes('buyer gstin') || tailPrompt.includes('recipient gstin') || tailPrompt.includes('15-digit buyer gstin'))) {\n                activeTopic = 'buyer_gstin';",
            "} else if (!isBuyerGstJustPatched && (tailPrompt.includes('buyer gstin') || tailPrompt.includes('recipient gstin') || tailPrompt.includes('15-digit buyer gstin'))) {\n                activeTopic = 'buyer_gstin';\n            } else if (!isDocnoJustPatched && (tailPrompt.includes('invoice number') || tailPrompt.includes('valid invoice number') || tailPrompt.includes('docno') || tailPrompt.includes('document number'))) {\n                activeTopic = 'docno';"
        )

    # 4. Add docno / invoice to hasInteractiveModule
    content = content.replace(
        "actions.some(a => /vehicle|veh|ka01|hsn|pin|state|date|mode|subsupply|gstin|tax\\s*math|transporter/i.test(a))",
        "actions.some(a => /vehicle|veh|ka01|hsn|pin|state|date|mode|subsupply|gstin|tax\\s*math|transporter|docno|invoice/i.test(a))"
    )

    # 5. Add renderDocnoBox() to Step 2 fallback sequence
    if "if (renderedBoxCount === 0 && !isDocnoJustPatched && (!isDocNoValid || actions.some(a => /invoice no|docno/i.test(a)))) renderDocnoBox();" not in content:
        content = content.replace(
            "// 2. Fallback step-by-step sequence of unresolved issues (strictly one-by-one, aligned with get_friendly_next_step priority)\n        if (renderedBoxCount === 0 && (!isDateValid || actions.some(a => /date/i.test(a)))) renderDateBox();",
            "// 2. Fallback step-by-step sequence of unresolved issues (strictly one-by-one, aligned with get_friendly_next_step priority)\n        if (renderedBoxCount === 0 && !isDocnoJustPatched && (!isDocNoValid || actions.some(a => /invoice no|docno/i.test(a)))) renderDocnoBox();\n        if (renderedBoxCount === 0 && (!isDateValid || actions.some(a => /date/i.test(a)))) renderDateBox();"
        )

    with open(fpath, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Updated: {fpath}")

# Also update hasInteractiveModule in ingestion files
ingestion_files = [
    'static/ingestion.html',
    'src/ui/ingestion.html',
    'frontend/ingestion.html',
    'gst_sentinal_7304/static/ingestion.html',
    'gst_sentinal_7304/src/ui/ingestion.html',
    'gst_sentinal_7304/frontend/ingestion.html'
]

for fpath in ingestion_files:
    with open(fpath, 'r', encoding='utf-8') as f:
        content = f.read()
    content = content.replace(
        "actions.some(a => /vehicle|veh|ka01|hsn|pin|state|date|mode|subsupply|gstin|tax\\s*math|transporter/i.test(a))",
        "actions.some(a => /vehicle|veh|ka01|hsn|pin|state|date|mode|subsupply|gstin|tax\\s*math|transporter|docno|invoice/i.test(a))"
    )
    with open(fpath, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Verified ingestion: {fpath}")
