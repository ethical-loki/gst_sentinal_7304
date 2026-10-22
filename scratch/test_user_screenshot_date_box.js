const fs = require('fs');
let content = fs.readFileSync('static/ingestion.html', 'utf8').replace(/\r\n/g, '\n');

const startMarker = 'function renderCopilotSuggestionsHtml(data, isCompliant, payload) {';
const endMarker = 'return barsHtml;\n        }';

const sIdx = content.indexOf(startMarker);
const eIdx = content.indexOf(endMarker, sIdx);

if (sIdx === -1 || eIdx === -1) {
    console.error("Markers not found", sIdx, eIdx);
    process.exit(1);
}

const fnBody = content.substring(sIdx + startMarker.length, eIdx + 'return barsHtml;'.length);
const escapeHtml = (s) => String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const getHsnChapterInfo = () => ({ code: '87', name: 'Vehicles' });
const buildStateOptionsHtml = () => '';
const buildSubsupplyOptionsHtml = () => '';

const testFn = new Function('data', 'isCompliant', 'payload', 'escapeHtml', 'getHsnChapterInfo', 'buildStateOptionsHtml', 'buildSubsupplyOptionsHtml', fnBody);

console.log("=== TEST 1: User Screenshot Scenario (docdt1.docdt blank, Set date: 2026-10-22) ===");
const userScreenData = {
    reply: "Live Re-Audit Status: 1 unresolved errors remaining.\n---\n👉 Quick Question on [docdt1.docdt]:\n\ndocdt (Document Date) is mandatory and cannot be blank\n\n💡 Action Required: Change the document date to a compliant date within the last 2 days (2026-10-22):\n\nClick an option below or use the date picker to change the date:",
    interactive_actions: ["Set date: 2026-10-22", "Auto-Fix All Compliance Errors"],
    patch_applied: false,
    patch_summary: []
};

const payload = {
    docno: "INV-2026-001",
    docdt1: { docno: "INV-2026-001", docdt: "" }
};

const htmlOut = testFn(userScreenData, false, payload, escapeHtml, getHsnChapterInfo, buildStateOptionsHtml, buildSubsupplyOptionsHtml);
console.log("Has copilot-date-bar:", htmlOut.includes("copilot-date-bar"));
console.log("Has input[type=date]:", htmlOut.includes('type="date"'));
console.log("Has Apply Date button:", htmlOut.includes("Apply Date"));
console.log("Has duplicate standalone 'Set date:' button:", htmlOut.includes("Set date: 2026-10-22"));

if (!htmlOut.includes("copilot-date-bar") || !htmlOut.includes('type="date"')) {
    console.error("❌ FAILED: Date box did NOT render!");
    process.exit(1);
} else {
    console.log("✅ PASSED: Editable Date Box rendered successfully!");
}

console.log("\n=== TEST 2: Invoice Number (docno) Scenario ===");
const docnoData = {
    reply: "👉 Please provide a valid Invoice Number:\n\nUnder NIC Rule 2144, document number cannot start with 0, /, or -.\nCurrently in payload: '0INV-BAD'",
    interactive_actions: ["Set Invoice No: INV-BAD", "⚡ Auto-Fix All Compliance Errors"],
    patch_applied: false,
    patch_summary: []
};
const docnoPayload = {
    docno: "0INV-BAD",
    docdt1: { docno: "0INV-BAD", docdt: "2026-10-22" }
};
const docnoHtmlOut = testFn(docnoData, false, docnoPayload, escapeHtml, getHsnChapterInfo, buildStateOptionsHtml, buildSubsupplyOptionsHtml);
console.log("Has copilot-docno-bar:", docnoHtmlOut.includes("copilot-docno-bar"));
console.log("Has copilot-inline-docno-input:", docnoHtmlOut.includes("copilot-inline-docno-input"));
console.log("Has Apply Invoice No button:", docnoHtmlOut.includes("Apply Invoice No"));

if (!docnoHtmlOut.includes("copilot-docno-bar") || !docnoHtmlOut.includes("copilot-inline-docno-input")) {
    console.error("❌ FAILED: Docno box did NOT render!");
    process.exit(1);
} else {
    console.log("✅ PASSED: Editable Invoice Number Box rendered successfully!");
}
