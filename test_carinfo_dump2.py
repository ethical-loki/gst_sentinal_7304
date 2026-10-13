import urllib.request

url = "https://www.carinfo.app/_next/static/chunks/pages/rc-search-b24859c1ca55eae4.js"
headers = {"User-Agent": "Mozilla/5.0"}
content = urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=5.0).read().decode("utf-8")
print(content[3000:])
