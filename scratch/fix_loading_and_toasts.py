import re
import shutil

with open('frontend/ingestion.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Remove loadingOverlay and toastBox from the bottom (after </script>)
bottom_pattern = r'<!-- Loading Overlay -->\s*<div class="loading-overlay" id="loadingOverlay">[\s\S]*?<!-- Toast Notification -->\s*<div class="toast-notification" id="toastBox">[\s\S]*?</div>\s*</div>?'
# Let's be very precise about what was at the bottom:
pattern_bottom = r'<!-- Loading Overlay -->\s*<div class="loading-overlay" id="loadingOverlay">.*?</div>\s*</div>\s*<!-- Toast Notification -->\s*<div class="toast-notification" id="toastBox">.*?</div>\s*</div>'

# Check exact bottom content:
idx_loading = content.rfind('<!-- Loading Overlay -->')
if idx_loading != -1:
    idx_body_end = content.find('</body>', idx_loading)
    if idx_body_end != -1:
        bottom_elements = content[idx_loading:idx_body_end].strip()
        print("Found bottom elements to move:")
        print(bottom_elements[:150])
        content = content[:idx_loading] + content[idx_body_end:]

# Place before <script>
script_tag = '  <!-- JAVASCRIPT LOGIC -->\n  <script>'
replacement_before_script = '''  <!-- Loading Overlay -->
  <div class="loading-overlay" id="loadingOverlay">
      <div class="spinner-ring"></div>
      <div class="loading-text" id="loadingText">Processing GST Pipeline...</div>
  </div>

  <!-- Toast Notification -->
  <div class="toast-notification" id="toastBox">
      <span id="toastMessage">Operation successful!</span>
  </div>

  <!-- JAVASCRIPT LOGIC -->
  <script>'''

content = content.replace(script_tag, replacement_before_script)

# 2. Fix the first showLoading / hideLoading / showToast
old_first_utils = '''    // TOAST & LOADING UTILITIES
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
    }'''

new_first_utils = '''    // TOAST & LOADING UTILITIES
    function showLoading(text = 'Processing GST Sentinel Pipeline...') {
        const overlay = document.getElementById('loadingOverlay');
        const txt = document.getElementById('loadingText');
        if (txt) txt.textContent = text;
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
            box.className = `toast-notification show ${type === 'success' ? 'toast-success' : type === 'error' ? 'toast-error' : 'toast-info'}`;
            box.style.display = 'flex';
            setTimeout(() => {
                box.classList.remove('show');
                setTimeout(() => { if (box) box.style.display = 'none'; }, 300);
            }, 3500);
        }
    }'''

if old_first_utils in content:
    content = content.replace(old_first_utils, new_first_utils)
    print("Replaced first utils successfully.")
else:
    print("Could not find exact old_first_utils")

# 3. Remove lines declaring loadingOverlay / loadingText at top level
old_vars = '''        const loadingOverlay = document.getElementById('loadingOverlay');
        const loadingText = document.getElementById('loadingText');
        const toastBox = document.getElementById('toastBox');
        const toastMessage = document.getElementById('toastMessage');'''

if old_vars in content:
    content = content.replace(old_vars, '// loadingOverlay & toastBox are dynamically resolved')
    print("Removed redundant top-level vars.")
else:
    print("Could not find exact old_vars")

# 4. Fix second showToast / showLoading / hideLoading around line 7230
old_second_utils = '''        // Utility: Toast
        function showToast(msg, type = 'success') {
            const box = document.getElementById('toastBox');
            const messageEl = document.getElementById('toastMessage');
            if (messageEl) messageEl.textContent = msg;
            if (box) {
                box.className = `toast-notification show ${type === 'success' ? 'toast-success' : type === 'error' ? 'toast-error' : 'toast-info'}`;
                box.style.display = 'flex';
                setTimeout(() => {
                    box.classList.remove('show');
                    setTimeout(() => { if (box) box.style.display = 'none'; }, 300);
                }, 3500);
            }
        }

        // Utility: Loading
        function showLoading(msg = 'Processing GST Sentinel Pipeline...') {
            loadingText.textContent = msg;
            loadingOverlay.style.display = 'flex';
        }

        function hideLoading() {
            loadingOverlay.style.display = 'none';
        }'''

new_second_utils = '''        // Utility: Toast
        function showToast(msg, type = 'success') {
            const box = document.getElementById('toastBox');
            const messageEl = document.getElementById('toastMessage');
            if (messageEl) messageEl.textContent = msg;
            if (box) {
                box.className = `toast-notification show ${type === 'success' ? 'toast-success' : type === 'error' ? 'toast-error' : 'toast-info'}`;
                box.style.display = 'flex';
                setTimeout(() => {
                    box.classList.remove('show');
                    setTimeout(() => { if (box) box.style.display = 'none'; }, 300);
                }, 3500);
            }
        }

        // Utility: Loading
        function showLoading(msg = 'Processing GST Sentinel Pipeline...') {
            const overlay = document.getElementById('loadingOverlay');
            const txt = document.getElementById('loadingText');
            if (txt) txt.textContent = msg;
            if (overlay) overlay.style.display = 'flex';
        }

        function hideLoading() {
            const overlay = document.getElementById('loadingOverlay');
            if (overlay) overlay.style.display = 'none';
        }'''

if old_second_utils in content:
    content = content.replace(old_second_utils, new_second_utils)
    print("Replaced second utils successfully.")
else:
    print("Could not find exact old_second_utils")

with open('frontend/ingestion.html', 'w', encoding='utf-8') as f:
    f.write(content)

with open('static/ingestion.html', 'w', encoding='utf-8') as f:
    f.write(content)

with open('src/ui/ingestion.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("Saved and synced all 3 ingestion.html files!")
