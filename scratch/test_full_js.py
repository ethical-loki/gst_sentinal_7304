import os
import subprocess

with open('frontend/ingestion.html', 'r', encoding='utf-8') as f:
    text = f.read()

import re
script_match = re.search(r'<script>(.*?)</script>', text, re.DOTALL)
js_code = script_match.group(1)

with open('scratch/full_ingestion_script.js', 'w', encoding='utf-8') as f:
    f.write(js_code)

# Check syntax
res = subprocess.run(['node', '--check', 'scratch/full_ingestion_script.js'], capture_output=True, text=True)
print("Node syntax check code:", res.returncode)
if res.stderr:
    print("Node syntax check errors:\n", res.stderr)
else:
    print("Zero syntax errors in JS!")
