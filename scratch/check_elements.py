import re

with open('frontend/ingestion.html', 'r', encoding='utf-8') as f:
    html = f.read()

script_idx = html.find('<script>')
script_part = html[script_idx:]

matches = re.findall(r'(?:const|let|var)\s+([a-zA-Z0-9_$]+)\s*=\s*document\.getElementById\([\'"]([^\'"]+)[\'"]\)', script_part)
print(f"Total getElementById assignments: {len(matches)}")

for var_name, elem_id in matches:
    pos = html.find(f'id="{elem_id}"')
    if pos == -1:
        pos = html.find(f"id='{elem_id}'")
    if pos == -1:
        print(f"MISSING IN HTML: {elem_id} (var {var_name})")
    elif pos > script_idx:
        print(f"AFTER SCRIPT: {elem_id} (var {var_name})")
