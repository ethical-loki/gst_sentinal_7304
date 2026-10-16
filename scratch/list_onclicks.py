import re

with open('frontend/ingestion.html', 'r', encoding='utf-8') as f:
    text = f.read()

onclicks = set(re.findall(r'onclick=["\']([^"\']+)["\']', text))
print("--- ALL ONCLICK HANDLERS ---")
for oc in sorted(onclicks):
    # extract function name
    fn_name = oc.split('(')[0].strip()
    # check if defined in JS
    is_defined = f"function {fn_name}" in text or f"{fn_name} =" in text or f"const {fn_name}" in text
    print(f"{oc} -> function '{fn_name}' exists? {is_defined}")
