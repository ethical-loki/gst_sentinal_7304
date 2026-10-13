import urllib.request
import re

url = "https://www.carinfo.app/_next/static/chunks/pages/rc-search-b24859c1ca55eae4.js"
headers = {"User-Agent": "Mozilla/5.0"}
content = urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=5.0).read().decode("utf-8")

# Search for fetch, axios, post
print("Length:", len(content))
calls = re.findall(r'(?:fetch|axios|get|post)\([^\)]+\)', content)
print("Calls:", calls[:10])

# Search for strings containing api or url
for match in re.finditer(r'https?://[a-zA-Z0-9.-]+/[^\s\"\'\`]+', content):
    print("Full URL:", match.group(0))

for match in re.finditer(r'\"(/[a-zA-Z0-9_/?&=.-]+)\"', content):
    val = match.group(1)
    if "api" in val or "rc" in val or "search" in val:
        print("API string:", val)
