const fs = require('fs');
const path = require('path');

const root = 'c:\\Users\\User\\OneDrive\\Desktop\\GST_Sentinal';
const files = [
    'frontend/converter.html',
    'static/converter.html',
    'frontend/ingestion.html',
    'static/ingestion.html',
    'src/ui/ingestion.html',
    'gst_sentinal_7304/frontend/converter.html',
    'gst_sentinal_7304/static/converter.html',
    'gst_sentinal_7304/frontend/ingestion.html',
    'gst_sentinal_7304/static/ingestion.html',
    'gst_sentinal_7304/src/ui/ingestion.html'
];

for (const rel of files) {
    const p = path.join(root, rel);
    if (!fs.existsSync(p)) continue;
    let s = fs.readFileSync(p, 'utf8');

    // Replace the defBuyerGst extraction
    const targetPattern = /let defBuyerGst = '29XYZAB5678C1Z2';\r?\n\s*if \(buyerGstinAct\) \{\r?\n\s*const m = buyerGstinAct\.match\(/;
    
    // Check if it has that or if already modified
    const oldBlock = `let defBuyerGst = '29XYZAB5678C1Z2';
                if (buyerGstinAct) {
                    const m = buyerGstinAct.match(/\\b([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z0-9]{1,3})\\b/i);
                    if (m) defBuyerGst = m[1].toUpperCase();
                    else if (buyerGstinAct.includes('URP')) defBuyerGst = 'URP';
                }`;

    const newBlock = `let defBuyerGst = '29XYZAB5678C1Z2';
                const mSugg = tailPrompt.match(/suggested format for state \\d+:\\s*([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z0-9]{4})/i) ||
                              replyLower.match(/suggested format for state \\d+:\\s*([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z0-9]{4})/i);
                if (mSugg) {
                    defBuyerGst = mSugg[1].toUpperCase();
                } else if (buyerGstinAct) {
                    const m = buyerGstinAct.match(/\\b([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z0-9]{4})\\b/i);
                    if (m) defBuyerGst = m[1].toUpperCase();
                    else if (buyerGstinAct.includes('URP')) defBuyerGst = 'URP';
                }`;

    // Normalize newlines for matching
    const sNorm = s.replace(/\r\n/g, '\n');
    const oldBlockNorm = oldBlock.replace(/\r\n/g, '\n');
    
    if (sNorm.includes(oldBlockNorm)) {
        s = sNorm.replace(oldBlockNorm, newBlock);
        fs.writeFileSync(p, s, 'utf8');
        console.log(`Updated defBuyerGst in ${rel}`);
    } else {
        console.log(`Could not find oldBlock in ${rel}, checking partial match...`);
    }
}
