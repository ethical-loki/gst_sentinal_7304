import urllib.request
import json

req = urllib.request.Request('http://localhost:8000/api/ingestion/sample')
with urllib.request.urlopen(req) as response:
    sample = json.loads(response.read().decode())

chat_payload = {
    "message": "Why did my invoice fail?",
    "payload": sample
}

req_chat = urllib.request.Request(
    'http://localhost:8000/api/ingestion/chat',
    data=json.dumps(chat_payload).encode('utf-8'),
    headers={'Content-Type': 'application/json'}
)

with urllib.request.urlopen(req_chat) as response:
    data = json.loads(response.read().decode())
    print("STATUS CODE:", response.status)
    print("REPLY:\n", data.get("reply"))
    print("VALIDATION REPORT ERRORS:", len(data.get("validation_report", {}).get("results", [{}])[0].get("errors", [])))
