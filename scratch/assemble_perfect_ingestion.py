import re
import subprocess

# Read HTML file
with open('frontend/ingestion.html', 'r', encoding='utf-8') as f:
    html_content = f.read()

# Separate HTML before <script> and after </script>
script_start = html_content.find('<script>')
script_end = html_content.find('</script>')

if script_start == -1 or script_end == -1:
    print("Script tags not found!")
    exit(1)

html_before = html_content[:script_start + len('<script>\n')]
html_after = html_content[script_end:]

# Ensure loadingOverlay and toastBox exist in html_before or html_after
if 'id="loadingOverlay"' not in html_content:
    overlay_html = """
    <!-- Loading Overlay -->
    <div class="loading-overlay" id="loadingOverlay" style="display:none;">
        <div class="spinner-ring"></div>
        <div class="loading-text" id="loadingText">Processing GST Pipeline...</div>
    </div>

    <!-- Toast Notification -->
    <div class="toast-notification" id="toastBox" style="display:none;">
        <span id="toastMessage">Operation successful!</span>
    </div>
"""
    html_after = overlay_html + html_after

# Now let's extract the clean Lakehouse functions from scratch/temp_ingestion.js
with open('scratch/temp_ingestion.js', 'r', encoding='utf-8') as f:
    temp_js = f.read()

# Extract state variables for Lakehouse
# rawFiles, currentSelectedRawFile, etc.
state_start = temp_js.find('let rawFiles = [];')
if state_start == -1:
    state_start = temp_js.find('let lastValidationReport = null;')

# Extract from fetchRawFiles to the end of exportCurrentViewCSV
raw_fn_start = temp_js.find('async function fetchRawFiles()')
csv_fn_idx = temp_js.find('function exportCurrentViewCSV()')
csv_click_idx = temp_js.find('a.click();', csv_fn_idx)
raw_fn_end = temp_js.find('}', csv_click_idx) + 1

lakehouse_tab1 = temp_js[raw_fn_start:raw_fn_end]

# Extract Tab 3 (Lakehouse Master) and Tab 4 (Audit Trail)
tab3_start = temp_js.find('async function fetchLakehouseMaster()')
tab4_end = temp_js.find('// =========================================================================\n        // CONVERTER MODULE CORE LOGIC')
lakehouse_tab3_4 = temp_js[tab3_start:tab4_end]

# Extract Converter Script from scratch/full_conv_script.js
with open('scratch/full_conv_script.js', 'r', encoding='utf-8') as f:
    conv_script = f.read()

# Remove duplicate window.addEventListener('DOMContentLoaded' inside conv_script
conv_script = re.sub(
    r"window\.addEventListener\('DOMContentLoaded',\s*async\s*\(\)\s*=>\s*\{.*?\}\);",
    "// Initialized in unified DOMContentLoaded below",
    conv_script,
    flags=re.DOTALL
)

# Build the complete, unified, perfectly working JavaScript block
perfect_script = f"""
    // =========================================================================
    // GLOBAL APPLICATION STATE (LAKEHOUSE + CONVERTER WORKBENCH)
    // =========================================================================
    let rawFiles = [];
    let currentSelectedRawFile = null;
    let rawPage = 1;
    let rawPageSize = 25;
    let rawTotalRows = 0;
    let rawTotalPages = 1;
    let rawSearch = "";
    let rawSortBy = null;
    let rawSortDir = "asc";

    let lakehousePage = 1;
    let lakehousePageSize = 25;
    let lakehouseSearch = "";

    let auditPage = 1;
    let auditPageSize = 25;
    let auditSearch = "";
    let auditCategory = "";

    // TOAST & LOADING UTILITIES
    function showLoading(text) {{
        const overlay = document.getElementById('loadingOverlay');
        const txt = document.getElementById('loadingText');
        if (txt) txt.textContent = text || 'Processing...';
        if (overlay) overlay.style.display = 'flex';
    }}

    function hideLoading() {{
        const overlay = document.getElementById('loadingOverlay');
        if (overlay) overlay.style.display = 'none';
    }}

    function showToast(message, type = 'info') {{
        const box = document.getElementById('toastBox');
        const msg = document.getElementById('toastMessage');
        if (msg) msg.textContent = message;
        if (box) {{
            box.className = `toast-notification show ${{type === 'success' ? 'toast-success' : type === 'error' ? 'toast-error' : ''}}`;
            box.style.display = 'flex';
            setTimeout(() => {{
                box.classList.remove('show');
                box.style.display = 'none';
            }}, 3500);
        }}
        const container = document.getElementById('toastContainer');
        if (container) {{
            const toast = document.createElement('div');
            toast.className = `toast ${{type}}`;
            const icon = type === 'success' ? 'fa-circle-check' : type === 'error' ? 'fa-circle-exclamation' : 'fa-circle-info';
            toast.innerHTML = `<i class="fa-solid ${{icon}}"></i> <span>${{message}}</span>`;
            container.appendChild(toast);
            setTimeout(() => {{
                toast.style.opacity = '0';
                setTimeout(() => toast.remove(), 300);
            }}, 3500);
        }}
    }}

    // HORIZONTAL SCROLL HELPER
    function scrollTableHorizontally(wrapperId, delta) {{
        const el = document.getElementById(wrapperId);
        if (el) {{
            el.scrollBy({{ left: delta, behavior: 'smooth' }});
        }}
    }}

    // MAIN TAB NAVIGATION
    function switchMainTab(tabId) {{
        document.querySelectorAll('.nav-tab-btn').forEach(btn => btn.classList.remove('active'));
        document.querySelectorAll('.tab-panel').forEach(panel => panel.classList.remove('active'));

        if (tabId === 'explorer') {{
            document.getElementById('tabBtnExplorer')?.classList.add('active');
            document.getElementById('tabPanelExplorer')?.classList.add('active');
        }} else if (tabId === 'validator') {{
            document.getElementById('tabBtnValidator')?.classList.add('active');
            document.getElementById('tabPanelValidator')?.classList.add('active');
        }} else if (tabId === 'lakehouse') {{
            document.getElementById('tabBtnLakehouse')?.classList.add('active');
            document.getElementById('tabPanelLakehouse')?.classList.add('active');
            fetchLakehouseMaster();
        }} else if (tabId === 'audit') {{
            document.getElementById('tabBtnAudit')?.classList.add('active');
            document.getElementById('tabPanelAudit')?.classList.add('active');
            fetchAuditTrail();
        }}
    }}

    // DASHBOARD TOP KPI STATS
    async function fetchDashboardStats() {{
        try {{
            const res = await fetch('/api/ingestion/stats');
            if (!res.ok) return;
            const data = await res.json();
            if (document.getElementById('kpiRawRows')) document.getElementById('kpiRawRows').innerText = Number(data.raw_total_rows).toLocaleString();
            if (document.getElementById('kpiRawFiles')) document.getElementById('kpiRawFiles').innerText = data.raw_files_count;
            if (document.getElementById('kpiLakehouseRows')) document.getElementById('kpiLakehouseRows').innerText = Number(data.lakehouse_records).toLocaleString();
            if (document.getElementById('kpiAuditFixes')) document.getElementById('kpiAuditFixes').innerText = Number(data.audit_fixes_count).toLocaleString();
            if (document.getElementById('kpiMasters')) document.getElementById('kpiMasters').innerText = `${{data.supported_code_masters}} States`;
        }} catch (err) {{
            console.error('Error fetching dashboard stats:', err);
        }}
    }}

    // ========================================================
    // TAB 1: RAW DATA LAKE EXPLORER
    // ========================================================
{lakehouse_tab1}

    // ========================================================
    // TAB 3: PROCESSED LAKEHOUSE MASTER & TAB 4: AUDIT TRAIL
    // ========================================================
{lakehouse_tab3_4}

    function downloadArtifact(type) {{
        const url = `/api/ingestion/download/${{type}}`;
        window.open(url, '_blank');
        showToast(`Downloading ${{type}} artifact...`, 'info');
    }}

    // ========================================================
    // TAB 2: INGESTION WORKBENCH & CONVERTER PIPELINE (FROM CONVERTER)
    // ========================================================
{conv_script}

    // Override / connect persistLivePayload to Lakehouse
    async function persistLivePayload() {{
        const rawEditorText = rawJsonEditor ? rawJsonEditor.value.trim() : '';
        if (!rawEditorText) {{
            showToast('Please enter or generate a payload to persist', 'error');
            return;
        }}
        let parsedPayload;
        try {{
            parsedPayload = JSON.parse(rawEditorText);
        }} catch (e) {{
            showToast('Invalid JSON syntax: ' + e.message, 'error');
            return;
        }}

        showLoading('Persisting to Parquet Lakehouse & updating master tables...');
        try {{
            const res = await fetch('/api/ingestion/persist', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify(parsedPayload)
            }});

            if (!res.ok) {{
                const err = await res.json();
                throw new Error(err.detail || 'Persistence failed');
            }}

            const data = await res.json();
            showToast(`Persisted invoice ${{data.invoice_number}} to Parquet lakehouse (+${{data.parquet_row_count}} rows)`, 'success');
            fetchDashboardStats();
            fetchLakehouseMaster();
            fetchAuditTrail();
        }} catch (err) {{
            showToast(err.message, 'error');
        }} finally {{
            hideLoading();
        }}
    }}

    // Unified DOMContentLoaded Initialization
    document.addEventListener('DOMContentLoaded', async () => {{
        fetchDashboardStats();
        fetchRawFiles();
        fetchLakehouseMaster();
        fetchAuditTrail();
        if (typeof initSplitResizer === 'function') initSplitResizer();
        const savedLayout = localStorage.getItem('copilot_layout_mode') || 'auto';
        if (typeof setCopilotLayout === 'function') setCopilotLayout(savedLayout);
        if (typeof loadConfiguredEndpoints === 'function') await loadConfiguredEndpoints();
        if (typeof handleGenerateRandom === 'function') await handleGenerateRandom();
    }});
"""

# Write out new full HTML
new_full_html = html_before + perfect_script + '\n    ' + html_after

with open('frontend/ingestion.html', 'w', encoding='utf-8') as f:
    f.write(new_full_html)

with open('static/ingestion.html', 'w', encoding='utf-8') as f:
    f.write(new_full_html)

with open('src/ui/ingestion.html', 'w', encoding='utf-8') as f:
    f.write(new_full_html)

print("Ingestion HTML successfully re-assembled and synced!")
