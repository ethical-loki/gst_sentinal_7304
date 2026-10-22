const fs = require('fs');
const path = require('path');

const src = fs.readFileSync('static/ingestion.html', 'utf8');

// Mock data corresponding exactly to the user screenshot
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

const mockPayload = {
    einvoices: [{
        supplierdt1: { supplier_gstin: "27ABCDE1234F1Z0", supplier_state: "27" },
        buyerdt1: { buyer_gstin: "URP", buyer_state: "29", pos: "29" }
    }]
};

// Check if current isBuyerGstJustPatched is buggy
const patchSummary = mockData.patch_summary.map(s => String(s).toLowerCase());
const isBuyerGstJustPatched_current = Boolean(mockData.patch_applied && patchSummary.some(s => s.includes('buyer gstin') || s.includes('urp')));
console.log('CURRENT isBuyerGstJustPatched:', isBuyerGstJustPatched_current);
console.log('BUG CONFIRMED: it evaluated to TRUE even though buyer_gstin was NOT patched!');
