const fs = require('fs');

const htmlContent = fs.readFileSync('static/ingestion.html', 'utf8');

// Mock data matching user screenshot exactly
const mockData = {
    patch_applied: true,
    patch_summary: [
        "Updated supplier_gstin & self_gstin to 27ABCDE1234F1Z0 (Maharashtra)",
        "Auto-routed GST split from Supplier & Buyer GSTIN (Interstate 27 -> 29: IGST Rs 9,000.00)"
    ],
    reply: `• Currently in payload: URP
• Buyer State: 29 (Karnataka)
• Official GSTIN Format: [2-digit State] + [10-digit PAN] + [1 Entity Digit] + 'Z' + [1 Checksum Digit]
💡 Suggested format for State 29: 29AABCT1234F1ZM

Please tell me your buyer's proper 15-digit GSTIN (e.g. "Buyer GSTIN is <BUYER_GSTIN>"), or select an option below if the buyer is unregistered:`,
    interactive_actions: [
        "Buyer GSTIN is 29AABCT1234F1ZM",
        "Buyer is URP (Unregistered)",
        "Verify current GSTIN",
        "⚡ Auto-Fix All Compliance Errors"
    ]
};

// Extract renderCopilotSuggestionsHtml function definition
const regex = /function\s+renderCopilotSuggestionsHtml\s*\([^)]*\)\s*\{/;
const match = regex.exec(htmlContent);
if (!match) {
    console.error('Could not find renderCopilotSuggestionsHtml');
    process.exit(1);
}

const startIndex = match.index;
let braceCount = 0;
let endIndex = startIndex;
for (let i = startIndex; i < htmlContent.length; i++) {
    if (htmlContent[i] === '{') braceCount++;
    else if (htmlContent[i] === '}') {
        braceCount--;
        if (braceCount === 0) {
            endIndex = i + 1;
            break;
        }
    }
}

const fnCode = htmlContent.slice(startIndex, endIndex);

const testCode = `
function escapeHtml(str) {
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
let activeIrnGenerated = false;
${fnCode}

const payload = {
    einvoices: [{
        supplierdt1: { supplier_gstin: "27ABCDE1234F1Z0", supplier_state: "27" },
        buyerdt1: { buyer_gstin: "URP", buyer_state: "29", pos: "29" }
    }]
};

renderCopilotSuggestionsHtml(mockData, false, payload);
`;

const resultHtml = eval(testCode);

console.log('--- RESULT HTML CHECK ---');
console.log('Contains copilot-buyer-gstin-bar:', resultHtml.includes('copilot-buyer-gstin-bar'));
console.log('Contains value="29AABCT1234F1ZM":', resultHtml.includes('value="29AABCT1234F1ZM"'));
console.log('Contains Apply Buyer GSTIN button:', resultHtml.includes('Apply Buyer GSTIN'));
console.log('Contains URP button:', resultHtml.includes('⚡ URP'));
console.log('Contains Auto-Fix button:', resultHtml.includes('Auto-Fix All Compliance Errors'));

console.log('\n--- RENDERED HTML SNIPPET ---');
console.log(resultHtml);
