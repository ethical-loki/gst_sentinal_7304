import re
from pathlib import Path

def analyze():
    c_html = Path("frontend/converter.html").read_text(encoding="utf-8")
    i_html = Path("frontend/ingestion.html").read_text(encoding="utf-8")

    c_endpoints = set(re.findall(r"fetch\(['\"`](/api/[^'\"` ?]+)", c_html))
    i_endpoints = set(re.findall(r"fetch\(['\"`](/api/[^'\"` ?]+)", i_html))

    print("Converter endpoints called in frontend/converter.html:")
    for ep in sorted(c_endpoints):
        print("  ", ep)

    print("\nIngestion endpoints called in frontend/ingestion.html:")
    for ep in sorted(i_endpoints):
        print("  ", ep)

if __name__ == "__main__":
    analyze()
