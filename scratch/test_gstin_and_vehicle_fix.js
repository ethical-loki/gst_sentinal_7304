const fs = require('fs');

function createRenderer(buildSubsupplyOptionsHtml, buildStateOptionsHtml, escapeHtml) {
    return function renderCopilotSuggestionsHtml(data, isCompliant, payload) {
        const actions = (data.interactive_actions || data.suggested_next_steps || []).slice();
        const replyLower = (data.reply || '').toLowerCase();
        const targetInv = (payload && payload.einvoices && payload.einvoices[0]) ? payload.einvoices[0] : (payload || {});
        let barsHtml = '';
        const standaloneButtons = [];
        const handledTypes = new Set();

        const findAction = (predicate) => actions.find(predicate);
        let renderedBoxCount = 0;

        // Detect patch summary items from current turn
        const patchSummary = (data.patch_summary || []).map(s => String(s).toLowerCase());
        const isDateJustPatched = Boolean(data.patch_applied && patchSummary.some(s => s.includes('date')));
        const isVehJustPatched = Boolean(data.patch_applied && patchSummary.some(s => s.includes('veh')));
        const isHsnJustPatched = Boolean(data.patch_applied && patchSummary.some(s => s.includes('hsn')));
        const isSupGstJustPatched = Boolean(data.patch_applied && patchSummary.some(s => s.includes('supplier gstin') || s.includes('self_gstin')));
        const isBuyerGstJustPatched = Boolean(data.patch_applied && patchSummary.some(s => s.includes('buyer gstin') || s.includes('urp')));
        const isPinJustPatched = Boolean(data.patch_applied && patchSummary.some(s => s.includes('pin')));
        const isStateJustPatched = Boolean(data.patch_applied && patchSummary.some(s => s.includes('state')));

        if (isDateJustPatched) handledTypes.add('date');
        if (isVehJustPatched) handledTypes.add('vehicle');
        if (isHsnJustPatched) handledTypes.add('hsn');
        if (isSupGstJustPatched) handledTypes.add('sup_gstin');
        if (isBuyerGstJustPatched) handledTypes.add('buyer_gstin');
        if (isPinJustPatched) handledTypes.add('pin');
        if (isStateJustPatched) handledTypes.add('state');

        // Check if vehicle in payload is ALREADY valid
        const currVeh = (targetInv.ewbdt1 && targetInv.ewbdt1.veh_number) || targetInv.veh_number || '';
        const cleanVeh = String(currVeh).replace(/[^A-Za-z0-9]/g, '').toUpperCase();
        const isVehFormatValid = /^[A-Z]{2}[0-9]{1,2}[A-Z0-9]{1,4}[0-9]{4}$/.test(cleanVeh);

        // Check if IRN is already generated
        const hasActiveIrn = Boolean(
            (targetInv && (targetInv.irn || targetInv.irn_status === 'GENERATED' || targetInv.status === 'IRN_GENERATED' || (targetInv.docdt1 && targetInv.docdt1.irn))) ||
            replyLower.includes('active irn') ||
            replyLower.includes('irn generated') ||
            replyLower.includes('irn (invoice reference number)') ||
            replyLower.includes('invoice is 100% compliant with active irn') ||
            patchSummary.some(s => s.includes('generated official nic irn') || s.includes('irn:'))
        );

        // Check 100% compliance
        const isFullyCompliant = Boolean(
            isCompliant ||
            replyLower.includes('all nic compliance errors have been resolved') ||
            replyLower.includes('0 unresolved errors remaining') ||
            replyLower.includes('ready for irn generation') ||
            replyLower.includes('100% compliant') ||
            replyLower.includes('generate the official nic irn') ||
            hasActiveIrn
        );

        const hasPendingCorrections = actions.some(a => /set (?:supplier|buyer)?\s*(?:pin|state|hsn|mode|transporter):|change date to|vehicle is/i.test(a));
        if (isFullyCompliant && !hasPendingCorrections) {
            if (hasActiveIrn) {
                return `
                    <div class="msg-action-bar" style="margin-top: 12px; display: flex; gap: 8px; flex-wrap: wrap;">
                        <button type="button" class="copilot-action-btn" onclick="sendCopilotQuickMessage('📥 Download Corrected JSON')" style="background: linear-gradient(135deg, #0ea5e9, #6366f1); color: #fff; font-weight: 700; border: none; padding: 7px 18px; border-radius: 8px; cursor: pointer; box-shadow: 0 4px 14px rgba(14, 165, 233, 0.35);">📥 Download Corrected JSON</button>
                    </div>
                `;
            }
            return `
                <div class="msg-action-bar" style="margin-top: 12px; display: flex; gap: 8px; flex-wrap: wrap;">
                    <button type="button" class="copilot-action-btn" onclick="sendCopilotQuickMessage('🚀 Generate IRN')" style="background: linear-gradient(135deg, #10b981, #059669); color: #fff; font-weight: 700; border: none; padding: 7px 16px; border-radius: 8px; cursor: pointer; box-shadow: 0 4px 14px rgba(16, 185, 129, 0.35);">🚀 Generate IRN</button>
                    <button type="button" class="copilot-action-btn" onclick="sendCopilotQuickMessage('📥 Download Corrected JSON')" style="background: rgba(56, 189, 248, 0.15); border: 1px solid #38bdf8; color: #38bdf8; font-weight: 600; padding: 7px 14px; border-radius: 8px; cursor: pointer;">📥 Download Corrected JSON</button>
                </div>
            `;
        }

        // Extract tailPrompt: isolate the active step prompt to avoid false positives from past turn acknowledgments and error lists
        let tailPrompt = replyLower;
        const lastPromptIdx = Math.max(
            replyLower.lastIndexOf('step-by-step resolution'),
            replyLower.lastIndexOf('👉'),
            replyLower.lastIndexOf('---')
        );
        if (lastPromptIdx !== -1) {
            tailPrompt = replyLower.substring(lastPromptIdx);
        }

        // Detect active focus topic strictly:
        // Priority 1: Direct action suggestions provided by the backend resolver for this turn
        let activeTopic = null;
        if (!isPinJustPatched && !isStateJustPatched && actions.some(a => /set (?:supplier|buyer)?\s*(?:pin|state):|pin\s*:\s*\d+/i.test(a))) {
            activeTopic = 'pin_state';
        } else if (!isSupGstJustPatched && actions.some(a => /my gstin is|supplier gstin/i.test(a))) {
            activeTopic = 'sup_gstin';
        } else if (!isBuyerGstJustPatched && actions.some(a => /buyer gstin is|buyer is urp|set buyer gstin/i.test(a))) {
            activeTopic = 'buyer_gstin';
        } else if (!isDateJustPatched && actions.some(a => /change date to|set date:/i.test(a))) {
            activeTopic = 'date';
        } else if (!isHsnJustPatched && actions.some(a => /set hsn:|fix hsn/i.test(a))) {
            activeTopic = 'hsn';
        } else if (!isVehJustPatched && actions.some(a => /vehicle is|verify vehicle/i.test(a))) {
            activeTopic = 'vehicle';
        } else if (actions.some(a => /set mode:/i.test(a))) {
            activeTopic = 'mode';
        } else if (actions.some(a => /subsupply/i.test(a))) {
            activeTopic = 'subsupply';
        } else if (actions.some(a => /transporter/i.test(a))) {
            activeTopic = 'transporter';
        } else if (actions.some(a => /rebalance tax/i.test(a))) {
            activeTopic = 'tax_math';
        }

        // Priority 2: Inquire tailPrompt if actions list didn't directly determine topic
        if (!activeTopic) {
            if (!isPinJustPatched && !isStateJustPatched && !tailPrompt.includes('aligned!') && !tailPrompt.includes('updated!') && (tailPrompt.includes('postal pin') || tailPrompt.includes('pincode conflict') || tailPrompt.includes('pincode mismatch') || tailPrompt.includes('taxpayer check on'))) {
                activeTopic = 'pin_state';
            } else if (!isSupGstJustPatched && (tailPrompt.includes('supplier gstin') || tailPrompt.includes('my gstin is') || tailPrompt.includes('15-digit supplier gstin'))) {
                activeTopic = 'sup_gstin';
            } else if (!isBuyerGstJustPatched && (tailPrompt.includes('buyer gstin') || tailPrompt.includes('recipient gstin') || tailPrompt.includes('15-digit buyer gstin'))) {
                activeTopic = 'buyer_gstin';
            } else if (!isDateJustPatched && (tailPrompt.includes('document date') || tailPrompt.includes('change the document date') || tailPrompt.includes('invoice date') || tailPrompt.includes('date to within'))) {
                activeTopic = 'date';
            } else if (!isHsnJustPatched && (tailPrompt.includes('product hsn') || tailPrompt.includes('wrong hsn code') || tailPrompt.includes('wrong / incomplete hsn') || tailPrompt.includes('hsn intelligence'))) {
                activeTopic = 'hsn';
            } else if (!isVehJustPatched && (tailPrompt.includes('what is your vehicle registration') || tailPrompt.includes('vehicle registration number') || tailPrompt.includes('vehicle plate') || tailPrompt.includes('e-way bill road transit'))) {
                activeTopic = 'vehicle';
            } else if (tailPrompt.includes('delivery mode applies') || tailPrompt.includes('transaction mode')) {
                activeTopic = 'mode';
            } else if (tailPrompt.includes('sub-supply') || tailPrompt.includes('subsupply')) {
                activeTopic = 'subsupply';
            } else if (tailPrompt.includes('transporter gstin') || tailPrompt.includes('transporter id')) {
                activeTopic = 'transporter';
            } else if (tailPrompt.includes('tax valuation recalculation') || tailPrompt.includes('tax math imbalance')) {
                activeTopic = 'tax_math';
            }
        }

        // If 100% compliant AND no interactive module is being discussed or requested, show Generate IRN / Download
        const hasInteractiveModule = Boolean(
            activeTopic ||
            actions.some(a => /vehicle|veh|ka01|hsn|pin|state|date|mode|subsupply|gstin|tax\s*math|transporter/i.test(a))
        );

        if (isCompliant && !hasInteractiveModule) {
            if (hasActiveIrn) {
                return `
                    <div class="msg-action-bar" style="margin-top: 12px; display: flex; gap: 8px; flex-wrap: wrap;">
                        <button type="button" class="copilot-action-btn" onclick="sendCopilotQuickMessage('📥 Download Corrected JSON')" style="background: linear-gradient(135deg, #0ea5e9, #6366f1); color: #fff; font-weight: 700; border: none; padding: 7px 18px; border-radius: 8px; cursor: pointer; box-shadow: 0 4px 14px rgba(14, 165, 233, 0.35);">📥 Download Corrected JSON</button>
                    </div>
                `;
            }
            return `
                <div class="msg-action-bar" style="margin-top: 12px; display: flex; gap: 8px; flex-wrap: wrap;">
                    <button type="button" class="copilot-action-btn" onclick="sendCopilotQuickMessage('🚀 Generate IRN')" style="background: linear-gradient(135deg, #10b981, #059669); color: #fff; font-weight: 700; border: none; padding: 7px 16px; border-radius: 8px; cursor: pointer; box-shadow: 0 4px 14px rgba(16, 185, 129, 0.35);">🚀 Generate IRN</button>
                    <button type="button" class="copilot-action-btn" onclick="sendCopilotQuickMessage('📥 Download Corrected JSON')" style="background: rgba(56, 189, 248, 0.15); border: 1px solid #38bdf8; color: #38bdf8; font-weight: 600; padding: 7px 14px; border-radius: 8px; cursor: pointer;">📥 Download Corrected JSON</button>
                </div>
            `;
        }

        // Box Renderers
        const renderDateBox = () => {
            if (renderedBoxCount > 0 || handledTypes.has('date') || isDateJustPatched) return;
            const dateAct = findAction(a => /change date to|set date:|today|yesterday/i.test(a));
            const hasDatePrompt = Boolean(activeTopic === 'date' || dateAct || tailPrompt.includes('document date') || tailPrompt.includes('date to within') || tailPrompt.includes('change the document date'));
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
                    <div class="copilot-inline-suggestion-bar copilot-date-bar" style="margin-top: 8px; margin-bottom: 6px; padding: 12px 14px; background: rgba(15, 23, 42, 0.95); border: 1px solid rgba(56, 189, 248, 0.45); border-radius: 8px; display: flex; flex-direction: column; gap: 8px;">
                        <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap;">
                            <span style="font-size: 0.82rem; font-weight: 700; color: #38bdf8;">📅 Document Date (NIC Statutory Rule 2164):</span>
                            <span style="font-size: 0.72rem; color: #38bdf8; font-family: 'JetBrains Mono', monospace; background: rgba(56, 189, 248, 0.1); padding: 2px 8px; border-radius: 4px; border: 1px solid rgba(56, 189, 248, 0.3);">Max 2-Day Past Window</span>
                        </div>
                        <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                            <input type="date" class="copilot-inline-custom-input copilot-inline-date-input" value="${defDate}" onkeydown="if(event.key==='Enter'){event.preventDefault();submitCopilotInlineInput(this, 'Change date to ');}" style="background: #090e1a; color: #f8fafc; border: 1px solid #38bdf8; border-radius: 6px; padding: 5px 9px; font-size: 0.84rem; outline: none; font-family: 'JetBrains Mono', monospace;">
                            <button type="button" class="copilot-action-btn" onclick="submitCopilotInlineInput(this, 'Change date to ')" style="background: linear-gradient(135deg, #0ea5e9, #6366f1); color: #fff; border: none; font-weight: 700; padding: 6px 14px; border-radius: 6px; cursor: pointer;">📅 Apply Date</button>
                            <button type="button" class="copilot-action-btn" onclick="sendCopilotQuickMessage('Change date to Today (${todayIso})')" style="background: rgba(16, 185, 129, 0.2); border: 1px solid #10b981; color: #34d399; font-weight: 600; padding: 6px 12px; border-radius: 6px; cursor: pointer;">⚡ Set Today</button>
                        </div>
                    </div>
                `;
            }
        };

        const renderSupGstinBox = () => {
            if (renderedBoxCount > 0 || handledTypes.has('sup_gstin') || isSupGstJustPatched) return;
            const supGstinAct = findAction(a => /my gstin is|supplier gstin/i.test(a));
            const hasSupGstinPrompt = Boolean(
                activeTopic === 'sup_gstin' ||
                supGstinAct ||
                tailPrompt.includes('supplier gstin') ||
                tailPrompt.includes('my gstin is') ||
                tailPrompt.includes('15-digit supplier gstin')
            );
            if (hasSupGstinPrompt) {
                handledTypes.add('sup_gstin');
                renderedBoxCount++;
                let defGst = '27ABCDE1234F1ZO';
                if (supGstinAct) {
                    const m = supGstinAct.match(/\b([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z0-9]{1,3})\b/i);
                    if (m) defGst = m[1].toUpperCase();
                } else {
                    const mRep = replyLower.match(/government calculated correction:\s*`?([0-9]{2}[a-z]{5}[0-9]{4}[a-z0-9]{1,3})`?/i);
                    if (mRep) {
                        defGst = mRep[1].toUpperCase();
                    } else if (targetInv.supplier_gstin || targetInv.self_gstin) {
                        const rawG = (targetInv.supplier_gstin || targetInv.self_gstin).trim();
                        defGst = rawG.length === 14 ? rawG + 'W' : (rawG.length >= 15 ? rawG : '27ABCDE1234F1ZO');
                    }
                }
                barsHtml += `
                    <div class="copilot-inline-suggestion-bar copilot-gstin-bar" style="margin-top: 8px; margin-bottom: 6px; padding: 12px 14px; background: rgba(15, 23, 42, 0.95); border: 1px solid rgba(56, 189, 248, 0.45); border-radius: 8px; display: flex; flex-direction: column; gap: 8px;">
                        <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap;">
                            <span style="font-size: 0.82rem; font-weight: 700; color: #38bdf8;">🏢 Supplier GSTIN (15-digit Checksum Verified):</span>
                            <span style="font-size: 0.72rem; color: #34d399; font-family: 'JetBrains Mono', monospace; background: rgba(52, 211, 153, 0.1); padding: 2px 8px; border-radius: 4px; border: 1px solid rgba(52, 211, 153, 0.3);">NIC Portal Compliant</span>
                        </div>
                        <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                            <div style="display: flex; flex-direction: column; gap: 2px;">
                                <label style="font-size: 0.70rem; color: #94a3b8; font-weight: 600;">15-DIGIT GSTIN</label>
                                <input type="text" class="copilot-inline-custom-input copilot-inline-gstin-input" placeholder="e.g. 27ABCDE1234F1ZO" value="${escapeHtml(defGst)}" maxlength="15" onkeydown="if(event.key==='Enter'){event.preventDefault();submitCopilotInlineInput(this, 'My GSTIN is ');}" style="background: #090e1a; color: #f8fafc; border: 1px solid #38bdf8; border-radius: 6px; padding: 6px 12px; font-size: 0.86rem; outline: none; font-family: 'JetBrains Mono', monospace; text-transform: uppercase; width: 195px; font-weight: 700; letter-spacing: 0.5px;">
                            </div>
                            <div style="display: flex; align-items: flex-end; padding-top: 14px; gap: 6px; flex-wrap: wrap;">
                                <button type="button" class="copilot-action-btn" onclick="submitCopilotInlineInput(this, 'My GSTIN is ')" style="background: linear-gradient(135deg, #0ea5e9, #6366f1); color: #fff; border: none; font-weight: 700; padding: 6px 14px; border-radius: 6px; cursor: pointer; white-space: nowrap;">🏢 Apply GSTIN</button>
                                <button type="button" class="copilot-action-btn" onclick="sendCopilotQuickMessage('Verify current GSTIN')" style="background: rgba(16, 185, 129, 0.2); border: 1px solid #10b981; color: #34d399; font-weight: 600; padding: 6px 12px; border-radius: 6px; cursor: pointer; white-space: nowrap;">🔍 Verify GSTIN</button>
                            </div>
                        </div>
                    </div>
                `;
            }
        };

        const renderBuyerGstinBox = () => {
            if (renderedBoxCount > 0 || handledTypes.has('buyer_gstin') || isBuyerGstJustPatched) return;
            const buyerGstinAct = findAction(a => /buyer gstin is|buyer is urp|set buyer gstin/i.test(a));
            const hasBuyerGstinPrompt = Boolean(
                activeTopic === 'buyer_gstin' ||
                buyerGstinAct ||
                tailPrompt.includes('buyer gstin') ||
                tailPrompt.includes('recipient gstin') ||
                tailPrompt.includes('15-digit buyer gstin')
            );
            if (hasBuyerGstinPrompt) {
                handledTypes.add('buyer_gstin');
                renderedBoxCount++;
                let defBuyerGst = '29XYZAB5678C1Z2';
                if (buyerGstinAct) {
                    const m = buyerGstinAct.match(/\b([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z0-9]{1,3})\b/i);
                    if (m) defBuyerGst = m[1].toUpperCase();
                    else if (buyerGstinAct.includes('URP')) defBuyerGst = 'URP';
                }
                barsHtml += `
                    <div class="copilot-inline-suggestion-bar copilot-buyer-gstin-bar" style="margin-top: 8px; margin-bottom: 6px; padding: 12px 14px; background: rgba(15, 23, 42, 0.95); border: 1px solid rgba(56, 189, 248, 0.45); border-radius: 8px; display: flex; flex-direction: column; gap: 8px;">
                        <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap;">
                            <span style="font-size: 0.82rem; font-weight: 700; color: #38bdf8;">👤 Buyer / Recipient GSTIN:</span>
                            <span style="font-size: 0.72rem; color: #34d399; font-family: 'JetBrains Mono', monospace; background: rgba(52, 211, 153, 0.1); padding: 2px 8px; border-radius: 4px; border: 1px solid rgba(52, 211, 153, 0.3);">B2B Mandatory</span>
                        </div>
                        <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                            <div style="display: flex; flex-direction: column; gap: 2px;">
                                <label style="font-size: 0.70rem; color: #94a3b8; font-weight: 600;">BUYER GSTIN OR URP</label>
                                <input type="text" class="copilot-inline-custom-input copilot-inline-buyer-gstin-input" placeholder="e.g. 29XYZAB5678C1Z2 or URP" value="${escapeHtml(defBuyerGst)}" maxlength="15" onkeydown="if(event.key==='Enter'){event.preventDefault();submitCopilotInlineInput(this, 'Buyer GSTIN is ');}" style="background: #090e1a; color: #f8fafc; border: 1px solid #38bdf8; border-radius: 6px; padding: 6px 12px; font-size: 0.86rem; outline: none; font-family: 'JetBrains Mono', monospace; text-transform: uppercase; width: 195px; font-weight: 700; letter-spacing: 0.5px;">
                            </div>
                            <div style="display: flex; align-items: flex-end; padding-top: 14px; gap: 6px; flex-wrap: wrap;">
                                <button type="button" class="copilot-action-btn" onclick="submitCopilotInlineInput(this, 'Buyer GSTIN is ')" style="background: linear-gradient(135deg, #0ea5e9, #6366f1); color: #fff; border: none; font-weight: 700; padding: 6px 14px; border-radius: 6px; cursor: pointer; white-space: nowrap;">👤 Apply Buyer GSTIN</button>
                                <button type="button" class="copilot-action-btn" onclick="sendCopilotQuickMessage('Buyer is URP (Unregistered)')" style="background: rgba(16, 185, 129, 0.2); border: 1px solid #10b981; color: #34d399; font-weight: 600; padding: 6px 12px; border-radius: 6px; cursor: pointer; white-space: nowrap;">⚡ URP</button>
                            </div>
                        </div>
                    </div>
                `;
            }
        };

        const renderModeBox = () => {
            if (renderedBoxCount > 0 || handledTypes.has('mode')) return;
            const modeAct = findAction(a => /set mode:/i.test(a));
            const hasModePrompt = Boolean(activeTopic === 'mode' || modeAct || tailPrompt.includes('delivery mode applies') || tailPrompt.includes('transaction mode'));
            if (hasModePrompt) {
                handledTypes.add('mode');
                renderedBoxCount++;
                let defMode = 'REG';
                if (modeAct) {
                    const m = modeAct.match(/\b(REG|DIS|SHP|CMB)\b/i);
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
            const hasHsnPrompt = Boolean(activeTopic === 'hsn' || hsnAct || tailPrompt.includes('quick question on product hsn') || tailPrompt.includes('wrong / incomplete hsn code') || tailPrompt.includes('wrong hsn code detected'));
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
            if (renderedBoxCount > 0 || handledTypes.has('pin') || isPinJustPatched || isStateJustPatched) return;
            const pinAct = findAction(a => /set (?:supplier|buyer)?\s*pin:/i.test(a));
            const stAct = findAction(a => /set (?:supplier|buyer)?\s*state:/i.test(a));
            const hasPinStatePrompt = Boolean(activeTopic === 'pin_state' || pinAct || stAct || (tailPrompt.includes('pincode') && tailPrompt.includes('conflict')) || (tailPrompt.includes('state') && tailPrompt.includes('pin') && !tailPrompt.includes('aligned!') && !tailPrompt.includes('updated!')) || tailPrompt.includes('postal pin & state'));
            if (hasPinStatePrompt) {
                handledTypes.add('pin');
                handledTypes.add('state');
                renderedBoxCount++;
                let role = 'Buyer';
                if ((pinAct && /supplier/i.test(pinAct)) || (stAct && /supplier/i.test(stAct)) || tailPrompt.includes('supplier pin') || tailPrompt.includes('supplier state')) {
                    role = 'Supplier';
                }
                const isBuyer = (role === 'Buyer');
                const entityDt = isBuyer ? (targetInv.buyerdt1 || {}) : (targetInv.supplierdt1 || {});
                let defPin = entityDt.buyer_pin || entityDt.supplier_pin || targetInv.buyer_pin || targetInv.supplier_pin || (isBuyer ? '400001' : '560001');
                let defSt = entityDt.buyer_state || entityDt.supplier_state || targetInv.buyer_state || targetInv.supplier_state || (isBuyer ? '27' : '29');

                if (pinAct) {
                    const mPin = pinAct.match(/\b([0-9]{6})\b/);
                    if (mPin) defPin = mPin[1];
                    const mStInPin = pinAct.match(/State:\s*([0-9]{1,2})/i);
                    if (mStInPin) defSt = mStInPin[1].padStart(2, '0');
                }
                if (stAct) {
                    const mSt = stAct.match(/\b([0-9]{1,2})\b/);
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
            const hasSubPrompt = Boolean(activeTopic === 'subsupply' || subAct || tailPrompt.includes('sub-supply') || tailPrompt.includes('subsupply'));
            if (hasSubPrompt) {
                handledTypes.add('subsupply');
                renderedBoxCount++;
                let defSub = (targetInv.ewbdt1 && targetInv.ewbdt1.subsupplytype) || targetInv.subsupplytype || '1';
                if (subAct) {
                    const m = subAct.match(/\b([1-8])\b/);
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
            const vehAct = findAction(a => /vehicle is|verify vehicle|ka01|mh12/i.test(a));
            // If vehicle is already formatted correctly in payload, do NOT display vehicle box unless explicitly prompted
            if (isVehFormatValid && activeTopic !== 'vehicle' && !vehAct) return;

            const hasVehPrompt = Boolean(
                activeTopic === 'vehicle' ||
                vehAct ||
                tailPrompt.includes('what is your vehicle registration') ||
                tailPrompt.includes('vehicle registration number') ||
                tailPrompt.includes('vehicle plate') ||
                tailPrompt.includes('vehicle format error')
            );
            if (hasVehPrompt) {
                handledTypes.add('vehicle');
                renderedBoxCount++;
                let defVeh = cleanVeh || 'KA01AB1234';
                if (vehAct) {
                    const m = vehAct.match(/([A-Z]{2}[0-9]{1,2}[A-Z0-9]{1,4}[0-9]{4})/i);
                    if (m) defVeh = m[1].toUpperCase();
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
            const hasTransPrompt = Boolean(activeTopic === 'transporter' || transAct || tailPrompt.includes('transporter gstin / id') || tailPrompt.includes('transporter id'));
            if (hasTransPrompt) {
                handledTypes.add('transporter');
                renderedBoxCount++;
                let defTrans = '29ABCDE1234F1Z5';
                if (transAct) {
                    const m = transAct.match(/\b([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z0-9]{1,3})\b/i);
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
            const hasTaxMathPrompt = Boolean(activeTopic === 'tax_math' || taxMathAct || tailPrompt.includes('tax valuation recalculation') || tailPrompt.includes('tax math imbalance'));
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
        if (activeTopic === 'sup_gstin') renderSupGstinBox();
        else if (activeTopic === 'buyer_gstin') renderBuyerGstinBox();
        else if (activeTopic === 'date') renderDateBox();
        else if (activeTopic === 'hsn') renderHsnBox();
        else if (activeTopic === 'pin_state') renderPinStateBox();
        else if (activeTopic === 'vehicle') renderVehicleBox();
        else if (activeTopic === 'mode') renderModeBox();
        else if (activeTopic === 'subsupply') renderSubsupplyBox();
        else if (activeTopic === 'transporter') renderTransporterBox();
        else if (activeTopic === 'tax_math') renderTaxMathBox();

        // 2. Fallback step-by-step sequence of unresolved issues (strictly one-by-one, aligned with get_friendly_next_step priority)
        if (renderedBoxCount === 0) renderDateBox();
        if (renderedBoxCount === 0) renderSupGstinBox();
        if (renderedBoxCount === 0) renderBuyerGstinBox();
        if (renderedBoxCount === 0) renderModeBox();
        if (renderedBoxCount === 0) renderHsnBox();
        if (renderedBoxCount === 0) renderVehicleBox();
        if (renderedBoxCount === 0) renderPinStateBox();
        if (renderedBoxCount === 0) renderSubsupplyBox();
        if (renderedBoxCount === 0) renderTransporterBox();
        if (renderedBoxCount === 0) renderTaxMathBox();

        // 3. Fallback for any other "Set Key: Value" or "Key is Value" suggestion (strictly one-by-one)
        for (const act of actions) {
            const actL = act.toLowerCase();
            if (
                (handledTypes.has('date') && (actL.includes('apply date') || actL.includes('set today') || actL.includes('change date to today') || actL.includes('change date to yesterday'))) ||
                (handledTypes.has('vehicle') && (actL.includes('vehicle') || actL.includes('vahan') || actL.includes('ka01') || actL.includes('plate') || actL.includes('disable e-way'))) ||
                (handledTypes.has('sup_gstin') && (actL.includes('my gstin is') || actL.includes('supplier gstin') || actL.includes('verify current gstin'))) ||
                (handledTypes.has('buyer_gstin') && (actL.includes('buyer gstin is') || actL.includes('buyer is urp'))) ||
                (handledTypes.has('hsn') && (actL.includes('set hsn:') || actL.includes('fix hsn') || actL.includes('apply & recalculate') || actL.includes('ml lookup'))) ||
                (handledTypes.has('pin') && (actL.includes('set supplier pin') || actL.includes('set buyer pin') || actL.includes('pin:') || (handledTypes.has('state') && actL.includes('my gstin is')))) ||
                (handledTypes.has('state') && (actL.includes('set supplier state') || actL.includes('set buyer state') || actL.includes('state:'))) ||
                (handledTypes.has('subsupply') && actL.includes('subsupply')) ||
                (handledTypes.has('mode') && actL.includes('set mode:')) ||
                (handledTypes.has('transporter') && actL.includes('set transporter:')) ||
                (handledTypes.has('tax_math') && actL.includes('rebalance tax math'))
            ) {
                continue;
            }

            // Check for ANY other "Set Key: Value" or "Key is Value" suggestion
            const kvMatch = act.match(/^(?:Set\s+)?([A-Za-z0-9_\s]+?)(?:\s*[:=]|\s+is)\s*(.+)$/i);
            if (kvMatch && !act.includes('Auto-Fix') && !act.includes('IRN') && !act.includes('Download') && !act.includes('Disable')) {
                const keyName = kvMatch[1].trim();
                const valVal = kvMatch[2].trim();
                const keySlug = keyName.toLowerCase().replace(/\s+/g, '_');
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

        if (hasActiveIrn) {
            for (let i = standaloneButtons.length - 1; i >= 0; i--) {
                if (standaloneButtons[i].includes('Generate IRN')) {
                    standaloneButtons.splice(i, 1);
                }
            }
        }

        if (isCompliant) {
            if (!hasActiveIrn && !standaloneButtons.some(b => b.includes('Generate IRN'))) {
                standaloneButtons.unshift('🚀 Generate IRN');
            }
            if (!standaloneButtons.some(b => b.includes('Download Corrected JSON'))) {
                standaloneButtons.push('📥 Download Corrected JSON');
            }
        }

        if (standaloneButtons.length > 0) {
            barsHtml += '<div class="msg-action-bar" style="margin-top: 10px; display: flex; gap: 8px; flex-wrap: wrap;">';
            for (const act of standaloneButtons) {
                let btnStyle = "background: rgba(56, 189, 248, 0.15); border: 1px solid #38bdf8; color: #38bdf8; font-weight: 600; padding: 6px 14px; border-radius: 6px; cursor: pointer; transition: all 0.2s;";
                if (act.includes('Auto-Fix All')) {
                    btnStyle = "background: linear-gradient(135deg, #ec4899, #8b5cf6); color: #fff; font-weight: 700; border: none; padding: 6px 14px; border-radius: 6px; cursor: pointer; box-shadow: 0 2px 10px rgba(236, 72, 153, 0.35);";
                } else if (act.includes('Generate IRN')) {
                    btnStyle = "background: linear-gradient(135deg, #10b981, #059669); color: #fff; font-weight: 700; border: none; padding: 6px 14px; border-radius: 6px; cursor: pointer; box-shadow: 0 2px 10px rgba(16, 185, 129, 0.35);";
                } else if (act.includes('Disable E-Way')) {
                    btnStyle = "background: rgba(239, 68, 68, 0.15); border: 1px solid #ef4444; color: #f87171; font-weight: 600; padding: 6px 12px; border-radius: 6px; cursor: pointer;";
                }
                barsHtml += `<button type="button" class="copilot-action-btn" onclick="sendCopilotQuickMessage('${escapeHtml(act)}')" style="${btnStyle}">${escapeHtml(act)}</button>`;
            }
            barsHtml += '</div>';
        }

        return barsHtml;
    };
}

// Tests
const mockSubsupply = () => '<option value="1">1 - Supply</option>';
const mockState = () => '<option value="27">27 - Maharashtra</option>';
const mockEscape = (s) => String(s).replace(/"/g, '&quot;');
const render = createRenderer(mockSubsupply, mockState, mockEscape);

console.log("=== TEST 1: User just updated Date, now GSTIN is requested ===");
const res1 = render({
    patch_applied: true,
    patch_summary: ["Updated document date to 2026-10-20 (NIC Rule 2164 Compliant)"],
    reply: "Updated document date to 2026-10-20 (NIC Rule 2164 Compliant)\n🔄 Live Re-Audit Status: 4 unresolved errors remaining.\n1. Error 4011 (ewbdt1.veh_number): Vehicle plate has invalid spacing\n---\n👉 **Please tell me your proper 15-digit Supplier GSTIN number:**\n• Currently in payload: '27ABCDE1234F1ZO'\n💡 Suggested format: 27ABCDE1234F1ZO",
    interactive_actions: ["My GSTIN is 27ABCDE1234F1ZO", "Verify current GSTIN", "⚡ Auto-Fix All Compliance Errors"]
}, false, {
    veh_number: "KA01AB1234",
    ewbdt1: { veh_number: "KA01AB1234" }
});

console.log("Test 1 includes Supplier GSTIN box:", res1.includes("copilot-gstin-bar"));
console.log("Test 1 includes GSTIN input:", res1.includes('value="27ABCDE1234F1ZO"'));
console.log("Test 1 includes Apply GSTIN button:", res1.includes('🏢 Apply GSTIN'));
console.log("Test 1 does NOT include Vehicle box:", !res1.includes("copilot-vehicle-picker-bar"));
console.log("Test 1 does NOT have standalone 'My GSTIN' button:", !res1.includes('>My GSTIN is 27ABCDE1234F1ZO</button>'));

console.log("\n=== TEST 2: User updated Vehicle, should NOT re-trigger Vehicle ===");
const res2 = render({
    patch_applied: true,
    patch_summary: ["Verified & updated vehicle KA01AB1234 on live Vahan registry"],
    reply: "🚚 MoRTH Vahan Registry — LIVE VERIFIED:\n• Registration Plate: KA01AB1234\n✅ Set veh_number to KA01AB1234.\n🔄 Live Re-Audit Status: 3 unresolved errors remaining.\n---\n👉 **Please tell me your proper 15-digit Supplier GSTIN number:**",
    interactive_actions: ["My GSTIN is 27ABCDE1234F1ZO", "Verify current GSTIN"]
}, false, {
    veh_number: "KA01AB1234",
    ewbdt1: { veh_number: "KA01AB1234" }
});

console.log("Test 2 includes Supplier GSTIN box:", res2.includes("copilot-gstin-bar"));
console.log("Test 2 does NOT include Vehicle box:", !res2.includes("copilot-vehicle-picker-bar"));

console.log("\n=== TEST 3: Vehicle is already valid, next step is HSN ===");
const res3 = render({
    reply: "👉 **Quick Question on Product HSN:**\nWrong HSN code detected.",
    interactive_actions: ["Set HSN: 85011013", "Fix HSN from product description"]
}, false, {
    veh_number: "KA01AB1234",
    ewbdt1: { veh_number: "KA01AB1234" }
});
console.log("Test 3 includes HSN box:", res3.includes("copilot-hsn-pricing-bar"));
console.log("Test 3 does NOT include Vehicle box:", !res3.includes("copilot-vehicle-picker-bar"));

console.log("\n=== TEST 4: Vehicle IS genuinely invalid and asked for ===");
const res4 = render({
    reply: "👉 **Vehicle Registration Number Format Error:**\nPlease update your vehicle registration number:",
    interactive_actions: ["Vehicle is KA01AB1234", "Verify vehicle number", "Disable E-Way Bill"]
}, false, {
    veh_number: "BADVEH",
    ewbdt1: { veh_number: "BADVEH" }
});
console.log("Test 4 includes Vehicle box:", res4.includes("copilot-vehicle-picker-bar"));
console.log("\n=== TEST 5: PIN / State Mismatch Conflict ===");
const res5 = render({
    reply: "👉 **Government Portal Taxpayer Check on [supplierdt1.supplier_pin]:**\n\n🏢 **Taxpayer Entity Name:** **`Acme Industries`**\n• **Supplier GSTIN:** `28ABCDE1234F1ZY`\n• **Government Registered State:** **Andhra Pradesh (Old) (Code 28)**\n• **Pincode on Invoice:** `400001` (Maharashtra)\n\n⚠️ **Conflict:** According to Government GST rules, Pincode `400001` is in **Maharashtra**, which does not match the registered State of `28ABCDE1234F1ZY` (**Andhra Pradesh (Old)**).\n\nHow would you like to align this?",
    interactive_actions: ["Set Supplier PIN: 510001, State: 28", "Set Supplier PIN: 510001", "Set Supplier State: 27", "My GSTIN is 27ABCDE1234F1ZY", "⚡ Auto-Fix All Compliance Errors"]
}, false, {
    supplierdt1: { supplier_pin: "400001", supplier_state: "28", supplier_gstin: "28ABCDE1234F1ZY" }
});
console.log("Test 5 includes PIN & State box:", res5.includes("copilot-pin-state-bar"));
console.log("Test 5 does NOT include GSTIN box:", !res5.includes("copilot-gstin-bar"));
console.log("Test 5 does NOT have standalone 'Set Supplier PIN' button:", !res5.includes('>Set Supplier PIN: 510001, State: 28</button>'));

console.log("\n=== TEST 6: Once PIN is updated, invoice is 100% compliant ===");
const res6 = render({
    patch_applied: true,
    patch_summary: ["Updated buyer_pin to 560001 and aligned State to 29 (Karnataka)"],
    reply: "✅ **Buyer PIN Code & State Aligned!**\n\n• PIN Code: **`560001`**\n• State: **`29 (Karnataka)`**\n\n🔄 **Live Re-Audit Status:** 0 unresolved errors remaining.\n🎉 **All NIC compliance errors have been resolved!** This invoice is now 100% compliant.\n\n🚀 **Next Step: Ready for IRN Generation!**\nYou can now generate the official NIC IRN or download the corrected JSON.",
    interactive_actions: ["🚀 Generate IRN", "📥 Download Corrected JSON"]
}, true, {
    buyer_pin: "560001",
    buyer_state: "29"
});
console.log("Test 6 does NOT include PIN & State box:", !res6.includes("copilot-pin-state-bar"));
console.log("Test 6 includes Generate IRN button:", res6.includes("🚀 Generate IRN"));
console.log("Test 6 includes Download button:", res6.includes("📥 Download Corrected JSON"));

console.log("\n=== TEST 7: Once IRN is generated, Generate IRN should NOT be visible, only Download JSON ===");
const res7 = render({
    patch_applied: true,
    patch_summary: ["Generated official NIC IRN: 8a4f91e3..."],
    reply: "🔄 **Live Re-Audit Status:** 0 unresolved errors remaining.\n🎉 **Invoice is 100% compliant with active IRN!** Ready for download or ERP dispatch.",
    interactive_actions: ["📥 Download Corrected JSON"]
}, true, {
    irn: "8a4f91e3b2c5...",
    irn_status: "GENERATED",
    status: "IRN_GENERATED"
});
console.log("Test 7 does NOT include Generate IRN button:", !res7.includes("🚀 Generate IRN"));
console.log("Test 7 includes Download button:", res7.includes("📥 Download Corrected JSON"));
console.log("Test 7 does NOT include any input box:", !res7.includes("copilot-inline"));

if (
    res1.includes("copilot-gstin-bar") &&
    !res1.includes("copilot-vehicle-picker-bar") &&
    res2.includes("copilot-gstin-bar") &&
    !res2.includes("copilot-vehicle-picker-bar") &&
    res3.includes("copilot-hsn-pricing-bar") &&
    res4.includes("copilot-vehicle-picker-bar") &&
    res5.includes("copilot-pin-state-bar") &&
    !res6.includes("copilot-pin-state-bar") &&
    res6.includes("🚀 Generate IRN") &&
    !res7.includes("🚀 Generate IRN") &&
    res7.includes("📥 Download Corrected JSON")
) {
    console.log("\n>>> ALL 7 TESTS PASSED SUCCESSFULLY! <<<");
} else {
    console.error("\n>>> TESTS FAILED! <<<");
    process.exit(1);
}
