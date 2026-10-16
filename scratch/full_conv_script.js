
        // Global State
        let currentMode = 'random'; // 'random' or 'custom'
        let currentRandomCount = 1;
        let pipelineData = null;
        let currentValidationReport = null;
        let currentCorrectedPayload = null;
        let initialDirtyPayloadStr = '';
        let currentLivePayload = null;
        let lastRawJsonStr = '';
        let lastCleanJsonStr = '';
        let lastSummaryText = '';
        let fullAuditRecords = [];
        let cumulativeErrorLogs = [];

        // DOM Elements
        const rawJsonEditor = document.getElementById('rawJsonEditor');
        const jsonStatusBadge = document.getElementById('jsonStatusBadge');
        const charCountLabel = document.getElementById('charCountLabel');
        const invoiceCountLabel = document.getElementById('invoiceCountLabel');
        const loadingOverlay = document.getElementById('loadingOverlay');
        const loadingText = document.getElementById('loadingText');
        const toastBox = document.getElementById('toastBox');
        const toastMessage = document.getElementById('toastMessage');

        // Initialize on page load
        window.addEventListener('DOMContentLoaded', async () => {
            initSplitResizer();
            const savedLayout = localStorage.getItem('copilot_layout_mode') || 'auto';
            setCopilotLayout(savedLayout);
            // Fetch live API module endpoint configurations
            await loadConfiguredEndpoints();
            // Load initial random batch so the user has immediate data to explore
            await handleGenerateRandom();
        });


        // Mode Switching
        function selectInputMode(mode) {
            currentMode = mode;
            const cardRandom = document.getElementById('modeCardRandom');
            const cardCustom = document.getElementById('modeCardCustom');
            const randomBox = document.getElementById('randomSettingsBox');
            const editorTitle = document.getElementById('editorPanelTitle');

            if (mode === 'random') {
                cardRandom.classList.add('active');
                cardCustom.classList.remove('active');
                randomBox.style.display = 'flex';
                editorTitle.textContent = 'Dirty Payload Inspector (Generated)';
            } else {
                cardCustom.classList.add('active');
                cardRandom.classList.remove('active');
                randomBox.style.display = 'none';
                editorTitle.textContent = 'Customer Payload Ingestion';
            }
        }

        // Pill selector for invoice count
        function setRandomCount(count, btnElement) {
            currentRandomCount = count;
            document.querySelectorAll('.pill-selector-group .pill-btn').forEach(btn => btn.classList.remove('active'));
            btnElement.classList.add('active');
            document.getElementById('selectedCountLabel').textContent = `${count} Invoice${count > 1 ? 's' : ''}`;
        }

        // Generate Random Dirty Batch via Backend API
        async function handleGenerateRandom() {
            showLoading(`Generating ${currentRandomCount} randomized invoice(s) with dirty fields...`);
            try {
                const response = await fetch('/api/converter/generate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ count: currentRandomCount })
                });

                if (!response.ok) {
                    throw new Error(`Server returned error ${response.status}`);
                }

                const result = await response.json();
                if (result.status === 'success' && result.payload) {
                    const dirtyStr = JSON.stringify(result.payload, null, 2);
                    rawJsonEditor.value = dirtyStr;
                    initialDirtyPayloadStr = dirtyStr;
                    currentLivePayload = result.payload;
                    validateJsonInput();
                    
                    // Silent background audit preview to initialize Copilot state
                    try {
                        const auditResp = await fetch('/api/converter/process', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ payload: result.payload })
                        });
                        if (auditResp.ok) {
                            pipelineData = await auditResp.json();
                            currentValidationReport = pipelineData.validation_report;
                            currentCorrectedPayload = pipelineData.corrected_payload;
                        }
                    } catch (auditErr) {
                        console.warn('Initial background audit preview:', auditErr);
                    }

                    showToast(`Generated ${result.count} invoice(s) with dirty field values!`, 'success');
                    // Automatically inspect and seed Copilot diagnostic with the fresh payload
                    await triggerCopilotAutoDiagnostic();
                } else {
                    throw new Error('Invalid response structure from generator API');
                }
            } catch (err) {
                console.error(err);
                showToast(`Failed to generate: ${err.message}`, 'error');
            } finally {
                hideLoading();
            }
        }

        // Load Default Sample from Backend
        async function handleLoadSample() {
            showLoading('Loading canonical sample dirty payload...');
            try {
                const response = await fetch('/api/converter/sample');
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                const data = await response.json();
                if (data.payload) {
                    const dirtyStr = JSON.stringify(data.payload, null, 2);
                    rawJsonEditor.value = dirtyStr;
                    initialDirtyPayloadStr = dirtyStr;
                    currentLivePayload = data.payload;
                    validateJsonInput();

                    // Silent background audit preview to initialize Copilot state
                    try {
                        const auditResp = await fetch('/api/converter/process', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ payload: data.payload })
                        });
                        if (auditResp.ok) {
                            pipelineData = await auditResp.json();
                            currentValidationReport = pipelineData.validation_report;
                            currentCorrectedPayload = pipelineData.corrected_payload;
                        }
                    } catch (auditErr) {
                        console.warn('Initial background audit preview:', auditErr);
                    }

                    showToast('Sample dirty payload loaded!', 'success');
                    // Automatically inspect and seed Copilot diagnostic with the sample payload
                    await triggerCopilotAutoDiagnostic();
                }
            } catch (err) {
                showToast(`Error loading sample: ${err.message}`, 'error');
            } finally {
                hideLoading();
            }
        }

        // File Upload Handling
        function handleFileUpload(event) {
            const file = event.target.files[0];
            if (!file) return;

            selectInputMode('custom');
            const reader = new FileReader();
            reader.onload = function(e) {
                try {
                    const parsed = JSON.parse(e.target.result);
                    rawJsonEditor.value = JSON.stringify(parsed, null, 2);
                    validateJsonInput();
                    showToast(`Loaded "${file.name}" (${(file.size / 1024).toFixed(1)} KB)`, 'success');
                } catch (jsonErr) {
                    rawJsonEditor.value = e.target.result;
                    validateJsonInput();
                    showToast(`File loaded with JSON syntax warning!`, 'error');
                }
            };
            reader.readAsText(file);
        }

        // JSON Input Validation & Stats Counter
        function validateJsonInput() {
            const val = rawJsonEditor.value.trim();
            charCountLabel.textContent = `${val.length.toLocaleString()} Characters`;

            if (!val) {
                jsonStatusBadge.textContent = 'Empty';
                jsonStatusBadge.className = 'editor-status-indicator';
                invoiceCountLabel.textContent = '0 Invoices Detected';
                return false;
            }

            try {
                const parsed = JSON.parse(val);
                jsonStatusBadge.textContent = 'Valid JSON ✓';
                jsonStatusBadge.className = 'editor-status-indicator';

                let invCount = 0;
                if (Array.isArray(parsed)) {
                    invCount = parsed.length;
                } else if (parsed && typeof parsed === 'object') {
                    if (Array.isArray(parsed.einvoices)) {
                        invCount = parsed.einvoices.length;
                    } else {
                        invCount = 1;
                    }
                }
                invoiceCountLabel.textContent = `${invCount} Invoice${invCount === 1 ? '' : 's'} Detected`;
                return true;
            } catch (err) {
                jsonStatusBadge.textContent = 'Syntax Error ✗';
                jsonStatusBadge.className = 'editor-status-indicator error';
                invoiceCountLabel.textContent = 'Parsing error';
                return false;
            }
        }

        // Format / Prettify Editor Content
        function handleFormatJson() {
            try {
                const parsed = JSON.parse(rawJsonEditor.value);
                rawJsonEditor.value = JSON.stringify(parsed, null, 2);
                validateJsonInput();
                showToast('JSON beautified with 2-space indentation', 'success');
            } catch (err) {
                showToast('Cannot format: invalid JSON syntax', 'error');
            }
        }

        // Clear Editor Content
        function handleClearEditor() {
            rawJsonEditor.value = '';
            validateJsonInput();
            showToast('Editor cleared', 'success');
        }

        // Copy Text
        function handleCopyPayload() {
            copyTextToClipboard(rawJsonEditor.value, 'Payload copied to clipboard!');
        }

        // Main Conversion Pipeline Execution
        async function handleProcessPipeline() {
            const rawText = rawJsonEditor.value.trim();
            if (!rawText) {
                showToast('Please provide a JSON payload before running the pipeline', 'error');
                return;
            }

            let parsedPayload;
            try {
                parsedPayload = JSON.parse(rawText);
            } catch (err) {
                showToast('Invalid JSON syntax: please correct errors before audit', 'error');
                return;
            }

            showLoading('Running auto-corrections, NIC schema transformation, and rule audits...');

            try {
                const response = await fetch('/api/converter/process', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ payload: parsedPayload })
                });

                if (!response.ok) {
                    const errDetail = await response.json();
                    throw new Error(errDetail.detail || `HTTP Error ${response.status}`);
                }

                pipelineData = await response.json();
                currentValidationReport = pipelineData.validation_report;
                currentCorrectedPayload = pipelineData.corrected_payload;
                initialDirtyPayloadStr = JSON.stringify(parsedPayload, null, 2);
                currentLivePayload = pipelineData.corrected_payload;
                lastRawJsonStr = initialDirtyPayloadStr;
                lastCleanJsonStr = JSON.stringify(pipelineData.corrected_payload, null, 2);
                lastSummaryText = pipelineData.summary_text;
                fullAuditRecords = pipelineData.audit_records || [];

                // Render Dashboard
                renderExecutiveKPIs(pipelineData.metrics);
                renderAuditTable(fullAuditRecords);
                renderDiffPanes(lastRawJsonStr, lastCleanJsonStr);
                renderValidationCards(pipelineData.validation_report);
                renderTerminalSummary(pipelineData.summary_text);
                renderPriceAnomalyPane(pipelineData.validation_report);

                // Show Dashboard Sections
                document.getElementById('kpiDashboardSection').style.display = 'block';
                document.getElementById('outputDashboardSection').style.display = 'block';

                // Scroll smoothly down to the KPI section
                document.getElementById('kpiDashboardSection').scrollIntoView({ behavior: 'smooth' });

                showToast('Pipeline audit completed successfully!', 'success');
            } catch (err) {
                console.error(err);
                showToast(`Audit failed: ${err.message}`, 'error');
            } finally {
                hideLoading();
            }
        }

        // Render KPI Counters & Financials
        function renderExecutiveKPIs(metrics) {
            document.getElementById('kpiTotalInvoices').textContent = metrics.total_invoices || 0;
            document.getElementById('kpiValidInvoices').textContent = metrics.valid_invoices || 0;
            document.getElementById('kpiFailedInvoices').textContent = metrics.failed_invoices || 0;
            document.getElementById('kpiTotalCorrections').textContent = metrics.total_corrections || 0;

            const complianceRate = metrics.compliance_rate || 0;
            document.getElementById('kpiValidRateBadge').textContent = `${complianceRate}% Compliant`;

            const errCount = metrics.total_errors || 0;
            document.getElementById('kpiFailedRateBadge').textContent = `${errCount} Error${errCount === 1 ? '' : 's'}`;

            // Tab counter pills
            document.getElementById('tabCountCorrections').textContent = metrics.total_corrections || 0;
            document.getElementById('tabCountErrors').textContent = metrics.total_errors || 0;

            // AI Price Anomaly Metrics
            const anom = metrics.price_anomalies || {};
            const anomStatusEl = document.getElementById('finPriceAnomalyStatus');
            const anomTabCount = document.getElementById('tabCountPriceAnomalies');
            if (anomTabCount) anomTabCount.textContent = anom.total_anomalies || 0;
            if (anomStatusEl) {
                if (anom.total_anomalies > 0) {
                    anomStatusEl.innerHTML = `<span style="color:#f43f5e; font-weight:700;">🚨 ${anom.total_anomalies} Anomaly (${anom.status})</span>`;
                } else {
                    anomStatusEl.innerHTML = `<span style="color:#10b981; font-weight:700;">🛡️ Clean (0 Anomaly)</span>`;
                }
            }

            // Financial valuations
            const fin = metrics.financials || {};
            document.getElementById('finTtlassval').textContent = formatCurrency(fin.ttlassval || 0);
            document.getElementById('finCgstval').textContent = formatCurrency(fin.cgstval || 0);
            document.getElementById('finSgstval').textContent = formatCurrency(fin.sgstval || 0);
            document.getElementById('finIgstval').textContent = formatCurrency(fin.igstval || 0);
            document.getElementById('finTotinvval').textContent = formatCurrency(fin.totinvval || 0);

            // Populate category dropdown in table filter
            populateCategoryFilter(metrics.category_counts || {});
        }

        // Render AI Price Anomaly Diagnostic Table (Tab 5)
        function renderPriceAnomalyPane(report) {
            const tbody = document.getElementById('priceAnomalyTableBody');
            const overviewBadge = document.getElementById('priceAnomalyOverviewBadge');
            if (!tbody) return;
            tbody.innerHTML = '';

            const results = report?.results || [];
            let allFindings = [];

            results.forEach(invRes => {
                const invNum = invRes.invoice_number || 'INV';
                const anomReport = invRes.price_anomaly_report;
                if (anomReport && anomReport.findings) {
                    anomReport.findings.forEach(f => {
                        allFindings.push({ ...f, invoice_number: invNum });
                    });
                }
            });

            if (allFindings.length === 0) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="8" style="text-align: center; padding: 36px; color: var(--text-dim);">
                            🛡️ All line items conform to statutory price benchmarks. No anomalies detected.
                        </td>
                    </tr>
                `;
                if (overviewBadge) {
                    overviewBadge.innerHTML = '<span class="pill-status status-valid">🛡️ No Price Anomalies (Clean)</span>';
                }
                return;
            }

            const anomaliesOnly = allFindings.filter(f => f.is_anomaly);
            if (overviewBadge) {
                if (anomaliesOnly.length > 0) {
                    overviewBadge.innerHTML = `<span class="pill-status status-invalid" style="background: rgba(244,63,94,0.2); color:#fda4af; border:1px solid rgba(244,63,94,0.4);">🚨 ${anomaliesOnly.length} Price Anomaly Flagged</span>`;
                } else {
                    overviewBadge.innerHTML = '<span class="pill-status status-valid">🛡️ All Items Within Normal Benchmarks</span>';
                }
            }

            allFindings.forEach(f => {
                const tr = document.createElement('tr');
                if (f.is_anomaly) {
                    tr.style.background = f.severity === 'CRITICAL' ? 'rgba(244, 63, 94, 0.08)' : 'rgba(245, 158, 11, 0.05)';
                }

                let typeBadge = '';
                if (f.anomaly_type === 'OVER_INVOICING') {
                    typeBadge = '<span class="type-pill" style="background: rgba(244,63,94,0.25); color:#fda4af; border:1px solid #f43f5e;">OVER-INVOICING</span>';
                } else if (f.anomaly_type === 'UNDER_INVOICING') {
                    typeBadge = '<span class="type-pill" style="background: rgba(245,158,11,0.25); color:#fde68a; border:1px solid #f59e0b;">UNDER-INVOICING</span>';
                } else if (f.anomaly_type === 'DECIMAL_SHIFT_TYPO') {
                    typeBadge = '<span class="type-pill" style="background: rgba(168,85,247,0.25); color:#e9d5ff; border:1px solid #a855f7;">TYPO DETECTED</span>';
                } else {
                    typeBadge = '<span class="type-pill type-correction" style="background: rgba(16,185,129,0.2); color:#6ee7b7; border:1px solid #10b981;">NORMAL</span>';
                }

                let riskMeter = '';
                if (f.risk_score >= 80) {
                    riskMeter = `<span style="color:#f43f5e; font-weight:700;">🔴 ${f.risk_score}/100 (Critical)</span>`;
                } else if (f.risk_score >= 50) {
                    riskMeter = `<span style="color:#f59e0b; font-weight:700;">🟡 ${f.risk_score}/100 (High)</span>`;
                } else if (f.risk_score > 0) {
                    riskMeter = `<span style="color:#38bdf8; font-weight:600;">🔵 ${f.risk_score}/100 (Moderate)</span>`;
                } else {
                    riskMeter = '<span style="color:#10b981; font-weight:600;">🟢 0/100 (Safe)</span>';
                }

                let actionBtn = '';
                if (f.is_anomaly) {
                    const fixRate = f.suggested_rate || f.benchmark_median;
                    actionBtn = `
                        <button type="button" class="btn-copy-url" style="margin-top:4px; font-size:0.75rem; background:rgba(99,102,241,0.25); color:#a5b4fc; border:1px solid #6366f1; cursor:pointer;" 
                            onclick="sendCopilotQuickMessage('Fix Item ${f.item_index} rate to ${fixRate}')">
                            🔧 Auto-Fix to ₹${Number(fixRate).toLocaleString('en-IN', {minimumFractionDigits: 2})}
                        </button>
                    `;
                } else {
                    actionBtn = '<span style="color:var(--text-dim); font-size:0.75rem;">Verified OK</span>';
                }

                const benchText = f.benchmark_min !== undefined ? `₹${Number(f.benchmark_min).toLocaleString('en-IN')} - ₹${Number(f.benchmark_max).toLocaleString('en-IN')}` : 'General UQC';

                tr.innerHTML = `
                    <td style="font-family:'JetBrains Mono', monospace; font-weight:700;">${escapeHtml(f.invoice_number)}</td>
                    <td><strong>Item #${f.item_index}:</strong> ${escapeHtml(f.prdnm)}</td>
                    <td><span class="field-tag">${escapeHtml(f.hsncd || '-')} / ${escapeHtml(f.uqc)}</span></td>
                    <td style="font-family:'JetBrains Mono', monospace; font-weight:700; ${f.is_anomaly ? 'color:#fda4af;' : ''}">₹${Number(f.unitrate).toLocaleString('en-IN', {minimumFractionDigits: 2})}</td>
                    <td style="font-size:0.78rem; color:var(--text-muted);">${benchText}</td>
                    <td>${typeBadge}</td>
                    <td>${riskMeter}</td>
                    <td style="max-width:320px; font-size:0.78rem; line-height:1.4;">
                        <div>${escapeHtml(f.reason)}</div>
                        ${actionBtn}
                    </td>
                `;

                tbody.appendChild(tr);
            });
        }

        function formatCurrency(val) {
            return '₹ ' + Number(val).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        }

        function populateCategoryFilter(categoryCounts) {
            const select = document.getElementById('auditCategoryFilterSelect');
            select.innerHTML = '<option value="ALL">All Categories</option>';
            for (const [cat, count] of Object.entries(categoryCounts)) {
                const opt = document.createElement('option');
                opt.value = cat;
                opt.textContent = `${cat} (${count})`;
                select.appendChild(opt);
            }
        }

        // Render Tabular Audit Records (Tab 1)
        function renderAuditTable(records) {
            const tbody = document.getElementById('auditTableBody');
            tbody.innerHTML = '';

            if (!records || records.length === 0) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="8" style="text-align: center; padding: 36px; color: var(--text-dim);">
                            No auto-corrections or validation errors logged for this payload.
                        </td>
                    </tr>
                `;
                return;
            }

            records.forEach(row => {
                const tr = document.createElement('tr');

                // Status pill
                const isStatusValid = row.status === 'VALID';
                const statusPill = `<span class="pill-status ${isStatusValid ? 'status-valid' : 'status-invalid'}">${escapeHtml(row.status)}</span>`;

                // Type pill
                const isCorrection = row.type === 'AUTO_CORRECTION';
                const typePill = `<span class="type-pill ${isCorrection ? 'type-correction' : 'type-error'}">${isCorrection ? 'AUTO-FIX' : 'NIC ERROR'}</span>`;

                // Value pills
                const origVal = row.original && row.original !== '-' 
                    ? `<span class="val-original">${escapeHtml(row.original)}</span>` 
                    : '<span style="color:var(--text-dim);">-</span>';

                const corrVal = row.corrected && row.corrected !== '-' 
                    ? `<span class="val-corrected">${escapeHtml(row.corrected)}</span>` 
                    : '<span style="color:var(--text-dim);">-</span>';

                tr.innerHTML = `
                    <td style="font-weight: 700; font-family: 'JetBrains Mono', monospace;">${escapeHtml(row.invoice_number)}</td>
                    <td>${statusPill}</td>
                    <td>${typePill}</td>
                    <td><span style="font-size: 0.78rem; font-weight: 600; color: #a5b4fc;">${escapeHtml(row.category)}</span></td>
                    <td><span class="field-tag">${escapeHtml(row.field)}</span></td>
                    <td>${origVal}</td>
                    <td>${corrVal}</td>
                    <td style="max-width: 320px; color: var(--text-muted); line-height: 1.4;">${escapeHtml(row.description)}</td>
                `;

                tbody.appendChild(tr);
            });
        }

        // Filter Audit Table
        function filterAuditTable() {
            const query = document.getElementById('auditTableSearchInput').value.toLowerCase().trim();
            const typeFilter = document.getElementById('auditTypeFilterSelect').value;
            const categoryFilter = document.getElementById('auditCategoryFilterSelect').value;

            const filtered = fullAuditRecords.filter(item => {
                // Type filter
                if (typeFilter !== 'ALL' && item.type !== typeFilter) return false;
                // Category filter
                if (categoryFilter !== 'ALL' && item.category !== categoryFilter) return false;
                // Text search
                if (query) {
                    const matchText = (
                        (item.invoice_number || '') + ' ' +
                        (item.field || '') + ' ' +
                        (item.category || '') + ' ' +
                        (item.description || '') + ' ' +
                        (item.original || '') + ' ' +
                        (item.corrected || '')
                    ).toLowerCase();
                    if (!matchText.includes(query)) return false;
                }
                return true;
            });

            renderAuditTable(filtered);
        }

        // Render Side-by-Side Diff (Tab 2)
        function renderDiffPanes(rawStr, cleanStr) {
            document.getElementById('diffDirtyPane').textContent = rawStr;
            document.getElementById('diffCleanPane').textContent = cleanStr;
        }

        // Render NIC Rule Validation Cards (Tab 3)
        function renderValidationCards(report) {
            const container = document.getElementById('validationCardsContainer');
            container.innerHTML = '';

            const results = report.results || [];
            if (results.length === 0) {
                container.innerHTML = '<div style="color: var(--text-dim); padding: 20px;">No invoice results available.</div>';
                return;
            }

            results.forEach((invRes, index) => {
                const card = document.createElement('div');
                card.className = 'invoice-rule-card';

                const isValid = invRes.status === 'VALID';
                const statusBadge = isValid 
                    ? '<span class="pill-status status-valid">APPROVED (VALID)</span>'
                    : '<span class="pill-status status-invalid">REJECTED (FAIL)</span>';

                let errorBlocks = '';
                if (invRes.errors && invRes.errors.length > 0) {
                    errorBlocks = invRes.errors.map(err => `
                        <div class="rule-issue-box">
                            <div>
                                <span class="rule-code-badge">NIC Code ${err.error_code}</span>
                                <span class="rule-message">Field: [${escapeHtml(err.field)}] — ${escapeHtml(err.message)}</span>
                            </div>
                            <div class="rule-meta-line">
                                <strong>Root Cause:</strong> ${escapeHtml(err.reason || 'Rule mismatch')}
                            </div>
                            ${err.resolution ? `
                                <div class="rule-resolution-line">
                                    💡 <strong>Recommended Fix:</strong> ${escapeHtml(err.resolution)}
                                </div>
                            ` : ''}
                        </div>
                    `).join('');
                } else {
                    errorBlocks = `
                        <div class="clean-pass-box">
                            <span>✓</span>
                            <span>All 18 NIC IRN Pre-Flight Validation Rules Passed Successfully. No business rule violations detected.</span>
                        </div>
                    `;
                }

                card.innerHTML = `
                    <div class="inv-card-header">
                        <div class="inv-card-title">
                            <h3>Invoice #${index + 1}: ${escapeHtml(invRes.invoice_number)}</h3>
                            ${statusBadge}
                        </div>
                        <div style="font-size: 0.8rem; color: var(--text-muted); display: flex; gap: 14px;">
                            <span>Auto-Corrections: <strong>${invRes.corrections_applied_count || 0}</strong></span>
                            <span>Errors: <strong>${invRes.error_count || 0}</strong></span>
                        </div>
                    </div>
                    <div>
                        ${errorBlocks}
                    </div>
                `;

                container.appendChild(card);
            });
        }

        // Render Terminal Summary (Tab 4)
        function renderTerminalSummary(summaryText) {
            document.getElementById('terminalSummaryBody').textContent = summaryText || 'No summary generated.';
        }

        // Switch Output Dashboard Tabs
        function switchDashboardTab(tabId, el) {
            document.querySelectorAll('.dashboard-nav-tabs .dash-tab-btn').forEach(btn => btn.classList.remove('active'));
            document.querySelectorAll('.output-dashboard-card .tab-pane').forEach(pane => pane.classList.remove('active'));

            const targetBtn = el || (window.event && window.event.currentTarget) || document.querySelector(`.dashboard-nav-tabs .dash-tab-btn[data-tab="${tabId}"]`);
            if (targetBtn) targetBtn.classList.add('active');
            const pane = document.getElementById(tabId);
            if (pane) pane.classList.add('active');
        }

        // File Download Handler
        function downloadFile(fileType) {
            const a = document.createElement('a');
            a.href = `/api/converter/download/${fileType}`;
            a.download = '';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            showToast(`Initiating ${fileType} download...`, 'success');
        }

        // Utility: Copy to Clipboard
        function copyTextToClipboard(text, successMsg) {
            if (!text) return;
            navigator.clipboard.writeText(text).then(() => {
                showToast(successMsg, 'success');
            }).catch(() => {
                showToast('Failed to copy text', 'error');
            });
        }

        // Utility: Toast
        function showToast(msg, type = 'success') {
            toastMessage.textContent = msg;
            toastBox.className = `toast-notification show ${type === 'success' ? 'toast-success' : 'toast-error'}`;
            setTimeout(() => {
                toastBox.classList.remove('show');
            }, 3500);
        }

        // Utility: Loading
        function showLoading(msg = 'Processing GST Sentinel Pipeline...') {
            loadingText.textContent = msg;
            loadingOverlay.style.display = 'flex';
        }

        function hideLoading() {
            loadingOverlay.style.display = 'none';
        }

        // Utility: Escape HTML
        function escapeHtml(str) {
            if (str === null || str === undefined) return '';
            return String(str)
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#039;');
        }

        // ==============================================================
        // AI COMPLIANCE COPILOT & SPLIT-SCREEN CHATBOT LOGIC
        // ==============================================================
        let copilotChatHistory = [];
        let isCopilotSplitActive = true;
        let activeCopilotLayout = localStorage.getItem('copilot_layout_mode') || 'auto';

        // Set Copilot Layout & Screen Split Width
        function setCopilotLayout(mode) {
            const splitContainer = document.getElementById('editorCopilotSplit');
            if (!splitContainer) return;
            const buttons = document.querySelectorAll('.copilot-layout-btn');
            buttons.forEach(btn => btn.classList.remove('active'));

            // Clear any inline drag styling
            splitContainer.style.gridTemplateColumns = '';

            splitContainer.classList.remove('split-half', 'split-wide', 'split-max', 'editor-only');
            activeCopilotLayout = mode;

            if (mode === 'half') {
                splitContainer.classList.add('split-half');
                document.getElementById('btnSplitHalf')?.classList.add('active');
                showToast('📐 50:50 Balanced Split Activated', 'info');
            } else if (mode === 'wide') {
                splitContainer.classList.add('split-wide');
                document.getElementById('btnSplitWide')?.classList.add('active');
                showToast('📐 Wide Chat Window Activated (65% width)', 'info');
            } else if (mode === 'full') {
                splitContainer.classList.add('split-max');
                document.getElementById('btnSplitFull')?.classList.add('active');
                showToast('⤢ Full Chat Mode Activated', 'info');
            } else {
                // 'auto'
                document.getElementById('btnSplitAuto')?.classList.add('active');
                showToast('⚡ Smart Resolution Auto-Adjust Active', 'info');
            }

            localStorage.setItem('copilot_layout_mode', mode);
        }

        // Toggle between Split Screen and Full-Width Editor
        function toggleCopilotSplit() {
            const splitContainer = document.getElementById('editorCopilotSplit');
            const toggleText = document.getElementById('toggleCopilotText');
            isCopilotSplitActive = !isCopilotSplitActive;

            if (isCopilotSplitActive) {
                splitContainer.classList.remove('editor-only');
                toggleText.textContent = 'Copilot Split';
                const savedMode = localStorage.getItem('copilot_layout_mode') || 'auto';
                setCopilotLayout(savedMode);
                showToast('AI Copilot Split-Screen Enabled', 'success');
            } else {
                splitContainer.classList.remove('split-half', 'split-wide', 'split-max');
                splitContainer.classList.add('editor-only');
                toggleText.textContent = 'Show Copilot';
                showToast('Full-Width Editor Mode Activated', 'success');
            }
        }

        // Initialize Draggable Split Resizer
        function initSplitResizer() {
            const resizer = document.getElementById('splitResizer');
            const splitContainer = document.getElementById('editorCopilotSplit');
            if (!resizer || !splitContainer) return;

            let isDragging = false;

            resizer.addEventListener('mousedown', (e) => {
                isDragging = true;
                resizer.classList.add('is-dragging');
                document.body.style.cursor = 'col-resize';
                document.body.style.userSelect = 'none';
                e.preventDefault();
            });

            window.addEventListener('mousemove', (e) => {
                if (!isDragging) return;
                const rect = splitContainer.getBoundingClientRect();
                const totalWidth = rect.width;
                if (totalWidth <= 0) return;

                // Position within splitContainer
                const mouseX = e.clientX - rect.left;
                let editorPct = (mouseX / totalWidth) * 100;

                // Bounds checking (keep editor between 22% and 78%)
                if (editorPct < 22) editorPct = 22;
                if (editorPct > 78) editorPct = 78;

                const copilotPct = 100 - editorPct;

                // Remove preset classes while custom dragging
                splitContainer.classList.remove('split-half', 'split-wide', 'split-max');
                const buttons = document.querySelectorAll('.copilot-layout-btn');
                buttons.forEach(btn => btn.classList.remove('active'));

                splitContainer.style.gridTemplateColumns = `${editorPct.toFixed(1)}% ${copilotPct.toFixed(1)}%`;
            });

            window.addEventListener('mouseup', () => {
                if (isDragging) {
                    isDragging = false;
                    resizer.classList.remove('is-dragging');
                    document.body.style.cursor = '';
                    document.body.style.userSelect = '';
                }
            });

            // Double click on resizer knob to reset to Auto
            resizer.addEventListener('dblclick', () => {
                setCopilotLayout('auto');
            });
        }

        // Update Copilot Status Badge in Header
        function updateCopilotHeaderStatus(validationReport) {
            const statusText = document.getElementById('copilotStatusText');
            const statusPill = document.getElementById('copilotStatusPill');
            if (!statusText) return;

            if (!validationReport || !validationReport.results || validationReport.results.length === 0) {
                statusText.textContent = 'Active';
                statusText.style.color = '#38bdf8';
                return;
            }

            const firstRes = validationReport.results[0] || {};
            const errCount = (firstRes.errors || []).length;
            if (errCount === 0) {
                statusText.textContent = '100% Compliant';
                statusText.style.color = '#10b981';
                if (statusPill) {
                    statusPill.style.borderColor = 'rgba(16, 185, 129, 0.4)';
                    const dot = statusPill.querySelector('span');
                    if (dot) dot.style.background = '#10b981';
                }
            } else {
                statusText.textContent = `${errCount} Error${errCount > 1 ? 's' : ''} Remaining`;
                statusText.style.color = '#f43f5e';
                if (statusPill) {
                    statusPill.style.borderColor = 'rgba(244, 63, 94, 0.4)';
                    const dot = statusPill.querySelector('span');
                    if (dot) dot.style.background = '#f43f5e';
                }
            }
        }

        // Trigger Automatic Diagnostic on current payload in editor
        async function triggerCopilotAutoDiagnostic(customNotice = null) {
            const feed = document.getElementById('copilotMessagesFeed');
            if (!feed) return;

            copilotChatHistory = [];

            let currentPayload = null;
            try {
                const rawEditorText = rawJsonEditor.value.trim();
                if (rawEditorText) {
                    currentPayload = JSON.parse(rawEditorText);
                }
            } catch (err) {
                currentPayload = null;
            }

            if (!currentPayload) {
                feed.innerHTML = `
                    <div class="copilot-msg bot">
                        <div class="msg-bubble">
                            👋 <strong>No valid JSON payload in editor.</strong> Load a sample payload or generate a batch to begin real-time NIC compliance audits!
                        </div>
                    </div>
                `;
                updateCopilotPills(["Load Sample", "Generate Fresh Dirty Batch", "Format JSON"]);
                updateCopilotHeaderStatus(null);
                return;
            }

            feed.innerHTML = `
                <div class="copilot-msg bot" id="copilotAutoThinking">
                    <div class="msg-bubble" style="color: var(--accent-cyan); display: flex; align-items: center; gap: 8px;">
                        <span class="pulse-dot" style="width: 8px; height: 8px; background: #38bdf8;"></span>
                        <span>Auto-detecting NIC compliance errors across active payload...</span>
                    </div>
                </div>
            `;

            try {
                const response = await fetch('/api/converter/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        message: "Why did my invoice fail?",
                        payload: currentPayload,
                        validation_report: currentValidationReport || null,
                        chat_history: []
                    })
                });

                const thinkingEl = document.getElementById('copilotAutoThinking');
                if (thinkingEl) thinkingEl.remove();

                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                const data = await response.json();

                const botMsgDiv = document.createElement('div');
                botMsgDiv.className = 'copilot-msg bot';

                let noticePrefix = customNotice ? `<div style="font-size:0.85rem; color:#94a3b8; margin-bottom:8px;">${escapeHtml(customNotice)}</div>` : '';
                let replyHtml = `<div class="msg-bubble">${noticePrefix}${formatMarkdownReply(data.reply)}</div>`;

                if (data.interactive_actions && data.interactive_actions.length > 0) {
                    const actionBtns = data.interactive_actions.map(act => 
                        `<button type="button" class="copilot-action-btn" onclick="sendCopilotQuickMessage('${escapeHtml(act)}')">${escapeHtml(act)}</button>`
                    ).join(' ');
                    replyHtml += `<div class="msg-action-bar">${actionBtns}</div>`;
                }

                botMsgDiv.innerHTML = replyHtml;
                feed.innerHTML = '';
                feed.appendChild(botMsgDiv);
                feed.scrollTop = feed.scrollHeight;

                if (data.quick_prompts && data.quick_prompts.length > 0) {
                    updateCopilotPills(data.quick_prompts);
                } else if (data.interactive_actions && data.interactive_actions.length > 0) {
                    updateCopilotPills(data.interactive_actions);
                }

                updateCopilotHeaderStatus(data.validation_report);

            } catch (err) {
                const thinkingEl = document.getElementById('copilotAutoThinking');
                if (thinkingEl) thinkingEl.remove();

                feed.innerHTML = `
                    <div class="copilot-msg bot">
                        <div class="msg-bubble">
                            👋 <strong>Inspection Ready.</strong> Tell me your GSTIN or ask to fix an error to start.
                        </div>
                    </div>
                `;
            }
        }

        // Clear Chat History and Auto-Detect Active Errors Immediately
        async function clearCopilotChat() {
            showToast('Chat cleared — re-evaluating invoice errors...', 'info');
            await triggerCopilotAutoDiagnostic('🧹 Chat history cleared. Active payload re-inspected:');
        }

        // Quick Message Pill Click
        function sendCopilotQuickMessage(text) {
            const input = document.getElementById('copilotInputBox');
            input.value = text;
            handleCopilotSubmit(new Event('submit'));
        }

        // Update Quick Prompt Pills
        function updateCopilotPills(prompts) {
            if (!prompts || !prompts.length) return;
            const container = document.getElementById('copilotPillsBar');
            container.innerHTML = prompts.map(p => `
                <button type="button" class="copilot-pill" onclick="sendCopilotQuickMessage('${escapeHtml(p)}')">
                    ${escapeHtml(p)}
                </button>
            `).join('');
        }

        // Toggle Connected Module Endpoints Hub Drawer
        function toggleEndpointsHub() {
            const body = document.getElementById('endpointsHubBody');
            const arrow = document.getElementById('endpointsToggleArrow');
            const text = document.getElementById('endpointsToggleText');
            if (!body) return;
            const isCollapsed = body.classList.toggle('is-collapsed');
            if (isCollapsed) {
                if (arrow) arrow.textContent = '▼';
                if (text) text.textContent = 'Show Details';
            } else {
                if (arrow) arrow.textContent = '▲';
                if (text) text.textContent = 'Hide Details';
            }
        }

        // Copy Endpoint URL to Clipboard
        function copyEndpointText(text, btn) {
            if (!navigator.clipboard) {
                showToast(`Endpoint: ${text}`, 'info');
                return;
            }
            navigator.clipboard.writeText(text).then(() => {
                const orig = btn.innerHTML;
                btn.innerHTML = '✓ Copied!';
                btn.style.color = '#34d399';
                showToast(`Copied URL: ${text}`, 'success');
                setTimeout(() => {
                    btn.innerHTML = orig;
                    btn.style.color = '';
                }, 2000);
            }).catch(() => {
                showToast(`Copied URL: ${text}`, 'info');
            });
        }

        // Switch Right Column View: Module Endpoints vs Copilot Assistant
        function switchRightPanelView(view) {
            const endpointsView = document.getElementById('moduleEndpointsPanelView');
            const chatView = document.getElementById('copilotChatView');
            const btnEndpoints = document.getElementById('tabBtnEndpoints');
            const btnCopilot = document.getElementById('tabBtnCopilot');
            const title = document.getElementById('panelPrimaryTitle');
            const subtitle = document.getElementById('panelPrimarySubtitle');

            if (view === 'endpoints') {
                if (endpointsView) endpointsView.style.display = 'flex';
                if (chatView) chatView.style.display = 'none';
                if (btnEndpoints) btnEndpoints.classList.add('active');
                if (btnCopilot) btnCopilot.classList.remove('active');
                if (title) title.textContent = 'Module Endpoints & Live URLs';
                if (subtitle) subtitle.textContent = 'Government Portals, API Verification & Statutory Schemas';
            } else {
                if (endpointsView) endpointsView.style.display = 'none';
                if (chatView) chatView.style.display = 'flex';
                if (btnEndpoints) btnEndpoints.classList.remove('active');
                if (btnCopilot) btnCopilot.classList.add('active');
                if (title) title.textContent = 'GST Compliance Copilot';
                if (subtitle) subtitle.textContent = 'Real-Time NIC Diagnostics & Smart Patcher';
            }
        }

        // Quick Interactive GSTIN Live Tester
        async function runLiveGstinTest() {
            const input = document.getElementById('testGstinInput');
            const resultBox = document.getElementById('testGstinResult');
            if (!input || !resultBox) return;
            const gstin = input.value.trim().toUpperCase();
            if (!gstin) {
                showToast('Please enter a GSTIN to test', 'warning');
                return;
            }
            resultBox.style.display = 'block';
            resultBox.innerHTML = '<span style="color:#38bdf8;">⏳ Querying live GSTIN API...</span>';
            try {
                const res = await fetch(`/api/converter/verify-gstin/${encodeURIComponent(gstin)}`);
                const data = await res.json();
                if (data.is_live && data.trade_name) {
                    resultBox.innerHTML = `
                        <div style="color:#10b981; font-weight:700;">🟢 LIVE VERIFIED (GST Common Portal)</div>
                        <div style="color:#ffffff;">• Legal Name: <strong>${escapeHtml(data.legal_name || data.trade_name)}</strong></div>
                        <div style="color:#94a3b8;">• Trade Name: ${escapeHtml(data.trade_name)}</div>
                        <div style="color:#94a3b8;">• State: ${escapeHtml(data.state || '')} (Code ${escapeHtml(data.state_code || '')})</div>
                        <div style="color:#94a3b8;">• Status: <span style="color:#10b981;">${escapeHtml(data.status || 'Active')}</span> | Type: ${escapeHtml(data.taxpayer_type || 'Regular')}</div>
                    `;
                } else if (data.is_valid) {
                    resultBox.innerHTML = `
                        <div style="color:#10b981; font-weight:700;">🟢 Modulo-36 Checksum Valid</div>
                        <div style="color:#ffffff;">• State: ${escapeHtml(data.state || '')} (Code ${escapeHtml(data.state_code || '')})</div>
                        <div style="color:#94a3b8;">• Entity: ${escapeHtml(data.entity_type || 'Regular')}</div>
                    `;
                } else {
                    resultBox.innerHTML = `
                        <div style="color:#f43f5e; font-weight:700;">❌ Checksum / API Notice</div>
                        <div style="color:#fca5a5;">${escapeHtml(data.error || 'Invalid GSTIN')}</div>
                        ${data.corrected_gstin ? `<div style="color:#38bdf8;">• Suggested: <code>${escapeHtml(data.corrected_gstin)}</code></div>` : ''}
                    `;
                }
            } catch (err) {
                resultBox.innerHTML = `<span style="color:#f43f5e;">Error: ${escapeHtml(err.message)}</span>`;
            }
        }

        // Quick Interactive Vehicle Plate Tester
        async function runLiveVehicleTest() {
            const input = document.getElementById('testVehInput');
            const resultBox = document.getElementById('testVehResult');
            if (!input || !resultBox) return;
            const veh = input.value.trim().toUpperCase();
            if (!veh) {
                showToast('Please enter a vehicle plate number', 'warning');
                return;
            }
            resultBox.style.display = 'block';
            resultBox.innerHTML = '<span style="color:#38bdf8;">⏳ Verifying vehicle format &amp; MoRTH jurisdiction...</span>';
            try {
                const res = await fetch(`/api/converter/verify-vehicle/${encodeURIComponent(veh)}`);
                const data = await res.json();
                if (data.is_valid) {
                    resultBox.innerHTML = `
                        <div style="color:#fbbf24; font-weight:700;">🟡 MoRTH Statutory Validated (EWB Rule 138)</div>
                        <div style="color:#ffffff;">• Jurisdiction: <strong>${escapeHtml(data.rto_name || '')}</strong></div>
                        <div style="color:#94a3b8;">• State: ${escapeHtml(data.state || '')}</div>
                        <div style="color:#94a3b8;">• Series: ${escapeHtml(data.series_type || 'State RTO')}</div>
                        <div style="margin-top:4px;"><a href="${escapeHtml(data.carinfo_url || 'https://carinfo.app/rc-search')}" target="_blank" style="color:#38bdf8; text-decoration:underline;">View RC Details on CarInfo ↗</a></div>
                    `;
                } else {
                    resultBox.innerHTML = `
                        <div style="color:#f43f5e; font-weight:700;">❌ Invalid MoRTH Vehicle Plate</div>
                        <div style="color:#fca5a5;">${escapeHtml(data.error || 'Format invalid')}</div>
                    `;
                }
            } catch (err) {
                resultBox.innerHTML = `<span style="color:#f43f5e;">Error: ${escapeHtml(err.message)}</span>`;
            }
        }

        // Fetch Live Configured Endpoints from Server and dynamically sync UI
        async function loadConfiguredEndpoints() {
            try {
                const res = await fetch('/api/converter/endpoints');
                if (!res.ok) return;
                const data = await res.json();
                if (data && data.modules) {
                    const gstinMod = data.modules.find(m => m.module_id === 'gstin');
                    const vahanMod = data.modules.find(m => m.module_id === 'vahan');
                    if (gstinMod && document.getElementById('epGstinUrl')) {
                        document.getElementById('epGstinUrl').textContent = gstinMod.url;
                    }
                    if (vahanMod && document.getElementById('epVahanUrl')) {
                        document.getElementById('epVahanUrl').textContent = vahanMod.url;
                    }
                }
            } catch (e) {
                console.warn('Could not fetch live endpoints info:', e);
            }
        }

        // Format Markdown-like text to safe HTML
        function formatMarkdownReply(text) {
            if (!text) return '';
            let html = escapeHtml(text);
            // Clickable Links [title](url)
            html = html.replace(/\[(.*?)\]\((https?:\/\/[^\s\)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer" style="color:#38bdf8; text-decoration:underline; font-weight:600;">$1 ↗</a>');
            // Bold **text**
            html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
            // Italic *text*
            html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');
            // Inline code `code`
            html = html.replace(/`(.*?)`/g, '<code>$1</code>');
            // Bullet points
            html = html.replace(/^[•\-\*]\s+(.*)$/gm, '<div style="margin-left: 12px; margin-bottom: 4px;">• $1</div>');
            // Newlines
            html = html.replace(/\n\n/g, '<br><br>').replace(/\n/g, '<br>');
            return html;
        }


        // Submit message to Copilot
        async function handleCopilotSubmit(e) {
            if (e && e.preventDefault) e.preventDefault();
            const input = document.getElementById('copilotInputBox');
            const sendBtn = document.getElementById('copilotSendBtn');
            const feed = document.getElementById('copilotMessagesFeed');
            const message = (input.value || '').trim();

            if (!message) return;

            // 1. Append User Message
            const userMsgDiv = document.createElement('div');
            userMsgDiv.className = 'copilot-msg user';
            userMsgDiv.innerHTML = `<div class="msg-bubble">${escapeHtml(message)}</div>`;
            feed.appendChild(userMsgDiv);

            input.value = '';
            input.disabled = true;
            sendBtn.disabled = true;
            feed.scrollTop = feed.scrollHeight;

            // Add thinking indicator
            const typingDiv = document.createElement('div');
            typingDiv.className = 'copilot-msg bot';
            typingDiv.id = 'copilotTypingIndicator';
            typingDiv.innerHTML = `
                <div class="msg-bubble" style="color: var(--accent-cyan); display: flex; align-items: center; gap: 8px;">
                    <span class="pulse-dot" style="width: 8px; height: 8px; background: #38bdf8;"></span>
                    <span>Analyzing compliance rules & payload...</span>
                </div>
            `;
            feed.appendChild(typingDiv);
            feed.scrollTop = feed.scrollHeight;

            // 2. Prepare payload from active state or raw editor
            let currentPayload = currentLivePayload;
            if (!currentPayload) {
                try {
                    const rawEditorText = rawJsonEditor.value.trim();
                    if (rawEditorText) {
                        currentPayload = JSON.parse(rawEditorText);
                        initialDirtyPayloadStr = rawEditorText;
                    }
                } catch (err) {
                    currentPayload = null;
                }
            }

            try {
                const response = await fetch('/api/converter/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        message: message,
                        payload: currentPayload,
                        validation_report: currentValidationReport || null,
                        chat_history: copilotChatHistory
                    })
                });

                // Remove typing indicator
                const typingEl = document.getElementById('copilotTypingIndicator');
                if (typingEl) typingEl.remove();

                if (!response.ok) {
                    throw new Error(`Server returned HTTP ${response.status}`);
                }

                const data = await response.json();

                // 3. Render Assistant Reply
                const botMsgDiv = document.createElement('div');
                botMsgDiv.className = 'copilot-msg bot';

                let replyHtml = `<div class="msg-bubble">${formatMarkdownReply(data.reply)}</div>`;

                // Interactive Action Buttons inside Chat Bubble
                if (data.interactive_actions && data.interactive_actions.length > 0) {
                    const actionBtns = data.interactive_actions.map(act => 
                        `<button type="button" class="copilot-action-btn" onclick="sendCopilotQuickMessage('${escapeHtml(act)}')">${escapeHtml(act)}</button>`
                    ).join(' ');
                    replyHtml += `<div class="msg-action-bar">${actionBtns}</div>`;
                }

                if (data.patch_applied && data.patch_summary && data.patch_summary.length > 0) {
                    const patchTags = data.patch_summary.map(s => `<div>⚡ ${escapeHtml(s)}</div>`).join('');
                    replyHtml += `
                        <div class="msg-patch-banner">
                            <div>${patchTags}</div>
                        </div>
                    `;
                }

                botMsgDiv.innerHTML = replyHtml;
                feed.appendChild(botMsgDiv);
                feed.scrollTop = feed.scrollHeight;

                // 4. Update Chat History
                copilotChatHistory.push({ role: 'user', text: message });
                copilotChatHistory.push({ role: 'assistant', text: data.reply });

                // 5. Update Quick Pills
                if (data.quick_prompts) {
                    updateCopilotPills(data.quick_prompts);
                }

                // 6. If Patch was Applied: Automatically update the Live UI Screens!
                if (data.patch_applied && data.updated_payload) {
                    currentLivePayload = data.updated_payload;
                    if (!initialDirtyPayloadStr && rawJsonEditor.value.trim()) {
                        initialDirtyPayloadStr = rawJsonEditor.value.trim();
                    }

                    // Keep Customer Raw Dirty Input showing the DIRTY payload only!
                    // Do NOT overwrite rawJsonEditor or diffDirtyPane with clean/patched payload.
                    if (!rawJsonEditor.value.trim() && initialDirtyPayloadStr) {
                        rawJsonEditor.value = initialDirtyPayloadStr;
                    }
                    validateJsonInput();

                    // 6A. Synchronize Side-by-Side Diff Panes (Tab 2)
                    // Left Pane: Customer Raw Dirty Input ONLY!
                    // Right Pane: Clean Normalized Patched NIC Payload!
                    lastRawJsonStr = initialDirtyPayloadStr || rawJsonEditor.value;
                    lastCleanJsonStr = data.corrected_payload 
                        ? JSON.stringify(data.corrected_payload, null, 2) 
                        : JSON.stringify(data.updated_payload, null, 2);

                    if (typeof renderDiffPanes === 'function') {
                        renderDiffPanes(lastRawJsonStr, lastCleanJsonStr);
                    }

                    // 6B. Synchronize Validation Cards & Tab Error Counts (Tab 3)
                    if (data.validation_report) {
                        currentValidationReport = data.validation_report;
                        currentCorrectedPayload = data.corrected_payload || data.updated_payload;

                        // Render Cards
                        renderValidationCards(currentValidationReport);

                        // Update Status Badge on Copilot Header
                        updateCopilotHeaderStatus(currentValidationReport);

                        // Update Tab Counter Pills (Tab 1 Corrections & Tab 3 Errors)
                        const firstRes = (currentValidationReport.results || [])[0] || {};
                        const errCount = firstRes.error_count ?? (firstRes.errors || []).length;
                        const corrCount = firstRes.corrections_applied_count ?? (firstRes.corrections_applied || []).length;
                        const tabErrEl = document.getElementById('tabCountErrors');
                        if (tabErrEl) tabErrEl.textContent = errCount;
                        const tabCorrEl = document.getElementById('tabCountCorrections');
                        if (tabCorrEl) tabCorrEl.textContent = corrCount;
                    }

                    // 6C. Synchronize Terminal Summary Report (Tab 4)
                    if (data.summary_text) {
                        lastSummaryText = data.summary_text;
                        if (typeof renderTerminalSummary === 'function') {
                            renderTerminalSummary(data.summary_text);
                        }
                    }

                    // 6D. Synchronize Audit Records Table (Tab 1)
                    if (data.audit_records && Array.isArray(data.audit_records)) {
                        fullAuditRecords = data.audit_records;
                        if (typeof renderAuditTable === 'function') {
                            renderAuditTable(fullAuditRecords);
                        }
                    }

                    // 6E. Synchronize Executive KPIs & Financials
                    if (data.metrics && typeof renderExecutiveKPIs === 'function') {
                        renderExecutiveKPIs(data.metrics);
                    }

                    // 6F. Ensure Output Dashboard & KPI Sections are visible
                    const kpiSec = document.getElementById('kpiDashboardSection');
                    if (kpiSec) kpiSec.style.display = 'block';
                    const outSec = document.getElementById('outputDashboardSection');
                    if (outSec) outSec.style.display = 'block';

                    showToast('⚡ All screens & output tabs synchronized in real-time!', 'success');
                }

            } catch (err) {
                const typingEl = document.getElementById('copilotTypingIndicator');
                if (typingEl) typingEl.remove();

                const botMsgDiv = document.createElement('div');
                botMsgDiv.className = 'copilot-msg bot';
                botMsgDiv.innerHTML = `<div class="msg-bubble" style="color: #fca5a5;">⚠️ <strong>Error contacting Copilot:</strong> ${escapeHtml(err.message)}</div>`;
                feed.appendChild(botMsgDiv);
                feed.scrollTop = feed.scrollHeight;
            } finally {
                input.disabled = false;
                sendBtn.disabled = false;
                input.focus();
            }
        }
    