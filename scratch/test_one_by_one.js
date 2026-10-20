const fs = require('fs');
const html = fs.readFileSync('frontend/converter.html', 'utf8');

const startTag = 'function renderCopilotSuggestionsHtml(data, isCompliant, payload) {';
const sIdx = html.indexOf(startTag);
const endTag = 'async function handleCopilotSubmit(e)';
const fnBody = html.substring(sIdx, html.indexOf(endTag, sIdx));

const buildStateOptionsHtml = (sel) => '<option>State ' + sel + '</option>';
const buildSubsupplyOptionsHtml = (sel) => '<option>Sub ' + sel + '</option>';
const escapeHtml = (s) => String(s);

eval(fnBody);

// Test 1: Date Error turn (Step 1)
const mockDataStep1 = {
    reply: 'Please update the document date to within the last 2 days: Or click Auto-Fix All Compliance Errors',
    suggested_next_steps: ['Change date to Today (2026-10-20)', 'Change date to Yesterday'],
    validation_report: {
        results: [{
            errors: [
                { error_code: '2164', field: 'docdt', message: 'Invoice date is older than 2 days' },
                { error_code: '2274', field: 'buyerdt1.buyer_pin', message: 'Pincode does not match state' },
                { error_code: '4011', field: 'ewbdt1.veh_number', message: 'Vehicle number invalid' }
            ]
        }]
    }
};

const res1 = renderCopilotSuggestionsHtml(mockDataStep1, false, {});
console.log('=== TEST 1: DATE STEP ===');
console.log('Total bars rendered:', (res1.match(/copilot-inline-suggestion-bar/g) || []).length);
console.log('Has Date Bar:', res1.includes('Document Date:'));

// Test 2: PIN/State turn (Step 2)
const mockDataStep2 = {
    reply: 'Government Portal Taxpayer Check on [buyerdt1.buyer_pin]: Conflict: Pincode 560001 is in Karnataka, which does not match registered State. How would you like to align this?',
    suggested_next_steps: ['Set Buyer PIN: 400001, State: 27', 'Set Buyer PIN: 400001'],
    validation_report: {
        results: [{
            errors: [
                { error_code: '2274', field: 'buyerdt1.buyer_pin', message: 'Pincode does not match state' },
                { error_code: '4011', field: 'ewbdt1.veh_number', message: 'Vehicle number invalid' }
            ]
        }]
    }
};

const res2 = renderCopilotSuggestionsHtml(mockDataStep2, false, {});
console.log('=== TEST 2: PIN/STATE STEP ===');
console.log('Total bars rendered:', (res2.match(/copilot-inline-suggestion-bar/g) || []).length);
console.log('Has PIN Bar:', res2.includes('Postal PIN & State'));

// Test 3: Vehicle turn (Step 3)
const mockDataStep3 = {
    reply: 'Vehicle Registration Number Format Error: The vehicle plate KA01 in your payload does not conform. What is your vehicle registration number?',
    suggested_next_steps: ['Vehicle is KA01AB1234', 'Verify vehicle number', 'Disable E-Way Bill'],
    validation_report: {
        results: [{
            errors: [
                { error_code: '4011', field: 'ewbdt1.veh_number', message: 'Vehicle number invalid' }
            ]
        }]
    }
};

const res3 = renderCopilotSuggestionsHtml(mockDataStep3, false, {});
console.log('=== TEST 3: VEHICLE STEP ===');
console.log('Total bars rendered:', (res3.match(/copilot-inline-suggestion-bar/g) || []).length);
console.log('Has Vehicle Bar:', res3.includes('Vehicle Updation'));

// Test 4: HSN turn (Step 4)
const mockDataStep4 = {
    reply: 'Quick question on product HSN: Wrong HSN code detected: You entered 8471 for Servo Motor. Would you like to auto-correct this?',
    suggested_next_steps: ['Set HSN: 85011013', 'Fix HSN from product description'],
    validation_report: {
        results: [{
            errors: [
                { error_code: '2176', field: 'items[0].hsn', message: 'Invalid HSN' }
            ]
        }]
    }
};

const res4 = renderCopilotSuggestionsHtml(mockDataStep4, false, {});
console.log('=== TEST 4: HSN STEP ===');
console.log('Total bars rendered:', (res4.match(/copilot-inline-suggestion-bar/g) || []).length);
console.log('Has HSN Bar:', res4.includes('HSN CODE'));
