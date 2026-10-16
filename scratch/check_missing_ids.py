import re

with open('frontend/ingestion.html', 'r', encoding='utf-8') as f:
    text = f.read()

# Find HTML part and JS part
script_match = re.search(r'<script>(.*?)</script>', text, re.DOTALL)
if not script_match:
    print("No script tag found!")
    exit(1)

html_part = text[:script_match.start()] + text[script_match.end():]
js_part = script_match.group(1)

# Find all getElementById in JS
get_el_ids = set(re.findall(r'document\.getElementById\([\'"]([^\'"]+)[\'"]\)', js_part))

# Find all ids in HTML
html_ids = set(re.findall(r'\bid=[\'"]([^\'"]+)[\'"]', html_part))

missing_ids = get_el_ids - html_ids
print(f"Total getElementById queries: {len(get_el_ids)}")
print(f"Total HTML IDs: {len(html_ids)}")
print("--- MISSING IDS ACCESSED IN JS ---")
for mid in sorted(missing_ids):
    print(mid)
