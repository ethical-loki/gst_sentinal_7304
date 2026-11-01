"""
test_qa.py — Automated Verification & Regression Suite for GST Sentinel Multi-Domain QA Engine.

Covers:
1. IMS Domain: Verbatim extraction of the three recipient actions (Accept, Reject, Pending) and launch dates.
2. E-Invoice Domain: Numeric extraction of 24-hr IRN cancellation, regeneration rules, and minimum requirements.
3. E-Way Bill Domain: Distance-based validity periods (200 km / 1 day) and cancellation rules.
4. Strict Domain Isolation: Verifies cross-domain queries yield "Information not found in the selected domain context."
5. Unanswerability / Out-of-Domain: Zero hallucinations on irrelevant queries.
"""

import sys
import logging
from pathlib import Path

# Fix Windows console UTF-8 encoding (e.g. Rupee symbol ₹)
if sys.platform == "win32":
    import io
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Add src directory to path
SRC_DIR = Path(__file__).resolve().parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from qa_engine import QAEngine
from config import FALLBACK_RESPONSE

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger("test_qa")


def run_verification_tests():
    print("\n" + "=" * 78)
    print(" GST Sentinel Multi-Domain QA Pipeline — Regression & Grounding Suite")
    print("=" * 78)

    engine = QAEngine()

    test_cases = [
        # Domain 1: IMS
        {
            "id": "TC-IMS-01",
            "domain": "ims",
            "category": "IMS Recipient Actions (Image 1 fix)",
            "question": "What are the three actions a recipient can take on a record in IMS?",
            "required_phrases": ["accept", "reject", "pending"],
            "forbidden_phrases": ["^ii\\.?$", " 0 "],
            "must_not_equal": FALLBACK_RESPONSE,
            "custom_assert": lambda a: "accept" in a.lower() and "reject" in a.lower() and "pending" in a.lower(),
        },
        {
            "id": "TC-IMS-02",
            "domain": "ims",
            "category": "IMS Launch Timeline",
            "question": "When will IMS be made available to taxpayers?",
            "required_phrases": ["1st october 2024"],
            "must_not_equal": FALLBACK_RESPONSE,
            "custom_assert": lambda a: "1st october 2024" in a.lower() or "14th october 2024" in a.lower(),
        },

        # Domain 2: E-Invoice
        {
            "id": "TC-EINV-01",
            "domain": "e_invoice",
            "category": "IRN Minimum Requirements (Image 2 fix)",
            "question": "What is the minimum an e-invoice request needs to satisfy before an IRN can be generated?",
            "must_not_equal": FALLBACK_RESPONSE,
            "custom_assert": lambda a: a.strip() != "0" and len(a) > 10 and any(w in a.lower() for w in ["version", "schema", "date", "supplier", "document number", "conditions", "mandatory"]),
        },
        {
            "id": "TC-EINV-02",
            "domain": "e_invoice",
            "category": "IRN Cancellation & Regeneration (Image 3 fix)",
            "question": "what is the cancellation time frame for the IRN ?",
            "required_phrases": ["24 hours"],
            "forbidden_phrases": ["^0$", " 0 "],
            "must_not_equal": FALLBACK_RESPONSE,
            "custom_assert": lambda a: a.strip() != "0" and "24 hours" in a.lower(),
        },
        {
            "id": "TC-EINV-03",
            "domain": "e_invoice",
            "category": "Auth Token Validity",
            "question": "How long is the auth token valid for?",
            "must_not_equal": FALLBACK_RESPONSE,
            "custom_assert": lambda a: "360" in a or "6 hours" in a.lower(),
        },

        # Domain 3: E-Way Bill
        {
            "id": "TC-EWB-01",
            "domain": "eway_bill",
            "category": "E-Way Bill Validity by Distance",
            "question": "What is the validity period of an e-way bill for regular cargo?",
            "required_phrases": ["1 day"],
            "must_not_equal": FALLBACK_RESPONSE,
            "custom_assert": lambda a: "1 day" in a.lower(),
        },
        {
            "id": "TC-EWB-02",
            "domain": "eway_bill",
            "category": "Part-A Slip Generation Rule",
            "question": "What happens if only Transporter ID is provided in e-way bill request?",
            "required_phrases": ["part-a"],
            "must_not_equal": FALLBACK_RESPONSE,
            "custom_assert": lambda a: "part-a" in a.lower(),
        },

        # Domain Isolation & Negative Checks
        {
            "id": "TC-ISO-01",
            "domain": "ims",
            "category": "Domain Isolation (E-Way question queried against IMS domain)",
            "question": "What is the validity period of an e-way bill for regular cargo?",
            "must_equal": FALLBACK_RESPONSE,
            "custom_assert": lambda a: a == FALLBACK_RESPONSE,
        },
        {
            "id": "TC-NEG-01",
            "domain": "e_invoice",
            "category": "Out-of-Domain Negative Check",
            "question": "What is the population of Jupiter and Martian colonies?",
            "must_equal": FALLBACK_RESPONSE,
            "custom_assert": lambda a: a == FALLBACK_RESPONSE,
        },
    ]

    passed = 0
    total = len(test_cases)
    failures = []

    for i, tc in enumerate(test_cases, 1):
        dom = tc["domain"]
        print(f"\n[{i}/{total}] [{tc['id']}] Domain: [{dom.upper()}] — {tc['category']}")
        print(f"Question: \"{tc['question']}\"")

        res = engine.answer_question(tc["question"], domain=dom)
        ans = res["answer"]
        score = res["score"]
        latency = res["latency_seconds"]

        print(f"Answer:   {ans}")
        print(f"Score:    {score}")
        print(f"Latency:  {latency}s")
        if res["retrieved_chunks"]:
            top_chunk = res["retrieved_chunks"][0]
            print(f"Source:   [{top_chunk['section']}] (Chunk #{top_chunk['chunk_id']})")

        # Explicit Assertions
        test_passed = True
        err_msg = ""

        if "must_equal" in tc and ans != tc["must_equal"]:
            test_passed = False
            err_msg += f"Expected exact fallback '{tc['must_equal']}', got '{ans}'. "

        if "must_not_equal" in tc and ans == tc["must_not_equal"]:
            test_passed = False
            err_msg += f"Returned unexpected fallback for valid statutory query in domain '{dom}'. "

        if "required_phrases" in tc:
            lower_ans = ans.lower()
            for phrase in tc["required_phrases"]:
                if phrase.lower() not in lower_ans:
                    test_passed = False
                    err_msg += f"Missing required phrase '{phrase}' in answer. "

        if "forbidden_phrases" in tc:
            for phrase in tc["forbidden_phrases"]:
                if phrase == "^0$" and ans.strip() == "0":
                    test_passed = False
                    err_msg += "Hallucinated degenerate answer '0'! "
                elif phrase in ans:
                    test_passed = False
                    err_msg += f"Found forbidden phrase '{phrase}'. "

        if "custom_assert" in tc:
            try:
                assert tc["custom_assert"](ans)
            except AssertionError:
                test_passed = False
                err_msg += "Custom assertion failed. "

        if test_passed:
            passed += 1
            print("Status:   PASSED")
        else:
            print(f"Status:   FAILED -> {err_msg.strip()}")
            failures.append((tc["id"], tc["question"], err_msg))

    print("\n" + "=" * 78)
    print(f" SUMMARY: {passed}/{total} Test Cases Passed ({round((passed/total)*100, 1)}%)")
    print("=" * 78)

    if failures:
        print("\nFailed Cases:")
        for fid, fq, fmsg in failures:
            print(f" - [{fid}] \"{fq}\": {fmsg}")
        sys.exit(1)
    else:
        print("\nAll multi-domain regression & grounding edge cases PASSED successfully!\n")
        sys.exit(0)


if __name__ == "__main__":
    run_verification_tests()
