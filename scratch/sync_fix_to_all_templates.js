const fs = require('fs');
const path = require('path');

// 1. Read function from scratch/test_gstin_and_vehicle_fix.js
const testJsPath = path.join(__dirname, 'test_gstin_and_vehicle_fix.js');
const testContent = fs.readFileSync(testJsPath, 'utf8');

const startMarker = 'return function renderCopilotSuggestionsHtml(data, isCompliant, payload) {';
const endMarker = 'return barsHtml;\n    };';

const startIdx = testContent.indexOf(startMarker);
const endIdx = testContent.indexOf(endMarker);

if (startIdx === -1 || endIdx === -1) {
    console.error("Could not find start or end markers in test_gstin_and_vehicle_fix.js!");
    process.exit(1);
}

// Extract the body inside the function
const body = testContent.substring(startIdx + startMarker.length, endIdx);

// Build replacement string for HTML files with proper 8-space indentation
const replacement = `        // Helper to dynamically render editable input boxes for every suggestion
        function renderCopilotSuggestionsHtml(data, isCompliant, payload) {${body}            return barsHtml;
        }`;

// Target files to update
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

const pat = /(\s*\/\/\s*Helper to dynamically render editable input boxes for every suggestion[\s\S]*?function renderCopilotSuggestionsHtml\(data,\s*isCompliant,\s*payload\) \{[\s\S]*?\n\s*return barsHtml;\s*\n\s*\})/;

let successCount = 0;
for (const tf of targetFiles) {
    if (!fs.existsSync(tf)) {
        console.warn(`File does not exist: ${tf}`);
        continue;
    }
    const orig = fs.readFileSync(tf, 'utf8');
    if (!pat.test(orig)) {
        console.error(`Pattern match FAILED for: ${tf}`);
        continue;
    }
    const updated = orig.replace(pat, '\n' + replacement);
    fs.writeFileSync(tf, updated, 'utf8');
    console.log(`Successfully updated: ${path.relative(path.join(__dirname, '..'), tf)}`);
    successCount++;
}

console.log(`\nUpdated ${successCount}/${targetFiles.length} files successfully.`);
