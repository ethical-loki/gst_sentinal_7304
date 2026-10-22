const fs = require('fs');
const path = require('path');

const root = path.join(__dirname, '..');
const targetFiles = [
    'frontend/converter.html', 'static/converter.html',
    'frontend/ingestion.html', 'static/ingestion.html', 'src/ui/ingestion.html',
    'gst_sentinal_7304/frontend/converter.html', 'gst_sentinal_7304/static/converter.html',
    'gst_sentinal_7304/frontend/ingestion.html', 'gst_sentinal_7304/static/ingestion.html',
    'gst_sentinal_7304/src/ui/ingestion.html'
].map(p => path.join(root, p));

const HELPER = `        // Inline Place of Supply (POS) submission for Copilot
        function submitCopilotPosInput(btnOrInput) {
            const parent = btnOrInput.closest('.copilot-inline-suggestion-bar') || btnOrInput.parentElement;
            if (!parent) return;
            const posSel = parent.querySelector('select[data-field="pos"]') || parent.querySelector('select');
            const posVal = posSel ? posSel.value : '29';
            sendCopilotQuickMessage(\`Set POS: \${posVal}\`);
        }
`;

const POS_FLAGS = `
        const isPosJustPatched = Boolean(data.patch_applied && patchSummary.some(s => s.includes('place of supply') || /\\bpos\\b/i.test(s)));
        if (isPosJustPatched) handledTypes.add('pos');
        const hasPosMismatchText = Boolean(
            replyLower.includes('tax split mismatch') || tailPrompt_pos_check(replyLower)
        );`;

const RENDER_POS = `        const renderPosBox = () => {
            if (renderedBoxCount > 0 || handledTypes.has('pos') || isPosJustPatched) return;
            const posAct = findAction(a => /set pos:|place of supply/i.test(a));
            const hasPosPrompt = Boolean(
                activeTopic === 'pos' || posAct || hasPosMismatchText ||
                tailPrompt.includes('place of supply') || tailPrompt.includes('pos mismatch')
            );
            if (!hasPosPrompt) return;
            handledTypes.add('pos');
            renderedBoxCount++;
            const buyerBlk = targetInv.buyerdt1 || {};
            const suppBlk = targetInv.supplierdt1 || {};
            const valBlk = targetInv.valdtls || targetInv.valdt1 || {};
            const bPos = buyerBlk.pos || targetInv.pos || valBlk.pos || buyerBlk.buyer_state || targetInv.buyer_state || '29';
            const sStateRaw = suppBlk.supplier_state || targetInv.supplier_state || String(suppBlk.self_gstin || targetInv.self_gstin || '27').slice(0, 2);
            let defPos = String(bPos).replace(/\\D/g, '').padStart(2, '0') || '29';
            if (posAct) {
                const mPos = posAct.match(/\\b([0-9]{1,2})\\b/);
                if (mPos) defPos = mPos[1].padStart(2, '0');
            }
            const sState = String(sStateRaw).replace(/\\D/g, '').padStart(2, '0');
            const isInterstate = (sState !== defPos);
            const taxLabel = isInterstate ? \`Interstate \${sState} → \${defPos} (IGST)\` : \`Intrastate \${sState} (CGST+SGST)\`;
            barsHtml += \`
                <div class="copilot-inline-suggestion-bar copilot-pos-bar" style="margin-top: 8px; margin-bottom: 6px; padding: 12px 14px; background: rgba(15, 23, 42, 0.95); border: 1px solid rgba(56, 189, 248, 0.45); border-radius: 8px; display: flex; flex-direction: column; gap: 8px;">
                    <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap;">
                        <span style="font-size: 0.82rem; font-weight: 700; color: #38bdf8;">🌐 Place of Supply (POS) &amp; Tax Split Routing:</span>
                        <span class="copilot-pos-tax-label" data-supp-state="\${sState}" style="font-size: 0.72rem; color: #34d399; font-family: 'JetBrains Mono', monospace; background: rgba(52, 211, 153, 0.1); padding: 2px 8px; border-radius: 4px; border: 1px solid rgba(52, 211, 153, 0.3);">\${taxLabel}</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                        <div style="display: flex; flex-direction: column; gap: 2px;">
                            <label style="font-size: 0.70rem; color: #94a3b8; font-weight: 600;">PLACE OF SUPPLY (POS)</label>
                            <select data-field="pos" class="copilot-inline-pos-select" onchange="(function(sel){var bar=sel.closest('.copilot-pos-bar');var lbl=bar&&bar.querySelector('.copilot-pos-tax-label');if(!lbl)return;var s=lbl.getAttribute('data-supp-state');lbl.textContent=(s!==sel.value)?('Interstate '+s+' → '+sel.value+' (IGST)'):('Intrastate '+s+' (CGST+SGST)');})(this)" style="background: #090e1a; color: #f8fafc; border: 1px solid #38bdf8; border-radius: 6px; padding: 5px 8px; font-size: 0.84rem; outline: none; font-family: 'JetBrains Mono', monospace; cursor: pointer; max-width: 230px;">
                                \${buildStateOptionsHtml(defPos)}
                            </select>
                        </div>
                        <div style="display: flex; align-items: flex-end; padding-top: 14px; gap: 6px; flex-wrap: wrap;">
                            <button type="button" class="copilot-action-btn" onclick="submitCopilotPosInput(this)" style="background: linear-gradient(135deg, #0ea5e9, #6366f1); color: #fff; border: none; font-weight: 700; padding: 6px 14px; border-radius: 6px; cursor: pointer; white-space: nowrap;">🌐 Apply POS</button>
                            <button type="button" class="copilot-action-btn" onclick="sendCopilotQuickMessage('Rebalance tax math and invoice value')" style="background: rgba(16, 185, 129, 0.2); border: 1px solid #10b981; color: #34d399; font-weight: 600; padding: 6px 12px; border-radius: 6px; cursor: pointer; white-space: nowrap;">🧮 Rebalance Tax Split</button>
                        </div>
                    </div>
                </div>
            \`;
        };

`;

function mustReplace(src, re, fn, label, file) {
    if (!re.test(src)) throw new Error(`[${label}] anchor not found in ${file}`);
    return src.replace(re, fn);
}

let ok = 0;
for (const tf of targetFiles) {
    const rel = path.relative(root, tf);
    if (!fs.existsSync(tf)) { console.warn('Missing:', rel); continue; }
    let src = fs.readFileSync(tf, 'utf8');
    if (src.includes('const renderPosBox')) { console.log('Already patched:', rel); ok++; continue; }
    if (!src.includes('function buildStateOptionsHtml')) { console.error('No buildStateOptionsHtml in', rel); continue; }
    const nl = src.includes('\r\n') ? '\r\n' : '\n';
    const fix = s => s.replace(/\r?\n/g, nl);
    try {
        // 1. Helper before renderer
        src = mustReplace(src, /([ \t]*\/\/\s*Helper to dynamically render editable input boxes for every suggestion)/,
            m => fix(HELPER) + m, 'helper', rel);
        // 2. Pending corrections should include POS
        src = mustReplace(src, /\|change date to\|vehicle is/, '|set pos:|change date to|vehicle is', 'pending', rel);
        // 3. POS flags right after tailPrompt is computed (before topic detection)
        src = mustReplace(src, /([ \t]*\/\/ Detect active focus topic strictly:)/, m =>
            fix(POS_FLAGS.replace('tailPrompt_pos_check(replyLower)',
                "tailPrompt.includes('place of supply') && (tailPrompt.includes('mismatch') || tailPrompt.includes('select'))")) + nl + m, 'flags', rel);
        // 4. Priority 1 topic (before tax_math action)
        src = mustReplace(src, /\} else if \(actions\.some\(a => \/rebalance tax\/i\.test\(a\)\)\) \{/,
            "} else if (!isPosJustPatched && actions.some(a => /set pos:|place of supply/i.test(a))) {" + nl +
            "            activeTopic = 'pos';" + nl + "        $&", 'p1', rel);
        // 5. Priority 2 topic (before tax valuation)
        src = mustReplace(src, /\} else if \(tailPrompt\.includes\('tax valuation recalculation'\)/,
            "} else if (!isPosJustPatched && (hasPosMismatchText || tailPrompt.includes('pos mismatch'))) {" + nl +
            "                activeTopic = 'pos';" + nl + "            $&", 'p2', rel);
        // 6. renderPosBox definition + invocation
        src = mustReplace(src, /([ \t]*\/\/ 1\. Render active focus topic FIRST)/,
            m => fix(RENDER_POS) + m + nl + "        if (activeTopic === 'pos') renderPosBox();", 'render', rel);
        // 7. Fallback invocation
        src = mustReplace(src, /([ \t]*\/\/ 3\. Fallback for any other)/,
            m => "        if (renderedBoxCount === 0 && !isPosJustPatched && (hasPosMismatchText || actions.some(a => /set pos:|place of supply/i.test(a)))) renderPosBox();" + nl + nl + m, 'fallback', rel);
        // 8. Filter standalone buttons handled by the POS box
        src = mustReplace(src, /\(handledTypes\.has\('tax_math'\) && actL\.includes\('rebalance tax math'\)\)/,
            "$& ||" + nl + "                (handledTypes.has('pos') && (actL.includes('set pos:') || actL.includes('apply pos') || actL.includes('place of supply') || actL.includes('rebalance tax math')))", 'filter', rel);
        fs.writeFileSync(tf, src, 'utf8');
        console.log('Patched:', rel);
        ok++;
    } catch (e) {
        console.error(e.message);
    }
}
console.log(`\n${ok}/${targetFiles.length} files OK`);
