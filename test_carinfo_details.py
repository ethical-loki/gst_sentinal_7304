import urllib.request
import re

veh = "MH02CL0555"
url = f"https://www.carinfo.app/rc-details/{veh}"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
req = urllib.request.Request(url, headers=headers)
html = urllib.request.urlopen(req, timeout=8.0).read().decode("utf-8")

# Search for any script tags or vehicle info
scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
print(f"Scripts count: {len(scripts)}")
for idx, s in enumerate(scripts):
    if len(s) > 50 and ("vehicle" in s or "owner" in s or "rto" in s.lower() or "MH02" in s):
        print(f"Script {idx}:", s[:300])

# Search text in body
body_text = re.sub(r'<[^>]+>', ' ', html)
clean_text = ' '.join(body_text.split())
print("Body snippet:", clean_text[:600])
