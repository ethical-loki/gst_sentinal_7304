const fs = require('fs');
const path = require('path');
const root = path.join(__dirname, '..');
const files = ['frontend/converter.html', 'static/ingestion.html', 'gst_sentinal_7304/src/ui/ingestion.html'];

function extract(src, name) {
    const start = src.indexOf(`function ${name}(`);
    if (start === -1) throw new Error('missing ' + name);
    let i = src.indexOf('{', start), depth = 0;
    for (; i < src.length; i++) {
        if (src[i] === '{') depth++;
        else if (src[i] === '}') { depth--; if (depth === 0) break; }
    }
    return src.slice(start, i + 1);
}

for (const f of files) {
    const src = fs.readFileSync(path.join(root, f), 'utf8');
    const statesIdx = src.indexOf('INDIAN_STATES_LIST');
    const statesDecl = src.slice(src.lastIndexOf('const', statesIdx), src.indexOf('];', statesIdx) + 2);
    const code = [statesDecl, extract(src, 'buildStateOptionsHtml'), extract(src, 'buildSubsupplyOptionsHtml'),
        extract(src, 'escapeHtml'), extract(src, 'renderCopilotSuggestionsHtml'),
        'module.exports = renderCopilotSuggestionsHtml;'].join('\n');
    const m = { exports: null };
    new Function('module', code)(m);
    const render = m.exports;
    const payload = { einvoices: [{ docdt1: { docno: 'INV1', docdt: new Date().toLocaleDateString('en-GB').replace(/\//g, '/') },
        supplierdt1: { self_gstin: '27ABCDE1234F1Z5', supplier_state: '27' }, buyerdt1: { buyer_gstin: '29XYZAB5678C1Z2', pos: '29' } }] };
    // Case A: screenshot reply, no actions
    const a = render({ reply: '• ✅ Place of Supply (POS: 29) matches Buyer GSTIN state jurisdiction (29).\n• ❌ Tax Split Mismatch: Interstate supply (27 -> 29) charged CGST/SGST instead of IGST.', interactive_actions: [] }, false, payload);
    // Case B: backend actions
    const b = render({ reply: 'Tax split issue', interactive_actions: ['Set POS: 29', 'Rebalance tax math and invoice value', '⚡ Auto-Fix All Compliance Errors'] }, false, payload);
    // Case C: just patched -> no POS box
    const c = render({ reply: 'POS updated', patch_applied: true, patch_summary: ['Place of Supply set to 29'], interactive_actions: [] }, false, payload);
    if (process.env.DBG) console.log(a.replace(/<option[\s\S]*?<\/option>/g, '').slice(0, 900));
    console.log(f, '| A:', a.includes('copilot-pos-bar') && a.includes('data-field="pos"'),
        '| B:', b.includes('copilot-pos-bar'), 'dupBtn:', (b.match(/Set POS: 29/g) || []).length,
        '| C(no box):', !c.includes('copilot-pos-bar'));
}
