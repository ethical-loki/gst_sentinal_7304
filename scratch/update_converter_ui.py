import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def update_file(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Add updateCopilotGkStatus after updateCopilotHsnCalc
    gk_func = '''
        // Day 06 Safety Gatekeeper status updater for inline HSN box
        function updateCopilotGkStatus(input) {
            const bar = input.closest('.copilot-hsn-pricing-bar');
            if (!bar) return;
            const val = (input.value || '').trim();
            const pill = bar.querySelector('.copilot-gk-pill');
            const factor = bar.querySelector('.copilot-gk-factor');
            if (!pill) return;
            if (val.startsWith('85') && val.length >= 4) {
                pill.style.background = 'rgba(16, 185, 129, 0.15)';
                pill.style.borderColor = 'rgba(16, 185, 129, 0.4)';
                pill.style.color = '#34d399';
                pill.innerHTML = '🟢 Safe to Auto-File (2.7% Risk)';
                if (factor) factor.textContent = 'Tariff Ch. 85 (Electric Motors) aligned with statutory benchmark.';
            } else if (val.startsWith('84')) {
                pill.style.background = 'rgba(239, 68, 68, 0.15)';
                pill.style.borderColor = 'rgba(239, 68, 68, 0.4)';
                pill.style.color = '#f87171';
                pill.innerHTML = '🔴 Blocked / High Risk (73.3% Risk)';
                if (factor) factor.textContent = 'Chapter mismatch: Vendor entered Ch. 84 vs Official Tariff Ch. 85 (Motors).';
            } else if (val.length < 4) {
                pill.style.background = 'rgba(245, 158, 11, 0.15)';
                pill.style.borderColor = 'rgba(245, 158, 11, 0.4)';
                pill.style.color = '#fbbf24';
                pill.innerHTML = '🟡 Review Recommended (38.5% Risk)';
                if (factor) factor.textContent = 'Incomplete tariff code (< 4 digits required by NIC statutory mandate).';
            } else {
                pill.style.background = 'rgba(245, 158, 11, 0.15)';
                pill.style.borderColor = 'rgba(245, 158, 11, 0.4)';
                pill.style.color = '#fbbf24';
                pill.innerHTML = '🟡 Review Recommended (24.0% Risk)';
                if (factor) factor.textContent = 'Tariff code diverges from statutory benchmark.';
            }
        }
'''
    if "function updateCopilotGkStatus" not in content:
        target_calc = "function submitCopilotHsnInput"
        if target_calc in content:
            content = content.replace(target_calc, gk_func + "\n        " + target_calc, 1)
            print(f"[{path.name}] Inserted updateCopilotGkStatus!")

    # 2. Update copilot-hsn-pricing-bar header with Gatekeeper Pill
    old_header = '<span style="font-size: 0.82rem; font-weight: 700; color: #38bdf8;">📦 Product: <span style="color: #f1f5f9; font-weight: 600;">${prdName}</span></span>'
    new_header = '''<div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                                <span style="font-size: 0.82rem; font-weight: 700; color: #38bdf8;">📦 Product: <span style="color: #f1f5f9; font-weight: 600;">${prdName}</span></span>
                                <span class="copilot-gk-pill" style="display: inline-flex; align-items: center; gap: 4px; padding: 2px 8px; border-radius: 12px; font-size: 0.70rem; font-weight: 700; background: rgba(16, 185, 129, 0.15); border: 1px solid rgba(16, 185, 129, 0.4); color: #34d399;">
                                    🟢 Safe to Auto-File (2.7% Risk)
                                </span>
                            </div>'''
    if old_header in content:
        content = content.replace(old_header, new_header, 1)
        print(f"[{path.name}] Updated pricing bar header with GK Pill!")

    # 3. Add oninput="updateCopilotGkStatus(this)" to HSN input
    old_hsn = 'data-field="hsn" class="copilot-inline-hsn-input" placeholder="e.g. 85011013"'
    new_hsn = 'data-field="hsn" class="copilot-inline-hsn-input" placeholder="e.g. 85011013" oninput="updateCopilotGkStatus(this)"'
    if old_hsn in content and 'oninput="updateCopilotGkStatus(this)"' not in content:
        content = content.replace(old_hsn, new_hsn, 1)
        print(f"[{path.name}] Added oninput to HSN input!")

    # 4. Add Gatekeeper Audit row before closing of copilot-hsn-pricing-bar
    old_audit_tail = '''                            <div style="display: flex; align-items: flex-end; padding-top: 14px; gap: 6px;">
                                <button type="button" class="copilot-action-btn" onclick="submitCopilotHsnInput(this)" style="background: linear-gradient(135deg, #0ea5e9, #6366f1); color: #fff; border: none; font-weight: 700; padding: 6px 14px; border-radius: 6px; cursor: pointer; white-space: nowrap;">✨ Apply & Recalculate Tax</button>
                                <button type="button" class="copilot-action-btn" onclick="sendCopilotQuickMessage('Fix HSN from product description')" style="background: rgba(192, 132, 252, 0.2); border: 1px solid #c084fc; color: #e879f9; font-weight: 600; padding: 6px 12px; border-radius: 6px; cursor: pointer; white-space: nowrap;">⚡ ML Lookup</button>
                            </div>
                        </div>'''
    
    new_audit_tail = '''                            <div style="display: flex; align-items: flex-end; padding-top: 14px; gap: 6px;">
                                <button type="button" class="copilot-action-btn" onclick="submitCopilotHsnInput(this)" style="background: linear-gradient(135deg, #0ea5e9, #6366f1); color: #fff; border: none; font-weight: 700; padding: 6px 14px; border-radius: 6px; cursor: pointer; white-space: nowrap;">✨ Apply & Recalculate Tax</button>
                                <button type="button" class="copilot-action-btn" onclick="sendCopilotQuickMessage('Fix HSN from product description')" style="background: rgba(192, 132, 252, 0.2); border: 1px solid #c084fc; color: #e879f9; font-weight: 600; padding: 6px 12px; border-radius: 6px; cursor: pointer; white-space: nowrap;">⚡ ML Lookup</button>
                            </div>
                        </div>
                        <div style="display: flex; align-items: center; gap: 6px; font-size: 0.72rem; color: #94a3b8; margin-top: 2px;">
                            <span style="color: #818cf8; font-weight: 700;">🛡️ Gatekeeper Audit:</span>
                            <span class="copilot-gk-factor">Tariff Ch. 85 (Electric Motors) aligned with statutory benchmark.</span>
                        </div>'''
    if old_audit_tail in content and '🛡️ Gatekeeper Audit:' not in content:
        content = content.replace(old_audit_tail, new_audit_tail, 1)
        print(f"[{path.name}] Added Gatekeeper Audit line!")

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[{path.name}] Saved successfully.")

update_file(ROOT / "frontend" / "converter.html")
update_file(ROOT / "static" / "converter.html")
print("All files updated!")
