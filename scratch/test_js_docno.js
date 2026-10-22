const fs = require('fs');

const helpers = `
function escapeHtml(str) {
    if (!str) return '';
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
function updateCopilotGkStatus() {}
function updateCopilotHsnCalc() {}
function submitCopilotHsnInput() {}
function submitCopilotInlineInput() {}
function sendCopilotQuickMessage() {}
function autoDetectStateFromPin() {}
function submitCopilotPinStateInput() {}
function getHsnChapterInfo() { return { code: '85', name: 'Electrical' }; }
`;

const fnCode = fs.readFileSync('scratch/fn_to_test.js', 'utf8');

eval(helpers + '\n' + fnCode);

const testData = {
    reply: `👉 **Please provide a valid Invoice Number:**

Under NIC Rule 2144, the document number cannot start with \`0\`, \`/\`, or \`-\`, must be 1 to 16 characters long, and contain only alphanumeric characters, \`/\`, and \`-\`.
• Currently in payload: 'INV-2026-OUTLIER-01'
• Suggested compliant format: **INV-2026-OUTLIER**

Please enter your invoice number below or click to apply:
• Or click "⚡ Auto-Fix All Compliance Errors" to resolve all errors in one click.`,
    interactive_actions: ["Set Invoice No: INV-2026-OUTLIER", "Set Invoice No: INV-2026-001"],
    patch_applied: false,
    patch_summary: []
};

const testPayload = {
    docno: "INV-2026-OUTLIER-01",
    docdt1: { docno: "INV-2026-OUTLIER-01" }
};

const html = renderCopilotSuggestionsHtml(testData, false, testPayload);
console.log("=== Rendered Output ===");
console.log(html);

if (html.includes('copilot-docno-bar') && html.includes('copilot-inline-docno-input')) {
    console.log("\n SUCCESS: Editable Invoice Number input box rendered properly!");
} else {
    console.error("\n FAILED: copilot-docno-bar not rendered!");
    process.exit(1);
}
