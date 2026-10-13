import urllib.request
import re

url = "https://cleartax.in/frontier/_next/static/chunks/pages/cleartax.in/gst-number-search/%5BspecificGstin%5D-e1734810e0fb3f4b.js"
headers = {"User-Agent": "Mozilla/5.0"}
content = urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=5.0).read().decode("utf-8")

# Search for api or fetch or post
print("Length:", len(content))
for match in re.finditer(r'(https?://[^\s\"\'\`]+)', content):
    print("URL match:", match.group(0))

for match in re.finditer(r'(/api/[^\s\"\'\`]+)', content):
    print("API match:", match.group(0))

# Search for how TATA or fields are displayed: "lgnm", "legalName", "tradeName"
fields = ["lgnm", "tradeNam", "pradr", "bno", "flno", "st", "dst", "pin", "ctb", "sts"]
for f in fields:
    if f in content:
        print("Found field:", f)
        idx = content.find(f)
        print("Snippet around", f, ":", content[max(0, idx-100):min(len(content), idx+100)])
        break
