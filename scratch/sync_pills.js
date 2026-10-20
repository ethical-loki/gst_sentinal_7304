const fs = require('fs');
const path = require('path');

const targetFiles = [
    path.join(__dirname, '..', 'frontend', 'converter.html'),
    path.join(__dirname, '..', 'static', 'converter.html'),
    path.join(__dirname, '..', 'frontend', 'ingestion.html'),
    path.join(__dirname, '..', 'static', 'ingestion.html'),
    path.join(__dirname, '..', 'src', 'ui', 'ingestion.html'),
    path.join(__dirname, '..', 'gst_sentinal_7304', 'frontend', 'converter.html'),
    path.join(__dirname, '..', 'gst_sentinal_7304', 'static', 'converter.html'),
    path.join(__dirname, '..', 'gst_sentinal_7304', 'frontend', 'ingestion.html'),
    path.join(__dirname, '..', 'gst_sentinal_7304', 'static', 'ingestion.html'),
    path.join(__dirname, '..', 'gst_sentinal_7304', 'src', 'ui', 'ingestion.html')
];

const oldPillsPat = /(\s*\/\/\s*Update Quick Prompt Pills\s*function updateCopilotPills\(prompts\) \{[\s\S]*?container\.innerHTML = DEFAULT_COPILOT_PILLS_HTML;\s*\})/;

const newPillsFunc = `        // Update Quick Prompt Pills
        function updateCopilotPills(prompts) {
            const container = document.getElementById('copilotPillsBar');
            if (!container) return;
            const targetInv = (typeof currentLivePayload !== 'undefined' && currentLivePayload && currentLivePayload.einvoices && currentLivePayload.einvoices[0]) ? currentLivePayload.einvoices[0] : ((typeof currentLivePayload !== 'undefined' && currentLivePayload) ? currentLivePayload : ((typeof currentPayload !== 'undefined' && currentPayload) ? currentPayload : {}));
            const hasIrn = Boolean(targetInv.irn || targetInv.irn_status === 'GENERATED' || targetInv.status === 'IRN_GENERATED' || (targetInv.docdt1 && targetInv.docdt1.irn));
            let list = (prompts || []).slice();
            if (hasIrn) {
                list = list.filter(p => !p.includes('Generate IRN'));
            }
            if (list && list.length > 0 && list.some(p => p.includes('IRN') || p.includes('Download'))) {
                container.innerHTML = list.map(p => {
                    const icon = p.includes('IRN') ? '🚀 ' : (p.includes('Download') ? '📥 ' : '⚡ ');
                    return '<button class="copilot-pill" onclick="sendCopilotQuickMessage(\\'' + escapeHtml(p) + '\\')">' + icon + escapeHtml(p) + '</button>';
                }).join(' ');
                return;
            }
            container.innerHTML = DEFAULT_COPILOT_PILLS_HTML;
        }`;

for (const tf of targetFiles) {
    if (fs.existsSync(tf)) {
        const c = fs.readFileSync(tf, 'utf8');
        if (oldPillsPat.test(c)) {
            const updated = c.replace(oldPillsPat, '\n' + newPillsFunc);
            fs.writeFileSync(tf, updated, 'utf8');
            console.log('Updated pills in:', path.relative(path.join(__dirname, '..'), tf));
        } else {
            console.log('No pills match in:', path.relative(path.join(__dirname, '..'), tf));
        }
    }
}
