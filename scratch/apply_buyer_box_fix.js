const fs = require('fs');
const path = require('path');

const root = path.join(__dirname, '..');

// 1. Fix backend patch_summary string in both converter_service.py files
const backendFiles = [
    path.join(root, 'backend', 'converter_service.py'),
    path.join(root, 'gst_sentinal_7304', 'backend', 'converter_service.py')
];

for (const bf of backendFiles) {
    if (fs.existsSync(bf)) {
        let content = fs.readFileSync(bf, 'utf8');
        const oldStr = 'patch_summary.append(f"Auto-routed GST split from Supplier & Buyer GSTIN ({_route_txt})")';
        const newStr = 'patch_summary.append(f"Auto-calculated GST split: {_route_txt}")';
        if (content.includes(oldStr)) {
            content = content.replace(oldStr, newStr);
            fs.writeFileSync(bf, content, 'utf8');
            console.log(`Updated backend: ${path.relative(root, bf)}`);
        }
    }
}

// 2. Fix the 10 HTML templates
const targetHtmls = [
    'frontend/converter.html', 'static/converter.html',
    'frontend/ingestion.html', 'static/ingestion.html', 'src/ui/ingestion.html',
    'gst_sentinal_7304/frontend/converter.html', 'gst_sentinal_7304/static/converter.html',
    'gst_sentinal_7304/frontend/ingestion.html', 'gst_sentinal_7304/static/ingestion.html',
    'gst_sentinal_7304/src/ui/ingestion.html'
].map(p => path.join(root, p));

const oldSupGstLine = "const isSupGstJustPatched = Boolean(data.patch_applied && patchSummary.some(s => s.includes('supplier gstin') || s.includes('self_gstin')));";
const oldBuyerGstLine = "const isBuyerGstJustPatched = Boolean(data.patch_applied && patchSummary.some(s => s.includes('buyer gstin') || s.includes('urp')));";

const newSupGstLine = "const isSupGstJustPatched = Boolean(data.patch_applied && patchSummary.some(s => !s.includes('auto-routed') && !s.includes('auto-calculated') && !s.includes('split') && (s.includes('supplier_gstin') || s.includes('self_gstin') || (s.includes('supplier gstin') && (s.includes('updated') || s.includes('corrected') || s.includes('aligned') || s.includes('set'))))));";
const newBuyerGstLine = "const isBuyerGstJustPatched = Boolean(data.patch_applied && patchSummary.some(s => !s.includes('auto-routed') && !s.includes('auto-calculated') && !s.includes('split') && (s.includes('buyer_gstin') || (s.includes('buyer gstin') && (s.includes('updated') || s.includes('set') || s.includes('assigned'))) || (s.includes('urp') && (s.includes('buyer') || s.includes('set') || s.includes('unregistered'))))));";

let updatedCount = 0;
for (const tf of targetHtmls) {
    if (!fs.existsSync(tf)) continue;
    let content = fs.readFileSync(tf, 'utf8');
    
    // Replace isBuyerGstJustPatched and isSupGstJustPatched
    if (content.includes(oldBuyerGstLine)) {
        content = content.replace(oldBuyerGstLine, newBuyerGstLine);
    }
    if (content.includes(oldSupGstLine)) {
        content = content.replace(oldSupGstLine, newSupGstLine);
    }
    
    // Enhance suggested GSTIN extraction in renderBuyerGstinBox
    const oldDefBuyer = "let defBuyerGst = '29XYZAB5678C1Z2';\n                if (buyerGstinAct) {";
    const newDefBuyer = `let defBuyerGst = '29XYZAB5678C1Z2';
                const mSugg = tailPrompt.match(/suggested format for state \\d+:\\s*([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z0-9]{1,3})/i) ||
                              replyLower.match(/suggested format for state \\d+:\\s*([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z0-9]{1,3})/i);
                if (mSugg) {
                    defBuyerGst = mSugg[1].toUpperCase();
                } else if (buyerGstinAct) {`;
    if (content.includes(oldDefBuyer)) {
        content = content.replace(oldDefBuyer, newDefBuyer);
    }

    // Enhance hasBuyerGstinPrompt
    const oldPromptCheck = "tailPrompt.includes('15-digit buyer gstin')";
    const newPromptCheck = "tailPrompt.includes('15-digit buyer gstin') || tailPrompt.includes(\"buyer's proper 15-digit gstin\") || tailPrompt.includes('tell me your buyer')";
    if (content.includes(oldPromptCheck) && !content.includes(newPromptCheck)) {
        content = content.split(oldPromptCheck).join(newPromptCheck);
    }

    fs.writeFileSync(tf, content, 'utf8');
    console.log(`Updated HTML: ${path.relative(root, tf)}`);
    updatedCount++;
}

console.log(`\nSuccessfully updated ${updatedCount} files.`);
