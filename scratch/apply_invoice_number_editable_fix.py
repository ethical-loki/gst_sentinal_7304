import re
from pathlib import Path

ROOT = Path(r"c:\Users\User\OneDrive\Desktop\GST_Sentinal")

FILES_TO_UPDATE = [
    ROOT / "static" / "ingestion.html",
    ROOT / "static" / "converter.html",
    ROOT / "frontend" / "ingestion.html",
    ROOT / "frontend" / "converter.html",
    ROOT / "src" / "ui" / "ingestion.html",
    ROOT / "gst_sentinal_7304" / "static" / "ingestion.html",
    ROOT / "gst_sentinal_7304" / "static" / "converter.html",
    ROOT / "gst_sentinal_7304" / "frontend" / "ingestion.html",
    ROOT / "gst_sentinal_7304" / "frontend" / "converter.html",
    ROOT / "gst_sentinal_7304" / "src" / "ui" / "ingestion.html",
]

def update_file(filepath: Path):
    if not filepath.exists():
        print(f"Skipping non-existent: {filepath}")
        return
    content = filepath.read_text(encoding="utf-8")
    
    # 1. Add applyDirectDocnoChange if missing
    if "function applyDirectDocnoChange" not in content:
        docno_helper = """        // Apply Direct Invoice Number Change from Error Card
        function applyDirectDocnoChange(inputId) {
            const input = document.getElementById(inputId);
            const val = input ? input.value.trim() : 'INV-2026-001';
            switchRightPanelView('copilot');
            sendCopilotQuickMessage(`Set Invoice No: ${val}`);
        }

"""
        # Insert before applyDirectHsnChange
        if "function applyDirectHsnChange" in content:
            content = content.replace("        // Apply Direct HSN Change from Error Card", docno_helper + "        // Apply Direct HSN Change from Error Card")

    # 2. In renderCopilotSuggestionsHtml, add isDocnoJustPatched
    if "const isDocnoJustPatched" not in content:
        old_patch_detect = "const isStateJustPatched = Boolean(data.patch_applied && patchSummary.some(s => s.includes('state')));"
        new_patch_detect = (
            "const isStateJustPatched = Boolean(data.patch_applied && patchSummary.some(s => s.includes('state')));\n"
            "        const isDocnoJustPatched = Boolean(data.patch_applied && patchSummary.some(s => s.includes('invoice number') || s.includes('docno')));"
        )
        content = content.replace(old_patch_detect, new_patch_detect)
        
        old_handled = "if (isStateJustPatched) handledTypes.add('state');"
        new_handled = (
            "if (isStateJustPatched) handledTypes.add('state');\n"
            "        if (isDocnoJustPatched) handledTypes.add('docno');"
        )
        content = content.replace(old_handled, new_handled)

    # 3. Add isDocNoValid check
    if "const isDocNoValid" not in content:
        target_marker = "if (isDateValid || isDateJustPatched) {\n            handledTypes.add('date');\n        }"
        docno_valid_code = """
        // Check if invoice number (docno) in payload is ALREADY valid per NIC Rule 2144
        const rawDocNo = (targetInv.docdt1 && (targetInv.docdt1.docno || targetInv.docdt1.document_number)) || targetInv.docno || targetInv.document_number || '';
        const cleanDocNo = String(rawDocNo).trim();
        const isDocNoValid = cleanDocNo.length > 0 && cleanDocNo.length <= 16 && /^[A-Za-z1-9][A-Za-z0-9/-]*$/.test(cleanDocNo);
        if (isDocNoValid || isDocnoJustPatched) {
            handledTypes.add('docno');
        }"""
        if target_marker in content:
            content = content.replace(target_marker, target_marker + docno_valid_code)

    # 4. In activeTopic priority 1
    if "activeTopic = 'docno';" not in content:
        old_topic1 = "} else if (!isDateValid && !isDateJustPatched && actions.some(a => /change date to|set date:/i.test(a))) {\n            activeTopic = 'date';"
        new_topic1 = """} else if (!isDocNoValid && !isDocnoJustPatched && actions.some(a => /set invoice no|invoice number|docno/i.test(a))) {
            activeTopic = 'docno';
        } else if (!isDateValid && !isDateJustPatched && actions.some(a => /change date to|set date:/i.test(a))) {
            activeTopic = 'date';"""
        content = content.replace(old_topic1, new_topic1)

        # In activeTopic priority 2 (tailPrompt)
        old_topic2 = "} else if (!isDateValid && !isDateJustPatched && (tailPrompt.includes('document date')"
        new_topic2 = """} else if (!isDocNoValid && !isDocnoJustPatched && (tailPrompt.includes('invoice number') || tailPrompt.includes('valid invoice number') || tailPrompt.includes('docno') || tailPrompt.includes('document number'))) {
                activeTopic = 'docno';
            } else if (!isDateValid && !isDateJustPatched && (tailPrompt.includes('document date')"""
        content = content.replace(old_topic2, new_topic2)

    # 5. Add renderDocnoBox definition
    if "const renderDocnoBox = () => {" not in content:
        render_docno_fn = """        const renderDocnoBox = () => {
            if (isDocNoValid || isDocnoJustPatched || renderedBoxCount > 0 || handledTypes.has('docno')) return;
            const docnoAct = findAction(a => /set invoice no|invoice number|docno/i.test(a));
            const hasDocnoPrompt = Boolean(activeTopic === 'docno' || docnoAct || tailPrompt.includes('invoice number') || tailPrompt.includes('valid invoice number') || tailPrompt.includes('docno') || tailPrompt.includes('document number'));
            if (hasDocnoPrompt) {
                handledTypes.add('docno');
                renderedBoxCount++;
                let defDocno = 'INV-2026-001';
                if (docnoAct) {
                    const m = docnoAct.match(/(?:Set Invoice No:\\s*|invoice number\\s*[:=]?\\s*)([A-Za-z0-9/-]+)/i);
                    if (m) defDocno = m[1];
                } else if (cleanDocNo) {
                    defDocno = cleanDocNo.replace(/^[^A-Za-z1-9]+/, '').replace(/[^0-9A-Za-z/-]/g, '').slice(0, 16) || 'INV-2026-001';
                }
                barsHtml += `
                    <div class="copilot-inline-suggestion-bar copilot-docno-bar" style="margin-top: 8px; margin-bottom: 6px; padding: 12px 14px; background: rgba(15, 23, 42, 0.95); border: 1px solid rgba(56, 189, 248, 0.45); border-radius: 8px; display: flex; flex-direction: column; gap: 8px;">
                        <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap;">
                            <span style="font-size: 0.82rem; font-weight: 700; color: #38bdf8;">📄 Invoice Number (NIC Statutory Rule 2144):</span>
                            <span style="font-size: 0.72rem; color: #38bdf8; font-family: 'JetBrains Mono', monospace; background: rgba(56, 189, 248, 0.1); padding: 2px 8px; border-radius: 4px; border: 1px solid rgba(56, 189, 248, 0.3);">Max 16 Chars (No Leading 0/-/)</span>
                        </div>
                        <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                            <input type="text" class="copilot-inline-custom-input copilot-inline-docno-input" placeholder="e.g. INV-2026-001" value="${escapeHtml(defDocno)}" maxlength="16" oninput="this.value = this.value.toUpperCase().replace(/[^0-9A-Z/-]/g, '')" onkeydown="if(event.key==='Enter'){event.preventDefault();submitCopilotInlineInput(this, 'Set Invoice No: ');}" style="background: #090e1a; color: #f8fafc; border: 1px solid #38bdf8; border-radius: 6px; padding: 5px 9px; font-size: 0.84rem; outline: none; font-family: 'JetBrains Mono', monospace; text-transform: uppercase; width: 160px; font-weight: 700;">
                            <button type="button" class="copilot-action-btn" onclick="submitCopilotInlineInput(this, 'Set Invoice No: ')" style="background: linear-gradient(135deg, #0ea5e9, #6366f1); color: #fff; border: none; font-weight: 700; padding: 6px 14px; border-radius: 6px; cursor: pointer;">✨ Apply Invoice No</button>
                            <button type="button" class="copilot-action-btn" onclick="sendCopilotQuickMessage('Set Invoice No: ${escapeHtml(defDocno)}')" style="background: rgba(16, 185, 129, 0.2); border: 1px solid #10b981; color: #34d399; font-weight: 600; padding: 6px 12px; border-radius: 6px; cursor: pointer;">⚡ Use ${escapeHtml(defDocno)}</button>
                        </div>
                    </div>
                `;
            }
        };

"""
        # Place before renderDateBox
        if "const renderDateBox = () => {" in content:
            content = content.replace("        const renderDateBox = () => {", render_docno_fn + "        const renderDateBox = () => {")

    # 6. Call renderDocnoBox in activeTopic dispatch
    if "if (activeTopic === 'docno') renderDocnoBox();" not in content:
        content = content.replace(
            "// 1. Render active focus topic FIRST\n        if (activeTopic === 'sup_gstin')",
            "// 1. Render active focus topic FIRST\n        if (activeTopic === 'docno') renderDocnoBox();\n        else if (activeTopic === 'sup_gstin')"
        )
        content = content.replace(
            "// 2. Fallback step-by-step sequence of unresolved issues (strictly one-by-one, aligned with get_friendly_next_step priority)\n        if (renderedBoxCount === 0 && !isDateValid && !isDateJustPatched) renderDateBox();",
            "// 2. Fallback step-by-step sequence of unresolved issues (strictly one-by-one, aligned with get_friendly_next_step priority)\n        if (renderedBoxCount === 0 && !isDocNoValid && !isDocnoJustPatched) renderDocnoBox();\n        if (renderedBoxCount === 0 && !isDateValid && !isDateJustPatched) renderDateBox();"
        )

    # 7. Add docno to standalone buttons skip list
    if "actL.includes('set invoice no')" not in content:
        content = content.replace(
            "(handledTypes.has('date') && (actL.includes('apply date')",
            "(handledTypes.has('docno') && (actL.includes('invoice no') || actL.includes('docno') || actL.includes('apply invoice no'))) ||\n                (handledTypes.has('date') && (actL.includes('apply date')"
        )

    filepath.write_text(content, encoding="utf-8")
    print(f"Successfully updated: {filepath}")

for f in FILES_TO_UPDATE:
    update_file(f)
