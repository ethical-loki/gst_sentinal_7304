import re
from collections import Counter

with open('frontend/ingestion.html', 'r', encoding='utf-8') as f:
    text = f.read()

funcs = re.findall(r'function\s+([a-zA-Z0-9_]+)\s*\(', text)
counts = Counter(funcs)
duplicates = {k: v for k, v in counts.items() if v > 1}
print("Duplicate functions:", duplicates)

consts = re.findall(r'(?:const|let|var)\s+([a-zA-Z0-9_]+)\s*=', text)
const_counts = Counter(consts)
dup_consts = {k: v for k, v in const_counts.items() if v > 1}
print("Duplicate variables:", dup_consts)
