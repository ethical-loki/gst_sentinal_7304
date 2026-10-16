import re

with open('frontend/ingestion.html', 'r', encoding='utf-8') as f:
    text = f.read()

matches = re.findall(r"fetch\(['\"]([^'\"]+)['\"]", text)
print("Endpoints fetched in ingestion.html:")
for ep in sorted(set(matches)):
    print(" -", ep)
