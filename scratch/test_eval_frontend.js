const fs = require('fs');
let fnCode = fs.readFileSync('scratch/fn_frontend_extracted.js', 'utf-8');

let activeIrnGenerated = false;
function escapeHtml(s) { return String(s || ''); }
function unlockStage2() {}

eval(fnCode);

const mockData = {
    reply: `💡 Step-by-Step Resolution (1 issue at a time):
👉 Please provide a valid Invoice Number:
Under NIC Rule 2144, the document number cannot start with 0, /, or -, must be 1 to 16 characters long, and contain only alphanumeric characters, /, and -.
• Currently in payload: 'INV-2026-OUTLIER-01'
• Suggested compliant format: INV-2026-OUTLIER
Please enter your invoice number below or click to apply:
• Or click "⚡ Auto-Fix All Compliance Errors" to resolve all errors in one click.`,
    interactive_actions: [
        'Set Invoice No: INV-2026-OUTLIER',
        'Set Invoice No: INV-2026-001',
        '⚡ Auto-Fix All Compliance Errors'
    ],
    validation_report: { failed_invoices: 1, results: [{ error_count: 2 }] }
};

const mockPayload = {
    docno: 'INV-2026-OUTLIER-01'
};

const result = renderCopilotSuggestionsHtml(mockData, false, mockPayload);
console.log('Result length:', result.length);
console.log('Has docno bar:', result.includes('copilot-docno-bar'));
