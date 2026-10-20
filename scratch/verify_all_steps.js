const fs = require('fs');

const INDIAN_STATES_LIST = [
    { code: "29", name: "Karnataka" },
    { code: "27", name: "Maharashtra" }
];
const OUTWARD_SUBSUPPLY_OPTIONS = [
    { code: "1", label: "1 - Supply" },
    { code: "3", label: "3 - Export" }
];
const buildStateOptionsHtml = (sel) => '<option>' + sel + '</option>';
const buildSubsupplyOptionsHtml = (sel) => '<option>' + sel + '</option>';
const escapeHtml = (s) => String(s);

// New implementation
function renderCopilotSuggestionsHtml(data, isCompliant, payload) {
    const actions = (data.interactive_actions || data.suggested_next_steps || []).slice();
    const replyLower = (data.reply || '').toLowerCase();
    const targetInv = (payload && payload.einvoices && payload.einvoices[0]) ? payload.einvoices[0] : (payload || {});
    let barsHtml = '';
    const standaloneButtons = [];
    const handledTypes = new Set();

    const findAction = (predicate) => actions.find(predicate);
    let renderedBoxCount = 0;

    // Detect whether HSN was just patched in this turn (if so, never repeat HSN command)
    const isHsnJustPatched = Boolean(data.patch_applied && (data.patch_summary || []).some(s => s.toLowerCase().includes('hsn')));
    if (isHsnJustPatched) {
        handledTypes.add('hsn');
    }

    // Detect whether Vehicle was just patched in this turn
    const isVehJustPatched = Boolean(data.patch_applied && (data.patch_summary || []).some(s => s.toLowerCase().includes('vehicle') || s.toLowerCase().includes('veh_number')));
    if (isVehJustPatched) {
        handledTypes.add('vehicle');
    }

    // Detect active focus topic from assistant's reply / prompt
    let activeTopic = null;
    if (replyLower.includes('vehicle') || replyLower.includes('vahan') || replyLower.includes('plate') || replyLower.includes('truck') || replyLower.includes('lorry') || replyLower.includes('ka01') || actions.some(a => /vehicle is|verify vehicle/i.test(a))) {
        if (!isVehJustPatched) activeTopic = 'vehicle';
    } else if (replyLower.includes('product hsn') || replyLower.includes('wrong hsn') || replyLower.includes('tariff') || replyLower.includes('hsn intelligence') || replyLower.includes('quick question on products') || actions.some(a => /set hsn:|fix hsn/i.test(a))) {
        if (!isHsnJustPatched) activeTopic = 'hsn';
    } else if (replyLower.includes('postal pin') || replyLower.includes('pincode') || (replyLower.includes('pin') && replyLower.includes('state')) || replyLower.includes('taxpayer check on') || replyLower.includes('pincode mismatch') || actions.some(a => /pin:/i.test(a))) {
        activeTopic = 'pin_state';
    } else if (replyLower.includes('document date') || replyLower.includes('invoice date') || replyLower.includes('date to within') || replyLower.includes('change the document date') || actions.some(a => /change date to|set date:/i.test(a))) {
        activeTopic = 'date';
    } else if (replyLower.includes('supplier gstin') || replyLower.includes('my gstin is')) {
        activeTopic = 'sup_gstin';
    } else if (replyLower.includes('buyer gstin') || replyLower.includes('recipient gstin')) {
        activeTopic = 'buyer_gstin';
    } else if (replyLower.includes('delivery mode') || replyLower.includes('transaction mode') || actions.some(a => /set mode:/i.test(a))) {
        activeTopic = 'mode';
    } else if (replyLower.includes('sub-supply') || replyLower.includes('subsupply') || actions.some(a => /subsupply/i.test(a))) {
        activeTopic = 'subsupply';
    } else if (replyLower.includes('transporter') || actions.some(a => /transporter/i.test(a))) {
        activeTopic = 'transporter';
    } else if (replyLower.includes('tax valuation') || replyLower.includes('tax math') || replyLower.includes('tax imbalance') || actions.some(a => /rebalance tax/i.test(a))) {
        activeTopic = 'tax_math';
    }

    // If 100% compliant AND no interactive module is being discussed or requested, show Generate IRN / Download
    const hasInteractiveModule = Boolean(
        activeTopic ||
        actions.some(a => /vehicle|veh|ka01|hsn|pin|state|date|mode|subsupply|gstin|tax\s*math|transporter/i.test(a))
    );

    if (isCompliant && !hasInteractiveModule) {
        return `
            <div class="msg-action-bar" style="margin-top: 12px; display: flex; gap: 8px; flex-wrap: wrap;">
                <button type="button" class="copilot-action-btn" onclick="sendCopilotQuickMessage('🚀 Generate IRN')" style="background: linear-gradient(135deg, #10b981, #059669); color: #fff; font-weight: 700; border: none; padding: 7px 16px; border-radius: 8px; cursor: pointer; box-shadow: 0 4px 14px rgba(16, 185, 129, 0.35);">🚀 Generate IRN</button>
                <button type="button" class="copilot-action-btn" onclick="sendCopilotQuickMessage('📥 Download Corrected JSON')" style="background: rgba(56, 189, 248, 0.15); border: 1px solid #38bdf8; color: #38bdf8; font-weight: 600; padding: 7px 14px; border-radius: 8px; cursor: pointer;">📥 Download Corrected JSON</button>
            </div>
        `;
    }

    // Box Renderers
    const renderDateBox = () => {
        if (renderedBoxCount > 0 || handledTypes.has('date')) return;
        const dateAct = findAction(a => /date|today|yesterday/i.test(a));
        const hasDatePrompt = Boolean(activeTopic === 'date' || dateAct || replyLower.includes('document date') || replyLower.includes('date to within') || replyLower.includes('invoice date') || replyLower.includes('what is the correct document date'));
        if (hasDatePrompt) {
            handledTypes.add('date');
            renderedBoxCount++;
            const todayIso = new Date().toISOString().split('T')[0];
            let defDate = todayIso;
            if (dateAct) {
                const m = dateAct.match(/\b(\d{4}-\d{2}-\d{2})\b/);
                if (m) defDate = m[1];
            }
            barsHtml += `
                <div class="copilot-inline-suggestion-bar copilot-date-bar" style="margin-top: 8px; margin-bottom: 6px; padding: 10px 14px; background: rgba(15, 23, 42, 0.9); border: 1px solid rgba(56, 189, 248, 0.45); border-radius: 8px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                    <span style="font-size: 0.82rem; font-weight: 700; color: #38bdf8;">📅 Document Date:</span>
                    <input type="date" class="copilot-inline-custom-input" value="${defDate}">
                    <button type="button" class="copilot-action-btn">📅 Apply Date</button>
                    <button type="button" class="copilot-action-btn">⚡ Set Today</button>
                </div>
            `;
        }
    };

    const renderPinStateBox = () => {
        if (renderedBoxCount > 0 || handledTypes.has('pin')) return;
        const pinAct = findAction(a => /set (?:supplier|buyer)?\s*pin:/i.test(a));
        const stAct = findAction(a => /set (?:supplier|buyer)?\s*state:/i.test(a));
        const hasPinStatePrompt = Boolean(activeTopic === 'pin_state' || pinAct || stAct || (replyLower.includes('pincode') && replyLower.includes('conflict')) || (replyLower.includes('state') && replyLower.includes('pin')) || replyLower.includes('taxpayer check on') || replyLower.includes('postal pin & state'));
        if (hasPinStatePrompt) {
            handledTypes.add('pin');
            handledTypes.add('state');
            renderedBoxCount++;
            let role = 'Buyer';
            if ((pinAct && /supplier/i.test(pinAct)) || (stAct && /supplier/i.test(stAct)) || replyLower.includes('supplier pin') || replyLower.includes('supplier state')) {
                role = 'Supplier';
            }
            const isBuyer = (role === 'Buyer');
            const entityDt = isBuyer ? (targetInv.buyerdt1 || {}) : (targetInv.supplierdt1 || {});
            let defPin = entityDt.buyer_pin || entityDt.supplier_pin || targetInv.buyer_pin || targetInv.supplier_pin || (isBuyer ? '400001' : '560001');
            let defSt = entityDt.buyer_state || entityDt.supplier_state || targetInv.buyer_state || targetInv.supplier_state || (isBuyer ? '27' : '29');

            barsHtml += `
                <div class="copilot-inline-suggestion-bar copilot-pin-state-bar" style="margin-top: 8px; margin-bottom: 6px; padding: 12px 14px; background: rgba(15, 23, 42, 0.95); border: 1px solid rgba(56, 189, 248, 0.45); border-radius: 8px; display: flex; flex-direction: column; gap: 8px;">
                    <span style="font-size: 0.82rem; font-weight: 700; color: #38bdf8;">📍 ${role} Postal PIN & State Jurisdiction:</span>
                    <input type="text" value="${escapeHtml(defPin)}">
                    <select>${buildStateOptionsHtml(defSt)}</select>
                    <button type="button" class="copilot-action-btn">📍 Apply PIN & State</button>
                </div>
            `;
        }
    };

    const renderVehicleBox = () => {
        if (renderedBoxCount > 0 || handledTypes.has('vehicle') || isVehJustPatched) return;
        const vehAct = findAction(a => /vehicle|veh|plate|ka01|mh12|vahan/i.test(a));
        const hasVehPrompt = Boolean(activeTopic === 'vehicle' || vehAct || replyLower.includes('vehicle') || replyLower.includes('vahan') || replyLower.includes('vehicle plate') || replyLower.includes('vehicle registration'));
        if (hasVehPrompt) {
            handledTypes.add('vehicle');
            renderedBoxCount++;
            let defVeh = 'KA01AB1234';
            if (vehAct) {
                const m = vehAct.match(/([A-Z]{2}[0-9]{1,2}[A-Z0-9]{1,4}[0-9]{4})/i);
                if (m) defVeh = m[1].toUpperCase();
            } else if (targetInv.ewbdt1 && targetInv.ewbdt1.veh_number) {
                defVeh = targetInv.ewbdt1.veh_number;
            } else if (targetInv.veh_number) {
                defVeh = targetInv.veh_number;
            }
            const defVehType = (targetInv.ewbdt1 && targetInv.ewbdt1.veh_type) || targetInv.veh_type || 'R';
            const defSubSupply = (targetInv.ewbdt1 && targetInv.ewbdt1.subsupplytype) || targetInv.subsupplytype || '1';
            barsHtml += `
                <div class="copilot-inline-suggestion-bar copilot-vehicle-picker-bar" style="margin-top: 8px; margin-bottom: 6px; padding: 12px 14px; background: rgba(15, 23, 42, 0.95); border: 1px solid rgba(56, 189, 248, 0.45); border-radius: 8px; display: flex; flex-direction: column; gap: 8px;">
                    <span style="font-size: 0.82rem; font-weight: 700; color: #38bdf8;">🚚 Vehicle Updation (Part-B Road Transit & E-Way Bill):</span>
                    <input type="text" data-field="vehicle" value="${escapeHtml(defVeh)}">
                    <select data-field="vehtype"><option value="R">R - Regular Road</option></select>
                    <select data-field="subsupply">${buildSubsupplyOptionsHtml(defSubSupply)}</select>
                    <button type="button" class="copilot-action-btn">✨ Apply & Verify Vehicle</button>
                </div>
            `;
        }
    };

    const renderHsnBox = () => {
        if (renderedBoxCount > 0 || handledTypes.has('hsn') || isHsnJustPatched) return;
        const hsnAct = findAction(a => /set hsn:|fix hsn/i.test(a));
        const hasHsnPrompt = Boolean(activeTopic === 'hsn' || hsnAct || replyLower.includes('quick question on product hsn') || replyLower.includes('wrong / incomplete hsn code') || replyLower.includes('wrong hsn code detected'));
        if (hasHsnPrompt) {
            handledTypes.add('hsn');
            renderedBoxCount++;
            let defHsn = '85011013';
            if (hsnAct) {
                const m = hsnAct.match(/\b([0-9]{2,8})\b/);
                if (m) defHsn = m[1];
            }
            let firstItm = null;
            if (targetInv.itemdtls && targetInv.itemdtls.length > 0) {
                firstItm = targetInv.itemdtls[0];
            } else if (targetInv.items && targetInv.items.length > 0) {
                firstItm = targetInv.items[0];
            }
            const prdName = (firstItm && (firstItm.prdnm || firstItm.prddesc)) ? (firstItm.prdnm || firstItm.prddesc) : 'Industrial Servo Motor';
            const defQty = (firstItm && firstItm.qty !== undefined) ? firstItm.qty : '5.0';
            let defUnitRate = (firstItm && (firstItm.unitprice || firstItm.unitrate || firstItm.unit_price)) ? (firstItm.unitprice || firstItm.unitrate || firstItm.unit_price) : '10000.00';
            let defTaxVal = (firstItm && (firstItm.assval !== undefined || firstItm.assamt !== undefined)) ? (firstItm.assval || firstItm.assamt) : (parseFloat(defQty) * parseFloat(defUnitRate)).toFixed(2);

            barsHtml += `
                <div class="copilot-inline-suggestion-bar copilot-hsn-pricing-bar" style="margin-top: 8px; margin-bottom: 6px; padding: 12px 14px; background: rgba(15, 23, 42, 0.95); border: 1px solid rgba(56, 189, 248, 0.45); border-radius: 8px; display: flex; flex-direction: column; gap: 8px;">
                    <span style="font-size: 0.82rem; font-weight: 700; color: #38bdf8;">📦 Product: ${prdName}</span>
                    <input type="text" data-field="hsn" value="${defHsn}">
                    <input type="number" data-field="rate" value="${defUnitRate}">
                    <input type="number" data-field="qty" value="${defQty}">
                    <input type="number" data-field="taxval" value="${defTaxVal}">
                    <button type="button" class="copilot-action-btn">✨ Apply & Recalculate Tax</button>
                </div>
            `;
        }
    };

    // Render active topic FIRST
    if (activeTopic === 'vehicle') renderVehicleBox();
    else if (activeTopic === 'hsn') renderHsnBox();
    else if (activeTopic === 'pin_state') renderPinStateBox();
    else if (activeTopic === 'date') renderDateBox();

    // Fallback sequence
    if (renderedBoxCount === 0) renderDateBox();
    if (renderedBoxCount === 0) renderPinStateBox();
    if (renderedBoxCount === 0) renderVehicleBox();
    if (renderedBoxCount === 0) renderHsnBox();

    // Standalone buttons
    for (const act of actions) {
        const actL = act.toLowerCase();
        if (
            (handledTypes.has('date') && (actL.includes('apply date') || actL.includes('set today') || actL.includes('change date to today') || actL.includes('change date to yesterday'))) ||
            (handledTypes.has('vehicle') && (actL.includes('vehicle') || actL.includes('vahan') || actL.includes('ka01') || actL.includes('plate') || actL.includes('disable e-way'))) ||
            (handledTypes.has('hsn') && (actL.includes('set hsn:') || actL.includes('fix hsn') || actL.includes('apply & recalculate') || actL.includes('ml lookup'))) ||
            (handledTypes.has('pin') && (actL.includes('set supplier pin') || actL.includes('set buyer pin') || actL.includes('pin:'))) ||
            (handledTypes.has('state') && (actL.includes('set supplier state') || actL.includes('set buyer state') || actL.includes('state:')))
        ) {
            continue;
        }
        standaloneButtons.push(act);
    }

    if (!standaloneButtons.some(b => b.includes('Auto-Fix All')) && !isCompliant) {
        standaloneButtons.unshift('⚡ Auto-Fix All Compliance Errors');
    }
    if (isCompliant) {
        if (!standaloneButtons.some(b => b.includes('Generate IRN'))) standaloneButtons.unshift('🚀 Generate IRN');
        if (!standaloneButtons.some(b => b.includes('Download'))) standaloneButtons.push('📥 Download Corrected JSON');
    }

    if (standaloneButtons.length > 0) {
        const btnsHtml = standaloneButtons.map(act => `<button type="button">${escapeHtml(act)}</button>`).join(' ');
        barsHtml += `<div class="msg-action-bar">${btnsHtml}</div>`;
    }

    return barsHtml;
}

// Tests
console.log('=== TEST 1: DATE STEP ===');
const res1 = renderCopilotSuggestionsHtml({
    reply: '👉 **Please change the document date:** Invoice date is older than 2 days...',
    interactive_actions: ['Change date to Today (2026-10-20)', 'Change date to Yesterday']
}, false, {});
console.log('Has Date Bar:', res1.includes('copilot-date-bar'));
console.log('Has Vehicle Bar:', res1.includes('copilot-vehicle-picker-bar'));
console.log('Has HSN Bar:', res1.includes('copilot-hsn-pricing-bar'));

console.log('\n=== TEST 2: PIN/STATE STEP ===');
const res2 = renderCopilotSuggestionsHtml({
    reply: '👉 **Government Portal Taxpayer Check on [buyerdt1.buyer_pin]:** Conflict: Pincode 560001...',
    patch_applied: true,
    patch_summary: ['Updated document date to 2026-10-20'],
    interactive_actions: ['Set Buyer PIN: 400001, State: 27', 'Set Buyer PIN: 400001']
}, false, {});
console.log('Has Date Bar:', res2.includes('copilot-date-bar'));
console.log('Has PIN Bar:', res2.includes('copilot-pin-state-bar'));
console.log('Has Vehicle Bar:', res2.includes('copilot-vehicle-picker-bar'));

console.log('\n=== TEST 3: VEHICLE STEP ===');
const res3 = renderCopilotSuggestionsHtml({
    reply: '👉 **Vehicle Registration Number Format Error:** Please update your vehicle registration number:',
    patch_applied: true,
    patch_summary: ['Set Buyer PIN: 400001, State: 27'],
    interactive_actions: ['Vehicle is KA01AB1234', 'Verify vehicle number', 'Disable E-Way Bill']
}, false, {});
console.log('Has Date Bar:', res3.includes('copilot-date-bar'));
console.log('Has PIN Bar:', res3.includes('copilot-pin-state-bar'));
console.log('Has Vehicle Bar:', res3.includes('copilot-vehicle-picker-bar'));

console.log('\n=== TEST 4: HSN STEP ===');
const res4 = renderCopilotSuggestionsHtml({
    reply: '👉 **Quick Question on Product HSN:** Wrong HSN Code Detected...',
    patch_applied: true,
    patch_summary: ['Verified & updated vehicle KA01AB1234 on live Vahan registry'],
    interactive_actions: ['Set HSN: 85011013', 'Fix HSN from product description']
}, false, {});
console.log('Has Vehicle Bar:', res4.includes('copilot-vehicle-picker-bar'));
console.log('Has HSN Bar:', res4.includes('copilot-hsn-pricing-bar'));

console.log('\n=== TEST 5: AFTER HSN IS DONE (DO NOT SHOW AGAIN) ===');
const res5 = renderCopilotSuggestionsHtml({
    reply: '🎉 All NIC compliance errors have been resolved! This invoice is now 100% compliant.',
    patch_applied: true,
    patch_summary: ['Updated item HSN: 8501 -> 85011013'],
    interactive_actions: ['🚀 Generate IRN', '📥 Download Corrected JSON']
}, true, {});
console.log('Has HSN Bar:', res5.includes('copilot-hsn-pricing-bar'));
console.log('Has IRN Button:', res5.includes('Generate IRN'));

console.log('\n=== TEST 6: USER ASKS VEHICLE ON COMPLIANT INVOICE ===');
const res6 = renderCopilotSuggestionsHtml({
    reply: '🚚 **Government Vehicle Portal Verification (MoRTH Vahan 4.0):** To verify your vehicle against the MoRTH Vahan 4.0 portal...',
    interactive_actions: ['Vehicle is KA01AB1234', 'Verify vehicle number', 'Disable E-Way Bill']
}, true, {});
console.log('Has Vehicle Bar in Editable Format:', res6.includes('copilot-vehicle-picker-bar'));
console.log('Has IRN Button as Standalone:', res6.includes('Generate IRN'));
