const fs = require('fs');

const converterContent = fs.readFileSync('frontend/converter.html', 'utf-8');

// Check that renderCopilotSuggestionsHtml exists and is intact
if (!converterContent.includes('function renderCopilotSuggestionsHtml(data, isCompliant, payload) {')) {
    console.error("Missing renderCopilotSuggestionsHtml in frontend/converter.html");
    process.exit(1);
}

// Check that copilot-gstin-bar is present
if (!converterContent.includes('copilot-gstin-bar')) {
    console.error("Missing copilot-gstin-bar in frontend/converter.html");
    process.exit(1);
}

// Check that priority 1 checks actions first
if (!converterContent.includes("activeTopic = 'sup_gstin';")) {
    console.error("Missing activeTopic = 'sup_gstin'");
    process.exit(1);
}

console.log("frontend/converter.html syntax and content verified successfully!");
