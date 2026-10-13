import urllib.request
import re

url = "https://www.carinfo.app/rto-vehicle-registration-detail"
headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
req = urllib.request.Request(url, headers=headers)
html = urllib.request.urlopen(req, timeout=8.0).read().decode("utf-8")

scripts = re.findall(r'src="([^"]+_next/static[^"]+)"', html)
print(f"Carinfo scripts count: {len(scripts)}")
for s in scripts:
    full_url = "https://www.carinfo.app" + s if s.startswith("/") else s
    try:
        content = urllib.request.urlopen(urllib.request.Request(full_url, headers=headers), timeout=5.0).read().decode("utf-8")
        if "rc" in content.lower() or "vehicle" in content.lower():
            endpoints = re.findall(r'\"(/[a-zA-Z0-9_/?&=.-]+(?:search|vehicle|rc|rto)[a-zA-Z0-9_/?&=.-]*)\"', content, re.IGNORECASE)
            if endpoints:
                print("Endpoints in", s[-30:], ":", set(endpoints))
            api_calls = re.findall(r'(https?://[a-zA-Z0-9.-]+/[^\s\"\'\`]+)', content)
            api_matches = [m for m in api_calls if "api" in m or "carinfo" in m or "rc" in m]
            if api_matches:
                print("API matches in", s[-30:], ":", set(api_matches[:5]))
    except Exception as e:
        pass
