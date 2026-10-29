import json
import logging
import re
import string
from collections import Counter
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from config import DATA_DIR, DOCS_DIR, TOP_K, SCORE_THRESHOLD
from qa_bot import QABot
from retriever import search

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s"
)
logger = logging.getLogger("gst_sentinel.evaluate")

QA_TEST_PATH = DATA_DIR / "qa_test.json"
REPORT_PATH = DOCS_DIR / "eval_report.md"


def normalize_answer(s: Optional[str]) -> str:
    """
    Standard SQuAD/QA text normalization:
    - Lowercase
    - Remove punctuation
    - Normalize consecutive whitespace
    """
    if s is None:
        return ""
    
    def remove_punctuation(text: str) -> str:
        return "".join(ch for ch in text if ch not in set(string.punctuation))

    def white_space_fix(text: str) -> str:
        return " ".join(text.split())

    def lower(text: str) -> str:
        return text.lower()

    return white_space_fix(remove_punctuation(lower(s)))


def compute_exact_match(prediction: str, ground_truth: Optional[str]) -> float:
    """Exact Match (EM) over normalized strings."""
    norm_pred = normalize_answer(prediction)
    norm_gt = normalize_answer(ground_truth)
    return 1.0 if norm_pred == norm_gt else 0.0


def compute_f1(prediction: str, ground_truth: Optional[str]) -> float:
    """Token-level F1 score based on word overlap."""
    norm_pred = normalize_answer(prediction)
    norm_gt = normalize_answer(ground_truth)

    pred_tokens = norm_pred.split()
    gt_tokens = norm_gt.split()

    if not pred_tokens or not gt_tokens:
        return 1.0 if pred_tokens == gt_tokens else 0.0

    common = Counter(pred_tokens) & Counter(gt_tokens)
    num_same = sum(common.values())

    if num_same == 0:
        return 0.0

    precision = 1.0 * num_same / len(pred_tokens)
    recall = 1.0 * num_same / len(gt_tokens)
    f1 = (2 * precision * recall) / (precision + recall)
    return f1


def diagnose_failure(
    item: Dict[str, Any],
    pred_ans: str,
    retrieved_chunks: List[Any]
) -> str:
    """
    Diagnoses failure mode into one of three categories:
    - 'false answer' (unanswerable query hallucinated an answer)
    - 'retrieval miss' (ground truth missing from retrieved passages)
    - 'wrong span' (chunk was retrieved, but Longformer picked bad tokens)
    """
    is_answerable = item.get("answerable", True)
    gt_answer = item.get("answer")

    if not is_answerable:
        if pred_ans.lower() != "not found":
            return "false answer"
        return "none"

    if pred_ans.lower() == "not found":
        # Check if ground truth appears in any retrieved chunk
        norm_gt = normalize_answer(gt_answer)
        chunk_texts = [normalize_answer(c.content) for c in retrieved_chunks]
        if any(norm_gt in text for text in chunk_texts):
            return "wrong span"
        return "retrieval miss"

    # Predicted an answer, but low F1 / non-matching
    norm_gt = normalize_answer(gt_answer)
    chunk_texts = [normalize_answer(c.content) for c in retrieved_chunks]
    if not any(norm_gt in text for text in chunk_texts):
        return "retrieval miss"
    return "wrong span"


def run_evaluation():
    if not QA_TEST_PATH.exists():
        raise FileNotFoundError(
            f"Test set missing at {QA_TEST_PATH.resolve()}. Complete Day 7 first."
        )

    with open(QA_TEST_PATH, "r", encoding="utf-8") as f:
        test_set = json.load(f)

    logger.info(f"Loaded {len(test_set)} test items from {QA_TEST_PATH}")
    bot = QABot()

    answerable_em: List[float] = []
    answerable_f1: List[float] = []
    refusal_correct = 0
    refusal_total = 0

    eval_records = []

    print("\n" + "=" * 80)
    print("RUNNING QA BENCHMARK OVER FULL TEST SET")
    print("=" * 80)

    for idx, item in enumerate(test_set, start=1):
        question = item["question"]
        gt_answer = item.get("answer")
        is_answerable = item.get("answerable", True)

        # Execute end-to-end bot
        result = bot.answer_question(question)
        pred_ans = result["answer"]

        # Also retrieve raw chunks for root-cause diagnosis
        retrieved_chunks = search(question, k=TOP_K)

        em = 0.0
        f1 = 0.0
        is_refusal_ok = False

        if is_answerable:
            em = compute_exact_match(pred_ans, gt_answer)
            f1 = compute_f1(pred_ans, gt_answer)
            answerable_em.append(em)
            answerable_f1.append(f1)
        else:
            refusal_total += 1
            if pred_ans.lower() == "not found":
                refusal_correct += 1
                is_refusal_ok = True

        diagnosis = diagnose_failure(item, pred_ans, retrieved_chunks)

        eval_records.append({
            "idx": idx,
            "question": question,
            "ground_truth": gt_answer,
            "prediction": pred_ans,
            "is_answerable": is_answerable,
            "em": em,
            "f1": f1,
            "refusal_ok": is_refusal_ok,
            "diagnosis": diagnosis
        })

    # Summary Metrics
    avg_em = (sum(answerable_em) / len(answerable_em)) * 100 if answerable_em else 0.0
    avg_f1 = (sum(answerable_f1) / len(answerable_f1)) * 100 if answerable_f1 else 0.0
    refusal_acc = (refusal_correct / refusal_total) * 100 if refusal_total else 0.0
    total_samples = len(test_set)
    answerable_count = len(answerable_em)

    # Identify 5 worst failures
    # Rank: Unanswerables that weren't refused, followed by answerables with lowest F1
    failed_items = [
        r for r in eval_records
        if (r["is_answerable"] and r["f1"] < 0.5) or (not r["is_answerable"] and not r["refusal_ok"])
    ]
    # Sort lowest F1 first
    failed_items.sort(key=lambda x: (x["f1"] if x["is_answerable"] else 0.0))
    worst_5 = failed_items[:5]

    print("\n" + "=" * 80)
    print("QA EVALUATION SUMMARY")
    print("=" * 80)
    print(f"Total Test Items:             {total_samples}")
    print(f"Answerable Items:             {answerable_count}")
    print(f"Unanswerable Items:           {refusal_total}")
    print(f"Exact Match (Normalized):     {avg_em:.2f}%")
    print(f"Token-Level F1:               {avg_f1:.2f}%")
    print(f"Refusal Accuracy:             {refusal_acc:.2f}% ({refusal_correct}/{refusal_total})")

    # Generate Markdown Report
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    report_md = f"""
## Evaluation Report

### Overall & Per-Type Benchmark Scores
| Metric / Type | Count | Score |
|---|---|---|
| **Total Test Set** | {total_samples} | 100% evaluated |
| **Exact Match (EM)** | {answerable_count} answerable | **{avg_em:.2f}%** |
| **Token-Level F1** | {answerable_count} answerable | **{avg_f1:.2f}%** |
| **Refusal Accuracy** | {refusal_total} unanswerable | **{refusal_acc:.2f}%** ({refusal_correct}/{refusal_total}) |

---

### Diagnosis of 5 Worst Failures
| # | Question | Ground Truth | Prediction | Failure Diagnosis |
|---|---|---|---|---|
"""
    for w in worst_5:
        gt_disp = str(w['ground_truth']).replace('|', '\\|') if w['ground_truth'] else "*(Unanswerable)*"
        pred_disp = str(w['prediction']).replace('|', '\\|')
        q_disp = str(w['question']).replace('|', '\\|')
        report_md += f"| {w['idx']} | {q_disp} | {gt_disp} | {pred_disp} | **{w['diagnosis']}** |\n"

    # Append to docs/eval_report.md
    with open(REPORT_PATH, "a", encoding="utf-8") as f:
        f.write("\n" + report_md)

    print(f"\n[+] Full report saved to: {REPORT_PATH}")
    print("\nTop Diagnosed Failures:")
    for i, w in enumerate(worst_5, start=1):
        print(f"  {i}. Q: {w['question']!r}")
        print(f"     Diagnosis: {w['diagnosis']} | Pred: {w['prediction']!r}")


if __name__ == "__main__":
    run_evaluation()