import urllib.request
import re

url = "https://cleartax.in/frontier/_next/static/chunks/pages/cleartax.in/gst-number-search/%5BspecificGstin%5D-e1734810e0fb3f4b.js"
headers = {"User-Agent": "Mozilla/5.0"}
content = urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=5.0).read().decode("utf-8")

for m in re.finditer(r'getGstinData', content):
    idx = m.start()
    print("--- getGstinData context ---")
    print(content[max(0, idx-200):min(len(content), idx+300)])
