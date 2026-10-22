function renderCopilotSuggestionsHtml(data, isCompliant, payload) {
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
        const isDocnoJustPatched = Boolean(data.patch_applied && patchSummary.some(s => s.includes('invoice number') || s.includes('docno')));

        if (isDateJustPatched) handledTypes.add('date');
        if (isVehJustPatched) handledTypes.add('vehicle');
        if (isHsnJustPatched) handledTypes.add('hsn');
        if (isSupGstJustPatched) handledTypes.add('sup_gstin');
        if (isBuyerGstJustPatched) handledTypes.add('buyer_gstin');
        if (isPinJustPatched) handledTypes.add('pin');
        if (isStateJustPatched) handledTypes.add('state');
        if (isDocnoJustPatched) handledTypes.add('docno');

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

        if (hasActiveIrn) {
            activeIrnGenerated = true;
            if (typeof unlockStage2 === 'function') unlockStage2(data.metrics, true);
        }

        // Check if doc date in payload is ALREADY valid (within 2 days of today or compliant)
        const rawDocDt = (targetInv.docdt1 && (targetInv.docdt1.docdt || targetInv.docdt1.doc_date)) || targetInv.docdt || targetInv.doc_date || '';
        let isDateValid = false;
        if (rawDocDt) {
            try {
                let pDate = null;
                if (/^\d{2}[\/\-.]\d{2}[\/\-.]\d{4}$/.test(rawDocDt)) {
                    const parts = rawDocDt.split(/[\/\-.]/);
                    pDate = new Date(`${parts[2]}-${parts[1]}-${parts[0]}`);
                } else if (/^\d{4}[\/\-.]\d{2}[\/\-.]\d{2}$/.test(rawDocDt)) {
                    pDate = new Date(rawDocDt);
                }
                if (pDate && !isNaN(pDate.getTime())) {
                    const now = new Date();
                    const diffDays = Math.abs((now - pDate) / (1000 * 60 * 60 * 24));
                    if (diffDays <= 2.1) {
                        isDateValid = true;
                    }
                }
            } catch (e) {}
        }
        if (isDateJustPatched) {
            handledTypes.add('date');
        }
        // Check if invoice number (docno) in payload is ALREADY valid per NIC Rule 2144
        const rawDocNo = (targetInv.docdt1 && (targetInv.docdt1.docno || targetInv.docdt1.document_number)) || targetInv.docno || targetInv.document_number || '';
        const cleanDocNo = String(rawDocNo).trim();
        const isDocNoValid = cleanDocNo.length > 0 && cleanDocNo.length <= 16 && /^[A-Za-z1-9][A-Za-z0-9/-]*$/.test(cleanDocNo);
        if (isDocnoJustPatched) {
            handledTypes.add('docno');
        }

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
        if (actions.some(a => /set (?:supplier|buyer)?\s*(?:pin|state):|pin\s*:\s*\d+/i.test(a))) {
            activeTopic = 'pin_state';
        } else if (!isSupGstJustPatched && actions.some(a => /^(?:my gstin is|set supplier gstin:)/i.test(a.trim()))) {
            activeTopic = 'sup_gstin';
        } else if (!isBuyerGstJustPatched && actions.some(a => /buyer gstin is|buyer is urp|set buyer gstin/i.test(a))) {
            activeTopic = 'buyer_gstin';
        } else if (!isDocnoJustPatched && actions.some(a => /set invoice no|invoice number|docno/i.test(a))) {
            activeTopic = 'docno';
        } else if (!isDateJustPatched && actions.some(a => /change date to|set date:|today|yesterday/i.test(a))) {
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
            if (tailPrompt.includes('postal pin') || tailPrompt.includes('pincode conflict') || tailPrompt.includes('pincode mismatch') || tailPrompt.includes('taxpayer check on') || tailPrompt.includes('pincode on invoice') || (tailPrompt.includes('pincode') && tailPrompt.includes('conflict'))) {
                activeTopic = 'pin_state';
            } else if (!isSupGstJustPatched && (tailPrompt.includes('15-digit supplier gstin') || tailPrompt.includes('supplier gstin number') || tailPrompt.includes('proper 15-digit supplier gstin'))) {
                activeTopic = 'sup_gstin';
            } else if (!isBuyerGstJustPatched && (tailPrompt.includes('buyer gstin') || tailPrompt.includes('recipient gstin') || tailPrompt.includes('15-digit buyer gstin'))) {
                activeTopic = 'buyer_gstin';
            } else if (!isDocnoJustPatched && (tailPrompt.includes('invoice number') || tailPrompt.includes('valid invoice number') || tailPrompt.includes('docno') || tailPrompt.includes('document number'))) {
                activeTopic = 'docno';
            } else if (!isDateJustPatched && (tailPrompt.includes('document date') || tailPrompt.includes('change the document date') || tailPrompt.includes('invoice date') || tailPrompt.includes('date to within') || tailPrompt.includes('docdt'))) {
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
            actions.some(a => /vehicle|veh|ka01|hsn|pin|state|date|mode|subsupply|gstin|tax\s*math|transporter|docno|invoice/i.test(a))
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
        const renderDocnoBox = () => {
            if (isDocnoJustPatched || renderedBoxCount > 0 || handledTypes.has('docno')) return;
            const docnoAct = findAction(a => /set invoice no|invoice number|docno/i.test(a));
            const hasDocnoPrompt = Boolean(activeTopic === 'docno' || docnoAct || tailPrompt.includes('invoice number') || tailPrompt.includes('valid invoice number') || tailPrompt.includes('docno') || tailPrompt.includes('document number'));
            if (hasDocnoPrompt) {
                handledTypes.add('docno');
                renderedBoxCount++;
                let defDocno = 'INV-2026-001';
                if (docnoAct) {
                    const m = docnoAct.match(/(?:Set Invoice No:\s*|invoice number\s*[:=]?\s*)([A-Za-z0-9/-]+)/i);
                    if (m) defDocno = m[1];
                } else if (cleanDocNo) {
                    defDocno = cleanDocNo.replace(/^[^A-Za-z1-9]+/, '').replace(/[^0-9A-Za-z/-]/g, '').slice(0, 16) || 'INV-2026-001';
                }
                barsHtml += `
                    <div class="copilot-inline-suggestion-bar copilot-docno-bar" style="margin-top: 8px; margin-bottom: 6px; padding: 12px 14px; background: rgba(15, 23, 42, 0.95); border: 1px solid rgba(56, 189, 248, 0.45); border-radius: 8px; display: flex; flex-direction: column; gap: 8px;">
                        <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap;">
                            <span style="font-size: 0.82rem; font-weight: 700; color: #38bdf8;">📄 Invoice Number (NIC Statutory Rule 2144):</span>
                            <span style="font-size: 0.72rem; color: #38bdf8; font-family: 'JetBrains Mono', monospace; background: rgba(56, 189, 248, 0.1); padding: 2px 8px; border-radius: 4px; border: 1px solid rgba(56, 189, 248, 0.3);">Max 16 Chars (No Leading 0/-/)</span>
                        </div>
                        <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                            <input type="text" class="copilot-inline-custom-input copilot-inline-docno-input" placeholder="e.g. INV-2026-001" value="${escapeHtml(defDocno)}" maxlength="16" oninput="this.value = this.value.toUpperCase().replace(/[^0-9A-Z/-]/g, '')" onkeydown="if(event.key==='Enter'){event.preventDefault();submitCopilotInlineInput(this, 'Set Invoice No: ');}" style="background: #090e1a; color: #f8fafc; border: 1px solid #38bdf8; border-radius: 6px; padding: 5px 9px; font-size: 0.84rem; outline: none; font-family: 'JetBrains Mono', monospace; text-transform: uppercase; width: 160px; font-weight: 700;">
                            <button type="button" class="copilot-action-btn" onclick="submitCopilotInlineInput(this, 'Set Invoice No: ')" style="background: linear-gradient(135deg, #0ea5e9, #6366f1); color: #fff; border: none; font-weight: 700; padding: 6px 14px; border-radius: 6px; cursor: pointer;">✨ Apply Invoice No</button>
                            <button type="button" class="copilot-action-btn" onclick="sendCopilotQuickMessage('Set Invoice No: ${escapeHtml(defDocno)}')" style="background: rgba(16, 185, 129, 0.2); border: 1px solid #10b981; color: #34d399; font-weight: 600; padding: 6px 12px; border-radius: 6px; cursor: pointer;">⚡ Use ${escapeHtml(defDocno)}</button>
                        </div>
                    </div>
                `;
            }
        };

        const renderDateBox = () => {
            if (isDateJustPatched || renderedBoxCount > 0 || handledTypes.has('date')) return;
            const dateAct = findAction(a => /change date to|set date:|today|yesterday/i.test(a));
            const hasDatePrompt = Boolean(activeTopic === 'date' || dateAct || tailPrompt.includes('document date') || tailPrompt.includes('date to within') || tailPrompt.includes('change the document date') || tailPrompt.includes('docdt') || tailPrompt.includes('set date:'));
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
            if (activeTopic && activeTopic !== 'sup_gstin') return;

            const supGstinAct = findAction(a => /^(?:my gstin is|set supplier gstin:)/i.test(a.trim()));
            const hasSupGstinPrompt = Boolean(
                activeTopic === 'sup_gstin' ||
                supGstinAct ||
                tailPrompt.includes('15-digit supplier gstin') ||
                tailPrompt.includes('proper 15-digit supplier gstin')
            );

            // Guard: If supplier GSTIN in payload is ALREADY valid 15-digits, never render unless explicitly in sup_gstin topic
            const rawSupG = String((targetInv.supplierdt1 && targetInv.supplierdt1.supplier_gstin) || targetInv.supplier_gstin || targetInv.self_gstin || '').trim();
            const isSupGstAlreadyValid = rawSupG.length === 15 && /^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$/i.test(rawSupG);
            if (isSupGstAlreadyValid && activeTopic !== 'sup_gstin') return;

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
                let firstItm = null;
                if (targetInv.itemdtls && targetInv.itemdtls.length > 0) {
                    firstItm = targetInv.itemdtls[0];
                } else if (targetInv.items && targetInv.items.length > 0) {
                    firstItm = targetInv.items[0];
                }
                let defHsn = (firstItm && (firstItm.hsncd || firstItm.hsn || firstItm.hsn_code)) ? String(firstItm.hsncd || firstItm.hsn || firstItm.hsn_code).trim() : '85011013';
                if (hsnAct) {
                    const m = hsnAct.match(/\b([0-9]{4,8})\b/);
                    if (m) defHsn = m[1];
                }
                const prdName = (firstItm && (firstItm.prdnm || firstItm.prddesc)) ? (firstItm.prdnm || firstItm.prddesc) : 'Product';
                const defQty = (firstItm && firstItm.qty !== undefined) ? firstItm.qty : '1.0';
                const defUqc = (firstItm && (firstItm.uqc || firstItm.unit)) ? (firstItm.uqc || firstItm.unit) : 'NOS';
                let defUnitRate = (firstItm && (firstItm.unitprice || firstItm.unitrate || firstItm.unit_price)) ? (firstItm.unitprice || firstItm.unitrate || firstItm.unit_price) : '1000.00';
                let defTaxVal = (firstItm && (firstItm.assval !== undefined || firstItm.assamt !== undefined)) ? (firstItm.assval || firstItm.assamt) : (parseFloat(defQty) * parseFloat(defUnitRate)).toFixed(2);

                const initCh = getHsnChapterInfo(defHsn);
                const initTaxNum = parseFloat(String(defTaxVal).replace(/,/g, '')) || (parseFloat(defQty) * parseFloat(defUnitRate)) || 0;
                let initGstRate = 18.0;
                if (firstItm) {
                    const rawIg = parseFloat(firstItm.igstrt || 0);
                    const rawDual = parseFloat(firstItm.cgstrt || 0) + parseFloat(firstItm.sgstrt || 0);
                    const rawG = parseFloat(firstItm.gstrate || 0);
                    if (rawIg > 0.01) initGstRate = rawIg;
                    else if (rawDual > 0.01) initGstRate = rawDual;
                    else if (rawG > 0.01) initGstRate = rawG;
                    else initGstRate = 18.0;
                }
                const initGstAmt = Math.round(initTaxNum * (initGstRate / 100) * 100) / 100;
                const initTotLine = Math.round((initTaxNum + initGstAmt) * 100) / 100;

                barsHtml += `
                    <div class="copilot-inline-suggestion-bar copilot-hsn-pricing-bar" style="margin-top: 8px; margin-bottom: 6px; padding: 12px 14px; background: rgba(15, 23, 42, 0.95); border: 1px solid rgba(56, 189, 248, 0.45); border-radius: 8px; display: flex; flex-direction: column; gap: 8px;">
                        <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap;">
                            <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                                <span style="font-size: 0.84rem; font-weight: 700; color: #38bdf8;">📦 Product: <span style="color: #f1f5f9; font-weight: 600;">${escapeHtml(prdName)}</span></span>
                                <span class="copilot-hsn-chapter-badge" style="font-size: 0.74rem; font-weight: 700; color: #c084fc; font-family: 'JetBrains Mono', monospace; background: rgba(192, 132, 252, 0.12); padding: 3px 10px; border-radius: 6px; border: 1px solid rgba(192, 132, 252, 0.35); display: inline-flex; align-items: center; gap: 5px;">
                                    🏷️ Chapter <span class="hsn-ch-num">${escapeHtml(initCh.code)}</span>: <span class="hsn-ch-name">${escapeHtml(initCh.name)}</span>
                                </span>
                            </div>
                            <span class="copilot-calc-summary-badge" style="font-size: 0.74rem; color: #34d399; font-family: 'JetBrains Mono', monospace; background: rgba(52, 211, 153, 0.12); padding: 3px 10px; border-radius: 6px; border: 1px solid rgba(52, 211, 153, 0.35); font-weight: 700;">GST ${initGstRate}% (+₹${initGstAmt.toLocaleString('en-IN', {minimumFractionDigits: 2})}) ➔ Total: ₹${initTotLine.toLocaleString('en-IN', {minimumFractionDigits: 2})}</span>
                        </div>
                        <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                            <div style="display: flex; flex-direction: column; gap: 2px;">
                                <label style="font-size: 0.70rem; color: #94a3b8; font-weight: 600;">HSN CODE</label>
                                <input type="text" data-field="hsn" class="copilot-inline-hsn-input" placeholder="e.g. 84451910" value="${escapeHtml(defHsn)}" maxlength="8" oninput="updateCopilotHsnCalc(this)" onkeydown="if(event.key==='Enter'){event.preventDefault();submitCopilotHsnInput(this);}" style="background: #090e1a; color: #f8fafc; border: 1px solid #38bdf8; border-radius: 6px; padding: 5px 9px; font-size: 0.84rem; outline: none; font-family: 'JetBrains Mono', monospace; width: 95px; font-weight: 700;">
                            </div>
                            <div style="display: flex; flex-direction: column; gap: 2px;">
                                <label style="font-size: 0.70rem; color: #94a3b8; font-weight: 600;">RATE / PRICE (₹)</label>
                                <input type="number" step="any" data-field="rate" class="copilot-inline-rate-input" placeholder="e.g. 150000" value="${defUnitRate}" oninput="updateCopilotHsnCalc(this)" onkeydown="if(event.key==='Enter'){event.preventDefault();submitCopilotHsnInput(this);}" style="background: #090e1a; color: #f8fafc; border: 1px solid #38bdf8; border-radius: 6px; padding: 5px 9px; font-size: 0.84rem; outline: none; font-family: 'JetBrains Mono', monospace; width: 110px;">
                            </div>
                            <div style="display: flex; flex-direction: column; gap: 2px;">
                                <label style="font-size: 0.70rem; color: #94a3b8; font-weight: 600;">QTY</label>
                                <input type="number" step="any" data-field="qty" class="copilot-inline-qty-input" placeholder="e.g. 1" value="${defQty}" oninput="updateCopilotHsnCalc(this)" onkeydown="if(event.key==='Enter'){event.preventDefault();submitCopilotHsnInput(this);}" style="background: #090e1a; color: #f8fafc; border: 1px solid #38bdf8; border-radius: 6px; padding: 5px 9px; font-size: 0.84rem; outline: none; font-family: 'JetBrains Mono', monospace; width: 75px;">
                            </div>
                            <div style="display: flex; flex-direction: column; gap: 2px;">
                                <label style="font-size: 0.70rem; color: #94a3b8; font-weight: 600;">UNIT</label>
                                <input type="text" data-field="unit" class="copilot-inline-unit-input" placeholder="e.g. NOS" value="${escapeHtml(defUqc)}" maxlength="5" onkeydown="if(event.key==='Enter'){event.preventDefault();submitCopilotHsnInput(this);}" style="background: #090e1a; color: #f8fafc; border: 1px solid #38bdf8; border-radius: 6px; padding: 5px 9px; font-size: 0.84rem; outline: none; font-family: 'JetBrains Mono', monospace; width: 65px; font-weight: 700; text-transform: uppercase;">
                            </div>
                            <div style="display: flex; flex-direction: column; gap: 2px;">
                                <label style="font-size: 0.70rem; color: #94a3b8; font-weight: 600;">TAXABLE VALUE (₹)</label>
                                <input type="number" step="any" data-field="taxval" class="copilot-inline-tax-input" placeholder="e.g. 150000" value="${defTaxVal}" oninput="updateCopilotHsnCalc(this)" onkeydown="if(event.key==='Enter'){event.preventDefault();submitCopilotHsnInput(this);}" style="background: #090e1a; color: #f8fafc; border: 1px solid #38bdf8; border-radius: 6px; padding: 5px 9px; font-size: 0.84rem; outline: none; font-family: 'JetBrains Mono', monospace; width: 125px;">
                            </div>
                            <div style="display: flex; align-items: flex-end; padding-top: 14px; gap: 6px;">
                                <button type="button" class="copilot-action-btn" onclick="submitCopilotHsnInput(this)" style="background: linear-gradient(135deg, #0ea5e9, #6366f1); color: #fff; border: none; font-weight: 700; padding: 6px 14px; border-radius: 6px; cursor: pointer; white-space: nowrap;">✨ Apply &amp; Recalculate Tax</button>
                                <button type="button" class="copilot-action-btn" onclick="sendCopilotQuickMessage('Fix HSN from product description')" style="background: rgba(192, 132, 252, 0.2); border: 1px solid #c084fc; color: #e879f9; font-weight: 600; padding: 6px 12px; border-radius: 6px; cursor: pointer; white-space: nowrap;">⚡ ML Lookup</button>
                            </div>
                        </div>
                    </div>
                `;
            }
        };

        const renderPinStateBox = () => {
            if (renderedBoxCount > 0 || handledTypes.has('pin')) return;
            const pinAct = findAction(a => /set (?:supplier|buyer)?\s*pin:/i.test(a));
            const stAct = findAction(a => /set (?:supplier|buyer)?\s*state:/i.test(a));
            const hasPinStatePrompt = Boolean(
                activeTopic === 'pin_state' ||
                pinAct || stAct ||
                (tailPrompt.includes('pincode') && tailPrompt.includes('conflict')) ||
                tailPrompt.includes('pincode on invoice') ||
                tailPrompt.includes('postal pin') ||
                (tailPrompt.includes('state') && tailPrompt.includes('pin') && !tailPrompt.includes('aligned!') && !tailPrompt.includes('updated!')) ||
                tailPrompt.includes('jurisdiction')
            );
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
        if (activeTopic === 'docno') renderDocnoBox();
        else if (activeTopic === 'sup_gstin') renderSupGstinBox();
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
        if (renderedBoxCount === 0 && !isDocnoJustPatched && (!isDocNoValid || actions.some(a => /invoice no|docno/i.test(a)))) renderDocnoBox();
        if (renderedBoxCount === 0 && !isDateJustPatched && (!isDateValid || actions.some(a => /date/i.test(a)))) renderDateBox();
        if (renderedBoxCount === 0 && (actions.some(a => /pin|state/i.test(a)) || tailPrompt.includes('pincode') || tailPrompt.includes('postal pin') || tailPrompt.includes('conflict'))) renderPinStateBox();
        if (renderedBoxCount === 0 && (actions.some(a => /^(?:my gstin is|supplier gstin)/i.test(a.trim())) || tailPrompt.includes('15-digit supplier gstin'))) renderSupGstinBox();
        if (renderedBoxCount === 0 && (actions.some(a => /buyer gstin|urp/i.test(a)) || tailPrompt.includes('buyer gstin'))) renderBuyerGstinBox();
        if (renderedBoxCount === 0 && (actions.some(a => /hsn/i.test(a)) || tailPrompt.includes('hsn'))) renderHsnBox();
        if (renderedBoxCount === 0 && (actions.some(a => /vehicle/i.test(a)) || tailPrompt.includes('vehicle'))) renderVehicleBox();
        if (renderedBoxCount === 0 && (actions.some(a => /mode/i.test(a)) || tailPrompt.includes('mode'))) renderModeBox();
        if (renderedBoxCount === 0 && (actions.some(a => /subsupply/i.test(a)) || tailPrompt.includes('subsupply'))) renderSubsupplyBox();
        if (renderedBoxCount === 0 && (actions.some(a => /transporter/i.test(a)) || tailPrompt.includes('transporter'))) renderTransporterBox();
        if (renderedBoxCount === 0 && (actions.some(a => /tax\s*math/i.test(a)) || tailPrompt.includes('tax valuation'))) renderTaxMathBox();

        // 3. Fallback for any other "Set Key: Value" or "Key is Value" suggestion (strictly one-by-one)
        for (const act of actions) {
            const actL = act.toLowerCase();
            if (
                (handledTypes.has('docno') && (actL.includes('invoice no') || actL.includes('docno') || actL.includes('set invoice') || actL.includes('apply invoice no'))) ||
                (handledTypes.has('date') && (actL.includes('apply date') || actL.includes('set today') || actL.includes('change date to today') || actL.includes('change date to yesterday') || actL.includes('set date:'))) ||
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
        }