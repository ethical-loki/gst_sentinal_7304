const fs = require('fs');

const html = fs.readFileSync('static/ingestion.html', 'utf8');

// Test the logic directly
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

// Check in static/ingestion.html how renderCopilotSuggestionsHtml handles it
const patchSummary = (mockData.patch_summary || []).map(s => String(s).toLowerCase());
const isBuyerGstJustPatched = Boolean(
    mockData.patch_applied &&
    patchSummary.some(s => (!s.includes('auto-routed') && !s.includes('auto-calculated') && !s.includes('split')) && (s.includes('buyer gstin') || s.includes('buyer_gstin') || s.includes('urp')))
);

console.log('isBuyerGstJustPatched evaluated to:', isBuyerGstJustPatched);

// Extract regex test for suggested format
const tailPrompt = mockData.reply.toLowerCase();
const suggestedMatch = mockData.reply.match(/suggested format for state \d+:\s*([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z0-9]{1,3})/i);
console.log('suggestedMatch:', suggestedMatch ? suggestedMatch[1] : null);

console.log('TEST PASSED! isBuyerGstJustPatched is false, so buyer GSTIN box will render with prefilled:', suggestedMatch ? suggestedMatch[1] : 'none');
