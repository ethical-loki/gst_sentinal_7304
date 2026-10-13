import urllib.request
import re

url = "https://www.carinfo.app/rc-search"
headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
req = urllib.request.Request(url, headers=headers)
html = urllib.request.urlopen(req, timeout=8.0).read().decode("utf-8")

scripts = re.findall(r'src="([^"]+_next/static[^"]+)"', html)
print(f"Carinfo rc-search scripts: {len(scripts)}")
for s in scripts:
    if "rc-search" in s:
        print("Found rc-search chunk:", s)
        full_url = "https://www.carinfo.app" + s if s.startswith("/") else s
        content = urllib.request.urlopen(urllib.request.Request(full_url, headers=headers), timeout=5.0).read().decode("utf-8")
        # search for api endpoints
        apis = re.findall(r'\"(/[a-zA-Z0-9_/?&=.-]+)\"', content)
        print("Routes:", [a for a in apis if "api" in a or "rc" in a or "search" in a or "vehicle" in a][:10])
        post_urls = re.findall(r'(https?://[^\s\"\'\`]+)', content)
        print("Urls:", [u for u in post_urls if "api" in u or "carinfo" in u][:5])
