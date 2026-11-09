import urllib.request
import json

url = "http://127.0.0.1:8000/api/v1/hsn-intelligence/unified-multi-model-audit"
payload = {
    "items": [
        "Microprocessor / Microcontroller Integrated Circuits",
        "Unvulcanised Natural Rubber Sheets",
        "Natural Honey",
        "Mounted Brake Linings / Brake Pads for Passenger Cars",
        "Whole Roasted Coffee Beans",
        "Lithium-ion Battery Pack"
    ]
}

req = urllib.request.Request(
    url,
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"}
)

with urllib.request.urlopen(req, timeout=90) as resp:
    data = json.loads(resp.read().decode("utf-8"))
    print(f"Total: {data['total_items']} | Latency: {data['batch_latency_ms']} ms")
    print("-" * 100)
    for r in data["results"]:
        print(
            f"{r['item_description']:55s} | "
            f"Day5: {r['day5_hsn']:10s} | "
            f"DeepSeek: {r['deepseek_hsn']:10s} | "
            f"RAG: {r['rag_hsn']:10s} | "
            f"FINAL: {r['final_hsn']:10s} (GST {r['final_gst_rate']}%)"
        )
