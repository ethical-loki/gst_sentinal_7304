import os
import re

NEW_FUNCTION = '''        // Helper to dynamically render editable input boxes for every suggestion
        function renderCopilotSuggestionsHtml(data, isCompliant, payload) {
            const actions = (data.interactive_actions || data.suggested_next_steps || []).slice();
            const replyLower = (data.reply || '').toLowerCase();
            const targetInv = (payload && payload.einvoices && payload.einvoices[0]) ? payload.einvoices[0] : (payload || {});
            let barsHtml = '';
            const standaloneButtons = [];
            const handledTypes = new Set();

            const findAction = (predicate) => actions.find(predicate);
            let renderedBoxCount = 0;

            // Extract active validation report and errors to check if issue is still unresolved
            const activeReport = data.validation_report || (typeof currentValidationReport !== 'undefined' ? currentValidationReport : null);
            const activeRes = (activeReport && activeReport.results && activeReport.results[0]) ? activeReport.results[0] : {};
            const activeErrors = activeRes.errors || [];

            // Detect whether HSN was just patched in this turn (if so, never repeat HSN command again)
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
                actions.some(a => /vehicle|veh|ka01|hsn|pin|state|date|mode|subsupply|gstin|tax\\s*math|transporter/i.test(a))
            );

            if (isCompliant && !hasInteractiveModule) {
                return `
                    <div class="msg-action-bar" style="margin-top: 12px; display: flex; gap: 8px; flex-wrap: wrap;">
                        <button type="button" class="copilot-action-btn" onclick="sendCopilotQuickMessage('🚀 Generate IRN')" style="background: linear-gradient(135deg, #10b981, #059669); color: #fff; font-weight: 700; border: none; padding: 7px 16px; border-radius: 8px; cursor: pointer; box-shadow: 0 4px 14px rgba(16, 185, 129, 0.35);">🚀 Generate IRN</button>
                        <button type="button" class="copilot-action-btn" onclick="sendCopilotQuickMessage('📥 Download Corrected JSON')" style="background: rgba(56, 189, 248, 0.15); border: 1px solid #38bdf8; color: #38bdf8; font-weight: 600; padding: 7px 14px; border-radius: 8px; cursor: pointer;">📥 Download Corrected JSON</button>
                    </div>
                `;
            }

            // Box Renderers: Each renders in the complete, interactive editable format
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
                        const m = dateAct.match(/\\b(\\d{4}-\\d{2}-\\d{2})\\b/);
                        if (m) defDate = m[1];
                    }
                    barsHtml += `
                        <div class="copilot-inline-suggestion-bar" style="margin-top: 8px; margin-bottom: 6px; padding: 10px 14px; background: rgba(15, 23, 42, 0.9); border: 1px solid rgba(56, 189, 248, 0.45); border-radius: 8px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                            <span style="font-size: 0.82rem; font-weight: 700; color: #38bdf8;">📅 Document Date:</span>
                            <input type="date" class="copilot-inline-custom-input" value="${defDate}" onkeydown="if(event.key==='Enter'){event.preventDefault();submitCopilotInlineInput(this, 'Change date to ');}" style="background: #090e1a; color: #f8fafc; border: 1px solid #38bdf8; border-radius: 6px; padding: 5px 9px; font-size: 0.84rem; outline: none; font-family: 'JetBrains Mono', monospace;">
                            <button type="button" class="copilot-action-btn" onclick="submitCopilotInlineInput(this, 'Change date to ')" style="background: linear-gradient(135deg, #0ea5e9, #6366f1); color: #fff; border: none; font-weight: 700; padding: 6px 14px; border-radius: 6px; cursor: pointer;">📅 Apply Date</button>
                            <button type="button" class="copilot-action-btn" onclick="sendCopilotQuickMessage('Change date to Today (${todayIso})')" style="background: rgba(16, 185, 129, 0.2); border: 1px solid #10b981; color: #34d399; font-weight: 600; padding: 6px 12px; border-radius: 6px; cursor: pointer;">⚡ Set Today</button>
                        </div>
                    `;
                }
            };

            const renderSupGstinBox = () => {
                if (renderedBoxCount > 0 || handledTypes.has('sup_gstin')) return;
                const supGstinAct = findAction(a => /my gstin is|supplier gstin/i.test(a));
                const hasSupGstinPrompt = Boolean(activeTopic === 'sup_gstin' || supGstinAct || replyLower.includes('proper 15-digit supplier gstin'));
                if (hasSupGstinPrompt) {
                    handledTypes.add('sup_gstin');
                    renderedBoxCount++;
                    let defGst = '29ABCDE1234F1ZW';
                    if (supGstinAct) {
                        const m = supGstinAct.match(/\\b([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z0-9]{1,3})\\b/i);
                        if (m) defGst = m[1].toUpperCase();
                    } else {
                        const mRep = replyLower.match(/government calculated correction:\\s*`?([0-9]{2}[a-z]{5}[0-9]{4}[a-z0-9]{1,3})`?/i);
                        if (mRep) {
                            defGst = mRep[1].toUpperCase();
                        } else if (targetInv.supplier_gstin || targetInv.self_gstin) {
                            const rawG = (targetInv.supplier_gstin || targetInv.self_gstin).trim();
                            defGst = rawG.length === 14 ? rawG + 'W' : (rawG.length >= 15 ? rawG : '29ABCDE1234F1ZW');
                        }
                    }
                    barsHtml += `
                        <div class="copilot-inline-suggestion-bar" style="margin-top: 8px; margin-bottom: 6px; padding: 10px 14px; background: rgba(15, 23, 42, 0.9); border: 1px solid rgba(56, 189, 248, 0.45); border-radius: 8px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                            <span style="font-size: 0.82rem; font-weight: 700; color: #38bdf8;">🏢 Supplier GSTIN:</span>
                            <input type="text" class="copilot-inline-custom-input" placeholder="15-digit GSTIN" value="${defGst}" maxlength="15" onkeydown="if(event.key==='Enter'){event.preventDefault();submitCopilotInlineInput(this, 'My GSTIN is ');}" style="background: #090e1a; color: #f8fafc; border: 1px solid #38bdf8; border-radius: 6px; padding: 5px 9px; font-size: 0.84rem; outline: none; font-family: 'JetBrains Mono', monospace; text-transform: uppercase; width: 175px;">
                            <button type="button" class="copilot-action-btn" onclick="submitCopilotInlineInput(this, 'My GSTIN is ')" style="background: linear-gradient(135deg, #0ea5e9, #6366f1); color: #fff; border: none; font-weight: 700; padding: 6px 14px; border-radius: 6px; cursor: pointer;">🏢 Apply GSTIN</button>
                        </div>
                    `;
                }
            };

            const renderBuyerGstinBox = () => {
                if (renderedBoxCount > 0 || handledTypes.has('buyer_gstin')) return;
                const buyerGstinAct = findAction(a => /buyer gstin is|buyer is urp|set buyer gstin/i.test(a));
                const hasBuyerGstinPrompt = Boolean(activeTopic === 'buyer_gstin' || buyerGstinAct || replyLower.includes('proper 15-digit buyer gstin'));
                if (hasBuyerGstinPrompt) {
                    handledTypes.add('buyer_gstin');
                    renderedBoxCount++;
                    let defBuyerGst = '29XYZAB5678C1Z2';
                    if (buyerGstinAct) {
                        const m = buyerGstinAct.match(/\\b([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z0-9]{1,3})\\b/i);
                        if (m) defBuyerGst = m[1].toUpperCase();
                        else if (buyerGstinAct.includes('URP')) defBuyerGst = 'URP';
                    }
                    barsHtml += `
                        <div class="copilot-inline-suggestion-bar" style="margin-top: 8px; margin-bottom: 6px; padding: 10px 14px; background: rgba(15, 23, 42, 0.9); border: 1px solid rgba(56, 189, 248, 0.45); border-radius: 8px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                            <span style="font-size: 0.82rem; font-weight: 700; color: #38bdf8;">👤 Buyer GSTIN:</span>
                            <input type="text" class="copilot-inline-custom-input" placeholder="Buyer GSTIN or URP" value="${defBuyerGst}" maxlength="15" onkeydown="if(event.key==='Enter'){event.preventDefault();submitCopilotInlineInput(this, 'Buyer GSTIN is ');}" style="background: #090e1a; color: #f8fafc; border: 1px solid #38bdf8; border-radius: 6px; padding: 5px 9px; font-size: 0.84rem; outline: none; font-family: 'JetBrains Mono', monospace; text-transform: uppercase; width: 175px;">
                            <button type="button" class="copilot-action-btn" onclick="submitCopilotInlineInput(this, 'Buyer GSTIN is ')" style="background: linear-gradient(135deg, #0ea5e9, #6366f1); color: #fff; border: none; font-weight: 700; padding: 6px 14px; border-radius: 6px; cursor: pointer;">👤 Apply Buyer GSTIN</button>
                            <button type="button" class="copilot-action-btn" onclick="sendCopilotQuickMessage('Buyer is URP (Unregistered)')" style="background: rgba(16, 185, 129, 0.2); border: 1px solid #10b981; color: #34d399; font-weight: 600; padding: 6px 12px; border-radius: 6px; cursor: pointer;">⚡ URP</button>
                        </div>
                    `;
                }
            };

            const renderModeBox = () => {
                if (renderedBoxCount > 0 || handledTypes.has('mode')) return;
                const modeAct = findAction(a => /set mode:/i.test(a));
                const hasModePrompt = Boolean(activeTopic === 'mode' || modeAct || replyLower.includes('delivery mode applies') || replyLower.includes('transaction mode'));
                if (hasModePrompt) {
                    handledTypes.add('mode');
                    renderedBoxCount++;
                    let defMode = 'REG';
                    if (modeAct) {
                        const m = modeAct.match(/\\b(REG|DIS|SHP|CMB)\\b/i);
                        if (m) defMode = m[1].toUpperCase();
                    }
                    barsHtml += `
                        <div class="copilot-inline-suggestion-bar" style="margin-top: 8px; margin-bottom: 6px; padding: 10px 14px; background: rgba(15, 23, 42, 0.9); border: 1px solid rgba(56, 189, 248, 0.45); border-radius: 8px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                            <span style="font-size: 0.82rem; font-weight: 700; color: #38bdf8;">🔄 Delivery Mode:</span>
                            <input type="text" class="copilot-inline-custom-input" placeholder="REG / DIS / SHP / CMB" value="${defMode}" maxlength="4" onkeydown="if(event.key==='Enter'){event.preventDefault();submitCopilotInlineInput(this, 'Set Mode: ');}" style="background: #090e1a; color: #f8fafc; border: 1px solid #38bdf8; border-radius: 6px; padding: 5px 9px; font-size: 0.84rem; outline: none; font-family: 'JetBrains Mono', monospace; text-transform: uppercase; width: 85px;">
                            <button type="button" class="copilot-action-btn" onclick="submitCopilotInlineInput(this, 'Set Mode: ')" style="background: linear-gradient(135deg, #0ea5e9, #6366f1); color: #fff; border: none; font-weight: 700; padding: 6px 14px; border-radius: 6px; cursor: pointer;">🔄 Apply Mode</button>
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
                        const m = hsnAct.match(/\\b([0-9]{2,8})\\b/);
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
                            <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap;">
                                <span style="font-size: 0.82rem; font-weight: 700; color: #38bdf8;">📦 Product: <span style="color: #f1f5f9; font-weight: 600;">${prdName}</span></span>
                                <span class="copilot-calc-summary-badge" style="font-size: 0.72rem; color: #34d399; font-family: 'JetBrains Mono', monospace; background: rgba(52, 211, 153, 0.1); padding: 2px 8px; border-radius: 4px; border: 1px solid rgba(52, 211, 153, 0.3);">GST 18% (₹9,000.00) ➔ Total: ₹59,000.00</span>
                            </div>
                            <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                                <div style="display: flex; flex-direction: column; gap: 2px;">
                                    <label style="font-size: 0.70rem; color: #94a3b8; font-weight: 600;">HSN CODE</label>
                                    <input type="text" data-field="hsn" class="copilot-inline-hsn-input" placeholder="e.g. 85011013" value="${defHsn}" maxlength="8" onkeydown="if(event.key==='Enter'){event.preventDefault();submitCopilotHsnInput(this);}" style="background: #090e1a; color: #f8fafc; border: 1px solid #38bdf8; border-radius: 6px; padding: 5px 9px; font-size: 0.84rem; outline: none; font-family: 'JetBrains Mono', monospace; width: 95px;">
                                </div>
                                <div style="display: flex; flex-direction: column; gap: 2px;">
                                    <label style="font-size: 0.70rem; color: #94a3b8; font-weight: 600;">RATE / PRICE (₹)</label>
                                    <input type="number" step="any" data-field="rate" class="copilot-inline-rate-input" placeholder="e.g. 10000" value="${defUnitRate}" oninput="updateCopilotHsnCalc(this)" onkeydown="if(event.key==='Enter'){event.preventDefault();submitCopilotHsnInput(this);}" style="background: #090e1a; color: #f8fafc; border: 1px solid #38bdf8; border-radius: 6px; padding: 5px 9px; font-size: 0.84rem; outline: none; font-family: 'JetBrains Mono', monospace; width: 110px;">
                                </div>
                                <div style="display: flex; flex-direction: column; gap: 2px;">
                                    <label style="font-size: 0.70rem; color: #94a3b8; font-weight: 600;">QTY</label>
                                    <input type="number" step="any" data-field="qty" class="copilot-inline-qty-input" placeholder="e.g. 5" value="${defQty}" oninput="updateCopilotHsnCalc(this)" onkeydown="if(event.key==='Enter'){event.preventDefault();submitCopilotHsnInput(this);}" style="background: #090e1a; color: #f8fafc; border: 1px solid #38bdf8; border-radius: 6px; padding: 5px 9px; font-size: 0.84rem; outline: none; font-family: 'JetBrains Mono', monospace; width: 75px;">
                                </div>
                                <div style="display: flex; flex-direction: column; gap: 2px;">
                                    <label style="font-size: 0.70rem; color: #94a3b8; font-weight: 600;">TAXABLE VALUE (₹)</label>
                                    <input type="number" step="any" data-field="taxval" class="copilot-inline-tax-input" placeholder="e.g. 50000" value="${defTaxVal}" oninput="updateCopilotHsnCalc(this)" onkeydown="if(event.key==='Enter'){event.preventDefault();submitCopilotHsnInput(this);}" style="background: #090e1a; color: #f8fafc; border: 1px solid #38bdf8; border-radius: 6px; padding: 5px 9px; font-size: 0.84rem; outline: none; font-family: 'JetBrains Mono', monospace; width: 125px;">
                                </div>
                                <div style="display: flex; align-items: flex-end; padding-top: 14px; gap: 6px;">
                                    <button type="button" class="copilot-action-btn" onclick="submitCopilotHsnInput(this)" style="background: linear-gradient(135deg, #0ea5e9, #6366f1); color: #fff; border: none; font-weight: 700; padding: 6px 14px; border-radius: 6px; cursor: pointer; white-space: nowrap;">✨ Apply & Recalculate Tax</button>
                                    <button type="button" class="copilot-action-btn" onclick="sendCopilotQuickMessage('Fix HSN from product description')" style="background: rgba(192, 132, 252, 0.2); border: 1px solid #c084fc; color: #e879f9; font-weight: 600; padding: 6px 12px; border-radius: 6px; cursor: pointer; white-space: nowrap;">⚡ ML Lookup</button>
                                </div>
                            </div>
                        </div>
                    `;
                }
            };

            const renderPinStateBox = () => {
                if (renderedBoxCount > 0 || handledTypes.has('pin')) return;
                const pinAct = findAction(a => /set (?:supplier|buyer)?\\s*pin:/i.test(a));
                const stAct = findAction(a => /set (?:supplier|buyer)?\\s*state:/i.test(a));
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

                    if (pinAct) {
                        const mPin = pinAct.match(/\\b([0-9]{6})\\b/);
                        if (mPin) defPin = mPin[1];
                    }
                    if (stAct) {
                        const mSt = stAct.match(/\\b([0-9]{1,2})\\b/);
                        if (mSt) defSt = mSt[1].padStart(2, '0');
                    }

                    barsHtml += `
                        <div class="copilot-inline-suggestion-bar copilot-pin-state-bar" style="margin-top: 8px; margin-bottom: 6px; padding: 12px 14px; background: rgba(15, 23, 42, 0.95); border: 1px solid rgba(56, 189, 248, 0.45); border-radius: 8px; display: flex; flex-direction: column; gap: 8px;">
                            <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap;">
                                <span style="font-size: 0.82rem; font-weight: 700; color: #38bdf8;">📍 ${role} Postal PIN & State Jurisdiction:</span>
                                <span style="font-size: 0.72rem; color: #34d399; font-family: 'JetBrains Mono', monospace; background: rgba(52, 211, 153, 0.1); padding: 2px 8px; border-radius: 4px; border: 1px solid rgba(52, 211, 153, 0.3);">GSTN Master Aligned</span>
                            </div>
                            <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                                <div style="display: flex; flex-direction: column; gap: 2px;">
                                    <label style="font-size: 0.70rem; color: #94a3b8; font-weight: 600;">6-DIGIT PIN</label>
                                    <input type="text" data-field="pin" class="copilot-inline-custom-input copilot-inline-pin-input" placeholder="e.g. 400001" value="${escapeHtml(defPin)}" maxlength="6" oninput="this.value = this.value.replace(/[^0-9]/g, ''); autoDetectStateFromPin(this);" onkeydown="if(event.key==='Enter'){event.preventDefault();submitCopilotPinStateInput(this, '${role}');}" style="background: #090e1a; color: #f8fafc; border: 1px solid #38bdf8; border-radius: 6px; padding: 5px 9px; font-size: 0.84rem; outline: none; font-family: 'JetBrains Mono', monospace; width: 100px; font-weight: 700;">
                                </div>
                                <div style="display: flex; flex-direction: column; gap: 2px;">
                                    <label style="font-size: 0.70rem; color: #94a3b8; font-weight: 600;">STATE / UT</label>
                                    <select data-field="state" class="copilot-inline-state-select" style="background: #090e1a; color: #f8fafc; border: 1px solid #38bdf8; border-radius: 6px; padding: 5px 8px; font-size: 0.84rem; outline: none; font-family: 'JetBrains Mono', monospace; cursor: pointer; max-width: 220px;">
                                        ${buildStateOptionsHtml(defSt)}
                                    </select>
                                </div>
                                <div style="display: flex; align-items: flex-end; padding-top: 14px; gap: 6px; flex-wrap: wrap;">
                                    <button type="button" class="copilot-action-btn" onclick="submitCopilotPinStateInput(this, '${role}')" style="background: linear-gradient(135deg, #0ea5e9, #6366f1); color: #fff; border: none; font-weight: 700; padding: 6px 14px; border-radius: 6px; cursor: pointer; white-space: nowrap;">📍 Apply PIN & State</button>
                                    <button type="button" class="copilot-action-btn" onclick="sendCopilotQuickMessage('Fix state and pin code mismatch')" style="background: rgba(16, 185, 129, 0.2); border: 1px solid #10b981; color: #34d399; font-weight: 600; padding: 6px 12px; border-radius: 6px; cursor: pointer; white-space: nowrap;">⚡ Auto-Align to GSTIN</button>
                                </div>
                            </div>
                        </div>
                    `;
                }
            };

            const renderSubsupplyBox = () => {
                if (renderedBoxCount > 0 || handledTypes.has('subsupply')) return;
                const subAct = findAction(a => /subsupply|sub-supply/i.test(a));
                const hasSubPrompt = Boolean(activeTopic === 'subsupply' || subAct || replyLower.includes('sub-supply') || replyLower.includes('subsupply'));
                if (hasSubPrompt) {
                    handledTypes.add('subsupply');
                    renderedBoxCount++;
                    let defSub = (targetInv.ewbdt1 && targetInv.ewbdt1.subsupplytype) || targetInv.subsupplytype || '1';
                    if (subAct) {
                        const m = subAct.match(/\\b([1-8])\\b/);
                        if (m) defSub = m[1];
                    }
                    barsHtml += `
                        <div class="copilot-inline-suggestion-bar copilot-subsupply-bar" style="margin-top: 8px; margin-bottom: 6px; padding: 12px 14px; background: rgba(15, 23, 42, 0.95); border: 1px solid rgba(56, 189, 248, 0.45); border-radius: 8px; display: flex; flex-direction: column; gap: 8px;">
                            <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap;">
                                <span style="font-size: 0.82rem; font-weight: 700; color: #38bdf8;">📦 Sub-Supply Types & Master Codes (Outward):</span>
                                <span style="font-size: 0.72rem; color: #38bdf8; font-family: 'JetBrains Mono', monospace; background: rgba(56, 189, 248, 0.1); padding: 2px 8px; border-radius: 4px; border: 1px solid rgba(56, 189, 248, 0.3);">NIC E-Way Bill Rulebook</span>
                            </div>
                            <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                                <div style="display: flex; flex-direction: column; gap: 2px; flex: 1; min-width: 260px;">
                                    <label style="font-size: 0.70rem; color: #94a3b8; font-weight: 600;">OUTWARD SUB-SUPPLY TYPE</label>
                                    <select data-field="subsupply" class="copilot-inline-subsupply-select" style="background: #090e1a; color: #f8fafc; border: 1px solid #38bdf8; border-radius: 6px; padding: 5px 8px; font-size: 0.84rem; outline: none; font-family: 'JetBrains Mono', monospace; cursor: pointer; width: 100%;">
                                        ${buildSubsupplyOptionsHtml(defSub)}
                                    </select>
                                </div>
                                <div style="display: flex; align-items: flex-end; padding-top: 14px; gap: 6px; flex-wrap: wrap;">
                                    <button type="button" class="copilot-action-btn" onclick="submitCopilotSubsupplyInput(this)" style="background: linear-gradient(135deg, #0ea5e9, #6366f1); color: #fff; border: none; font-weight: 700; padding: 6px 14px; border-radius: 6px; cursor: pointer; white-space: nowrap;">✨ Apply Sub-Supply</button>
                                    <button type="button" class="copilot-action-btn" onclick="sendCopilotQuickMessage('Disable E-Way Bill')" style="background: rgba(239, 68, 68, 0.15); border: 1px solid #ef4444; color: #f87171; font-weight: 600; padding: 6px 12px; border-radius: 6px; cursor: pointer; white-space: nowrap;">🚫 Disable E-Way Bill</button>
                                </div>
                            </div>
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
                            <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap;">
                                <span style="font-size: 0.82rem; font-weight: 700; color: #38bdf8;">🚚 Vehicle Updation (Part-B Road Transit & E-Way Bill):</span>
                                <span style="font-size: 0.72rem; color: #38bdf8; font-family: 'JetBrains Mono', monospace; background: rgba(56, 189, 248, 0.1); padding: 2px 8px; border-radius: 4px; border: 1px solid rgba(56, 189, 248, 0.3);">MoRTH Vahan / RTO Validated</span>
                            </div>
                            <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                                <div style="display: flex; flex-direction: column; gap: 2px;">
                                    <label style="font-size: 0.70rem; color: #94a3b8; font-weight: 600;">VEHICLE NUMBER</label>
                                    <input type="text" data-field="vehicle" class="copilot-inline-custom-input copilot-inline-vehicle-input" placeholder="e.g. KA01AB1234" value="${escapeHtml(defVeh)}" maxlength="15" oninput="this.value = this.value.toUpperCase().replace(/[^A-Z0-9]/g, '')" onkeydown="if(event.key==='Enter'){event.preventDefault();submitCopilotVehicleInput(this);}" style="background: #090e1a; color: #f8fafc; border: 1px solid #38bdf8; border-radius: 6px; padding: 5px 9px; font-size: 0.84rem; outline: none; font-family: 'JetBrains Mono', monospace; text-transform: uppercase; width: 130px; font-weight: 700; letter-spacing: 0.5px;">
                                </div>
                                <div style="display: flex; flex-direction: column; gap: 2px;">
                                    <label style="font-size: 0.70rem; color: #94a3b8; font-weight: 600;">VEHICLE TYPE</label>
                                    <select data-field="vehtype" class="copilot-inline-vehtype-select" style="background: #090e1a; color: #f8fafc; border: 1px solid #38bdf8; border-radius: 6px; padding: 5px 8px; font-size: 0.84rem; outline: none; font-family: 'JetBrains Mono', monospace; cursor: pointer;">
                                        <option value="R" ${defVehType==='R'?'selected':''}>R - Regular Road</option>
                                        <option value="O" ${defVehType==='O'?'selected':''}>O - Over Dimensional Cargo</option>
                                    </select>
                                </div>
                                <div style="display: flex; flex-direction: column; gap: 2px; min-width: 220px;">
                                    <label style="font-size: 0.70rem; color: #94a3b8; font-weight: 600;">SUB-SUPPLY TYPE</label>
                                    <select data-field="subsupply" class="copilot-inline-subsupply-select" style="background: #090e1a; color: #f8fafc; border: 1px solid #38bdf8; border-radius: 6px; padding: 5px 8px; font-size: 0.84rem; outline: none; font-family: 'JetBrains Mono', monospace; cursor: pointer;">
                                        ${buildSubsupplyOptionsHtml(defSubSupply)}
                                    </select>
                                </div>
                                <div style="display: flex; align-items: flex-end; padding-top: 14px; gap: 6px; flex-wrap: wrap;">
                                    <button type="button" class="copilot-action-btn" onclick="submitCopilotVehicleInput(this)" style="background: linear-gradient(135deg, #0ea5e9, #6366f1); color: #fff; border: none; font-weight: 700; padding: 6px 14px; border-radius: 6px; cursor: pointer; white-space: nowrap;">✨ Apply & Verify Vehicle</button>
                                    <button type="button" class="copilot-action-btn" onclick="sendCopilotQuickMessage('Vehicle is KA01AB1234')" style="background: rgba(16, 185, 129, 0.2); border: 1px solid #10b981; color: #34d399; font-weight: 600; padding: 6px 12px; border-radius: 6px; cursor: pointer; white-space: nowrap;">⚡ Use KA01AB1234</button>
                                    <button type="button" class="copilot-action-btn" onclick="sendCopilotQuickMessage('Disable E-Way Bill')" style="background: rgba(239, 68, 68, 0.15); border: 1px solid #ef4444; color: #f87171; font-weight: 600; padding: 6px 12px; border-radius: 6px; cursor: pointer; white-space: nowrap;">🚫 Disable E-Way Bill</button>
                                </div>
                            </div>
                        </div>
                    `;
                }
            };

            const renderTransporterBox = () => {
                if (renderedBoxCount > 0 || handledTypes.has('transporter')) return;
                const transAct = findAction(a => /set transporter:/i.test(a));
                const hasTransPrompt = Boolean(activeTopic === 'transporter' || transAct || replyLower.includes('transporter gstin / id') || replyLower.includes('transporter id'));
                if (hasTransPrompt) {
                    handledTypes.add('transporter');
                    renderedBoxCount++;
                    let defTrans = '29ABCDE1234F1Z5';
                    if (transAct) {
                        const m = transAct.match(/\\b([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z0-9]{1,3})\\b/i);
                        if (m) defTrans = m[1].toUpperCase();
                    }
                    barsHtml += `
                        <div class="copilot-inline-suggestion-bar" style="margin-top: 8px; margin-bottom: 6px; padding: 10px 14px; background: rgba(15, 23, 42, 0.9); border: 1px solid rgba(56, 189, 248, 0.45); border-radius: 8px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                            <span style="font-size: 0.82rem; font-weight: 700; color: #38bdf8;">🚛 Transporter ID:</span>
                            <input type="text" class="copilot-inline-custom-input" placeholder="Transporter GSTIN" value="${defTrans}" maxlength="15" onkeydown="if(event.key==='Enter'){event.preventDefault();submitCopilotInlineInput(this, 'Set Transporter: ');}" style="background: #090e1a; color: #f8fafc; border: 1px solid #38bdf8; border-radius: 6px; padding: 5px 9px; font-size: 0.84rem; outline: none; font-family: 'JetBrains Mono', monospace; text-transform: uppercase; width: 175px;">
                            <button type="button" class="copilot-action-btn" onclick="submitCopilotInlineInput(this, 'Set Transporter: ')" style="background: linear-gradient(135deg, #0ea5e9, #6366f1); color: #fff; border: none; font-weight: 700; padding: 6px 14px; border-radius: 6px; cursor: pointer;">🚛 Apply Transporter</button>
                        </div>
                    `;
                }
            };

            const renderTaxMathBox = () => {
                if (renderedBoxCount > 0 || handledTypes.has('tax_math')) return;
                const taxMathAct = findAction(a => /rebalance tax math|tax math/i.test(a));
                const hasTaxMathPrompt = Boolean(activeTopic === 'tax_math' || taxMathAct || replyLower.includes('tax valuation recalculation') || replyLower.includes('tax math imbalance'));
                if (hasTaxMathPrompt) {
                    handledTypes.add('tax_math');
                    renderedBoxCount++;
                    let defTot = '59000.00';
                    if (targetInv && targetInv.valdtls && targetInv.valdtls.assval) {
                        const assval = parseFloat(targetInv.valdtls.assval) || 50000;
                        const cgst = parseFloat(targetInv.valdtls.cgstval) || 0;
                        const sgst = parseFloat(targetInv.valdtls.sgstval) || 0;
                        const igst = parseFloat(targetInv.valdtls.igstval) || 0;
                        defTot = (assval + cgst + sgst + igst).toFixed(2);
                    }
                    barsHtml += `
                        <div class="copilot-inline-suggestion-bar" style="margin-top: 8px; margin-bottom: 6px; padding: 10px 14px; background: rgba(15, 23, 42, 0.9); border: 1px solid rgba(56, 189, 248, 0.45); border-radius: 8px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                            <span style="font-size: 0.82rem; font-weight: 700; color: #38bdf8;">💰 Invoice Total (₹):</span>
                            <input type="number" step="0.01" class="copilot-inline-custom-input" placeholder="e.g. 59000.00" value="${defTot}" onkeydown="if(event.key==='Enter'){event.preventDefault();sendCopilotQuickMessage('Rebalance tax math and invoice value');}" style="background: #090e1a; color: #f8fafc; border: 1px solid #38bdf8; border-radius: 6px; padding: 5px 9px; font-size: 0.84rem; outline: none; font-family: 'JetBrains Mono', monospace; width: 130px;">
                            <button type="button" class="copilot-action-btn" onclick="sendCopilotQuickMessage('Rebalance tax math and invoice value')" style="background: linear-gradient(135deg, #0ea5e9, #6366f1); color: #fff; border: none; font-weight: 700; padding: 6px 14px; border-radius: 6px; cursor: pointer;">💰 Rebalance Tax Math</button>
                        </div>
                    `;
                }
            };

            // 1. Render active focus topic FIRST
            if (activeTopic === 'vehicle') renderVehicleBox();
            else if (activeTopic === 'hsn') renderHsnBox();
            else if (activeTopic === 'pin_state') renderPinStateBox();
            else if (activeTopic === 'date') renderDateBox();
            else if (activeTopic === 'sup_gstin') renderSupGstinBox();
            else if (activeTopic === 'buyer_gstin') renderBuyerGstinBox();
            else if (activeTopic === 'mode') renderModeBox();
            else if (activeTopic === 'subsupply') renderSubsupplyBox();
            else if (activeTopic === 'transporter') renderTransporterBox();
            else if (activeTopic === 'tax_math') renderTaxMathBox();

            // 2. If no active topic was rendered, fall back to step-by-step sequence of unresolved issues
            if (renderedBoxCount === 0) renderDateBox();
            if (renderedBoxCount === 0) renderPinStateBox();
            if (renderedBoxCount === 0) renderVehicleBox();
            if (renderedBoxCount === 0) renderHsnBox();
            if (renderedBoxCount === 0) renderSupGstinBox();
            if (renderedBoxCount === 0) renderBuyerGstinBox();
            if (renderedBoxCount === 0) renderModeBox();
            if (renderedBoxCount === 0) renderSubsupplyBox();
            if (renderedBoxCount === 0) renderTransporterBox();
            if (renderedBoxCount === 0) renderTaxMathBox();

            // 3. Fallback for any other "Set Key: Value" or "Key is Value" suggestion (strictly one-by-one)
            for (const act of actions) {
                const actL = act.toLowerCase();
                if (
                    (handledTypes.has('date') && (actL.includes('apply date') || actL.includes('set today') || actL.includes('change date to today') || actL.includes('change date to yesterday'))) ||
                    (handledTypes.has('vehicle') && (actL.includes('vehicle') || actL.includes('vahan') || actL.includes('ka01') || actL.includes('plate') || actL.includes('disable e-way'))) ||
                    (handledTypes.has('sup_gstin') && (actL.includes('my gstin is') || actL.includes('supplier gstin'))) ||
                    (handledTypes.has('buyer_gstin') && (actL.includes('buyer gstin is') || actL.includes('buyer is urp'))) ||
                    (handledTypes.has('hsn') && (actL.includes('set hsn:') || actL.includes('fix hsn') || actL.includes('apply & recalculate') || actL.includes('ml lookup'))) ||
                    (handledTypes.has('pin') && (actL.includes('set supplier pin') || actL.includes('set buyer pin') || actL.includes('pin:'))) ||
                    (handledTypes.has('state') && (actL.includes('set supplier state') || actL.includes('set buyer state') || actL.includes('state:'))) ||
                    (handledTypes.has('subsupply') && actL.includes('subsupply')) ||
                    (handledTypes.has('mode') && actL.includes('set mode:')) ||
                    (handledTypes.has('transporter') && actL.includes('set transporter:')) ||
                    (handledTypes.has('tax_math') && actL.includes('rebalance tax math'))
                ) {
                    continue;
                }

                // Check for ANY other "Set Key: Value" or "Key is Value" suggestion
                const kvMatch = act.match(/^(?:Set\\s+)?([A-Za-z0-9_\\s]+?)(?:\\s*[:=]|\\s+is)\\s*(.+)$/i);
                if (kvMatch && !act.includes('Auto-Fix') && !act.includes('IRN') && !act.includes('Download') && !act.includes('Disable')) {
                    const keyName = kvMatch[1].trim();
                    const valVal = kvMatch[2].trim();
                    const keySlug = keyName.toLowerCase().replace(/\\s+/g, '_');
                    if (renderedBoxCount === 0 && !handledTypes.has(keySlug)) {
                        handledTypes.add(keySlug);
                        renderedBoxCount++;
                        barsHtml += `
                            <div class="copilot-inline-suggestion-bar" style="margin-top: 8px; margin-bottom: 6px; padding: 10px 14px; background: rgba(15, 23, 42, 0.9); border: 1px solid rgba(56, 189, 248, 0.45); border-radius: 8px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                                <span style="font-size: 0.82rem; font-weight: 700; color: #38bdf8;">✏️ ${escapeHtml(keyName)}:</span>
                                <input type="text" class="copilot-inline-custom-input" value="${escapeHtml(valVal)}" onkeydown="if(event.key==='Enter'){event.preventDefault();submitCopilotInlineInput(this, 'Set ${escapeHtml(keyName)}: ');}" style="background: #090e1a; color: #f8fafc; border: 1px solid #38bdf8; border-radius: 6px; padding: 5px 9px; font-size: 0.84rem; outline: none; font-family: 'JetBrains Mono', monospace; width: 140px;">
                                <button type="button" class="copilot-action-btn" onclick="submitCopilotInlineInput(this, 'Set ${escapeHtml(keyName)}: ')" style="background: linear-gradient(135deg, #0ea5e9, #6366f1); color: #fff; border: none; font-weight: 700; padding: 6px 14px; border-radius: 6px; cursor: pointer;">Apply</button>
                            </div>
                        `;
                        continue;
                    }
                }

                standaloneButtons.push(act);
            }

            if (!standaloneButtons.some(b => b.includes('Auto-Fix All')) && !isCompliant) {
                standaloneButtons.unshift('⚡ Auto-Fix All Compliance Errors');
            }

            if (isCompliant) {
                if (!standaloneButtons.some(b => b.includes('Generate IRN'))) {
                    standaloneButtons.unshift('🚀 Generate IRN');
                }
                if (!standaloneButtons.some(b => b.includes('Download'))) {
                    standaloneButtons.push('📥 Download Corrected JSON');
                }
            }

            if (standaloneButtons.length > 0) {
                const btnsHtml = standaloneButtons.map(act => {
                    const isHighlight = act.includes('Auto-Fix') || act.includes('Generate IRN');
                    const style = isHighlight 
                        ? 'background: linear-gradient(135deg, #ec4899, #8b5cf6); color: #fff; font-weight: 700; border: none; padding: 7px 15px; border-radius: 8px; cursor: pointer; box-shadow: 0 4px 14px rgba(236, 72, 153, 0.35);'
                        : 'background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(56, 189, 248, 0.4); color: #38bdf8; font-weight: 600; padding: 6px 13px; border-radius: 8px; cursor: pointer;';
                    return `<button type="button" class="copilot-action-btn" style="${style}" onclick="sendCopilotQuickMessage('${escapeHtml(act)}')">${escapeHtml(act)}</button>`;
                }).join(' ');
                barsHtml += `<div class="msg-action-bar" style="margin-top: 10px; display: flex; gap: 8px; flex-wrap: wrap;">${btnsHtml}</div>`;
            }

            return barsHtml;
        }'''

files_to_update = [
    "frontend/converter.html",
    "static/converter.html",
    "frontend/ingestion.html",
    "static/ingestion.html",
    "src/ui/ingestion.html",
    "gst_sentinal_7304/frontend/converter.html",
    "gst_sentinal_7304/static/converter.html",
    "gst_sentinal_7304/frontend/ingestion.html",
    "gst_sentinal_7304/static/ingestion.html",
    "gst_sentinal_7304/src/ui/ingestion.html"
]

pattern = re.compile(r'(\s*// Helper to dynamically render editable input boxes for every suggestion\s*function renderCopilotSuggestionsHtml\(data, isCompliant, payload\) \{[\s\S]*?\n\s*return barsHtml;\s*\n\s*\})', re.MULTILINE)

for rel_path in files_to_update:
    if os.path.exists(rel_path):
        with open(rel_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        m = pattern.search(content)
        if m:
            new_content = content[:m.start()] + '\n' + NEW_FUNCTION + content[m.end():]
            with open(rel_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f"[OK] Updated {rel_path}")
        else:
            print(f"[WARN] Pattern not found in {rel_path}")
    else:
        print(f"[SKIP] Does not exist: {rel_path}")
