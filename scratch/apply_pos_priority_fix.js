const fs = require('fs');
const path = require('path');
const root = path.join(__dirname, '..');
const files = [
    'frontend/converter.html', 'static/converter.html',
    'frontend/ingestion.html', 'static/ingestion.html', 'src/ui/ingestion.html',
    'gst_sentinal_7304/frontend/converter.html', 'gst_sentinal_7304/static/converter.html',
    'gst_sentinal_7304/frontend/ingestion.html', 'gst_sentinal_7304/static/ingestion.html',
    'gst_sentinal_7304/src/ui/ingestion.html'
];
const MARK = '// POS mismatch takes precedence over passive text matches';
let ok = 0;
for (const f of files) {
    const p = path.join(root, f);
    let src = fs.readFileSync(p, 'utf8');
    if (src.includes(MARK)) { ok++; continue; }
    const nl = src.includes('\r\n') ? '\r\n' : '\n';
    const re = /([ \t]*\/\/ Priority 2: Inquire tailPrompt)/;
    if (!re.test(src)) { console.error('anchor missing', f); continue; }
    src = src.replace(re, `        ${MARK} (e.g. a ✅ Buyer GSTIN line)${nl}        if (!activeTopic && !isPosJustPatched && hasPosMismatchText) activeTopic = 'pos';${nl}${nl}$1`);
    fs.writeFileSync(p, src, 'utf8');
    ok++;
}
console.log(`${ok}/${files.length} OK`);
