import requests, json, sys

sys.stdout.reconfigure(encoding="utf-8")

test_cases = [
    # E-Way Bill Domain
    ("eway_bill", "What is the penalty for moving goods without an e-way bill?"),
    ("eway_bill", "What is the threshold limit for inter-state e-way bill generation?"),
    ("eway_bill", "What is the 15-day rule for Part-A slip?"),
    ("eway_bill", "When is an e-way bill blocked under Rule 138E?"),
    ("eway_bill", "What is the validity period of an e-way bill for regular cargo?"),
    
    # E-Invoice Domain
    ("e_invoice", "what is meant by e-invoice"),
    ("e_invoice", "What is the turnover threshold for mandatory e-invoicing?"),
    ("e_invoice", "Can an IRN be cancelled after 24 hours?"),
    ("e_invoice", "Are B2C invoices eligible for e-invoicing?"),
    ("e_invoice", "How long is the auth token valid for?"),
    ("e_invoice", "Can an IRN be cancelled if active e-way bill exists?"),

    # IMS Domain
    ("ims", "What is Invoice Management System (IMS)?"),
    ("ims", "What are the recipient actions in IMS?"),
    ("ims", "What happens if a buyer takes no action on an invoice in IMS?"),
    ("ims", "When is Pending status not allowed in IMS?"),
    ("ims", "Which taxpayers are excluded from IMS?")
]

passed = 0
failed = 0

print(f"\n--- RUNNING COMPREHENSIVE LIVE QA TEST SUITE ({len(test_cases)} CASES) ---\n")

for domain, question in test_cases:
    print(f"Domain: [{domain}] | Question: \"{question}\"")
    try:
        res = requests.post("http://127.0.0.1:8001/api/qa/ask", json={"question": question, "domain": domain}, timeout=30)
        data = res.json()
        status = data.get("status")
        score = data.get("score")
        model = data.get("payload", {}).get("model")
        answer = data.get("answer", "").strip()

        if status == "success" and answer and "Information not found" not in answer:
            passed += 1
            print(f"  [PASS] (Score: {score:.4f}, Model: {model})")
            first_line = answer.split("\n")[0]
            print(f"  Answer: {first_line[:120]}...\n")
        else:
            failed += 1
            print(f"  [FAIL] Status: {status}, Score: {score}")
            print(f"  Answer: {answer}\n")
    except Exception as e:
        failed += 1
        print(f"  [ERROR] {e}\n")

print(f"\nSUMMARY: Total: {len(test_cases)}, Passed: {passed}, Failed: {failed}, Accuracy: {passed / len(test_cases) * 100:.1f}%\n")

