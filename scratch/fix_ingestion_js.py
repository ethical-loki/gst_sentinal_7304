import re

with open('frontend/ingestion.html', 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Add loadingOverlay and toastBox if missing
if 'id="loadingOverlay"' not in text:
    overlay_html = """
    <!-- Loading Overlay -->
    <div class="loading-overlay" id="loadingOverlay">
        <div class="spinner-ring"></div>
        <div class="loading-text" id="loadingText">Processing GST Pipeline...</div>
    </div>

    <!-- Toast Notification -->
    <div class="toast-notification" id="toastBox">
        <span id="toastMessage">Operation successful!</span>
    </div>
"""
    text = text.replace('</body>', overlay_html + '\n</body>')

# 2. Find the obsolete block between Tab 1 raw files explorer and Tab 3 Lakehouse master
# Starts at "function switchResultSubTab" or "async function loadSamplePayload"
old_start_str = "    async function loadSamplePayload(index) {"
old_end_str = "    // ========================================================\n    // TAB 3: PROCESSED LAKEHOUSE MASTER"

start_idx = text.find(old_start_str)
end_idx = text.find(old_end_str)

if start_idx != -1 and end_idx != -1:
    print(f"Removing obsolete Tab 2 functions from index {start_idx} to {end_idx} ({end_idx - start_idx} chars)")
    # Also check if there's any function right before loadSamplePayload that is obsolete (like mode switching for old tab 2)
    # Check lines right before
    prefix = text[:start_idx]
    # Let's find "function selectCustomerMode" or similar
    mode_switch_old = prefix.rfind("function selectCustomerMode")
    if mode_switch_old != -1:
        start_idx = mode_switch_old
    text = text[:start_idx] + text[end_idx:]

# 3. Fix DOMContentLoaded
# Remove old DOMContentLoaded that calls loadSamplePayload(0)
old_dcl = """    // INITIALIZATION
    document.addEventListener("DOMContentLoaded", () => {
      fetchDashboardStats();
      fetchRawFiles();
      loadSamplePayload(0);
      fetchLakehouseMaster();
      fetchAuditTrail();
    });"""

new_dcl = """    // INITIALIZATION
    document.addEventListener("DOMContentLoaded", async () => {
      fetchDashboardStats();
      fetchRawFiles();
      fetchLakehouseMaster();
      fetchAuditTrail();
      if (typeof initSplitResizer === 'function') initSplitResizer();
      const savedLayout = localStorage.getItem('copilot_layout_mode') || 'auto';
      if (typeof setCopilotLayout === 'function') setCopilotLayout(savedLayout);
      if (typeof loadConfiguredEndpoints === 'function') await loadConfiguredEndpoints();
      if (typeof handleGenerateRandom === 'function') await handleGenerateRandom();
    });"""

if old_dcl in text:
    text = text.replace(old_dcl, new_dcl)
    print("Replaced old DOMContentLoaded with unified DOMContentLoaded")
else:
    # Try flexible replacement
    text = re.sub(
        r'document\.addEventListener\("DOMContentLoaded",\s*\(\)\s*=>\s*\{.*?loadSamplePayload\(0\);.*?\}\);',
        new_dcl,
        text,
        flags=re.DOTALL
    )
    print("Applied regex replacement for DOMContentLoaded")

# Remove the second DOMContentLoaded window listener around line 6728 so it's not run twice
second_dcl = """        // Initialize on page load
        window.addEventListener('DOMContentLoaded', async () => {
            initSplitResizer();
            const savedLayout = localStorage.getItem('copilot_layout_mode') || 'auto';
            setCopilotLayout(savedLayout);
            // Fetch live API module endpoint configurations
            await loadConfiguredEndpoints();
            // Load initial random batch so the user has immediate data to explore
            await handleGenerateRandom();
        });"""

if second_dcl in text:
    text = text.replace(second_dcl, "// Page initialized in unified DOMContentLoaded above")
    print("Cleaned up redundant second DOMContentLoaded listener")

# 4. Make showLoading, hideLoading, and showToast ultra-safe
safe_loading_toast = """
        // Safe UI Notification & Loading Utilities
        function showLoading(text) {
            const overlay = document.getElementById('loadingOverlay');
            const txt = document.getElementById('loadingText');
            if (txt) txt.textContent = text || 'Processing...';
            if (overlay) overlay.style.display = 'flex';
        }

        function hideLoading() {
            const overlay = document.getElementById('loadingOverlay');
            if (overlay) overlay.style.display = 'none';
        }

        function showToast(message, type = 'info') {
            const box = document.getElementById('toastBox');
            const msg = document.getElementById('toastMessage');
            if (msg) msg.textContent = message;
            if (box) {
                box.className = `toast-notification show ${type === 'success' ? 'toast-success' : type === 'error' ? 'toast-error' : ''}`;
                box.style.display = 'flex';
                setTimeout(() => {
                    box.classList.remove('show');
                    box.style.display = 'none';
                }, 3500);
            }
            const container = document.getElementById('toastContainer');
            if (container) {
                const toast = document.createElement('div');
                toast.className = `toast ${type}`;
                const icon = type === 'success' ? 'fa-circle-check' : type === 'error' ? 'fa-circle-exclamation' : 'fa-circle-info';
                toast.innerHTML = `<i class="fa-solid ${icon}"></i> <span>${message}</span>`;
                container.appendChild(toast);
                setTimeout(() => {
                    toast.style.opacity = '0';
                    setTimeout(() => toast.remove(), 300);
                }, 3500);
            }
        }
"""

# Replace showToast definitions with safe_loading_toast
# Find any existing function showToast and replace
text = re.sub(
    r'function showToast\(message, type = [^\)]*\)\s*\{.*?setTimeout\(\(\) => toast\.remove\(\), 300\);\s*\}, 3500\);\s*\}',
    safe_loading_toast,
    text,
    flags=re.DOTALL
)

# And in converter script section, ensure showLoading and hideLoading use the safe versions
text = re.sub(
    r'function showLoading\(text\)\s*\{.*?loadingOverlay\.style\.display = [\'"]flex[\'"];\s*\}',
    '// showLoading defined in safe utilities above',
    text,
    flags=re.DOTALL
)

text = re.sub(
    r'function hideLoading\(\)\s*\{.*?loadingOverlay\.style\.display = [\'"]none[\'"];\s*\}',
    '// hideLoading defined in safe utilities above',
    text,
    flags=re.DOTALL
)

with open('frontend/ingestion.html', 'w', encoding='utf-8') as f:
    f.write(text)

with open('static/ingestion.html', 'w', encoding='utf-8') as f:
    f.write(text)

import os
if os.path.exists('src/ui/ingestion.html'):
    with open('src/ui/ingestion.html', 'w', encoding='utf-8') as f:
        f.write(text)

print("Ingestion HTML repaired and synced successfully!")
