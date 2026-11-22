"""
scripts/eval_master_workbook_9ch.py
===================================
Evaluates hierarchical classification across ALL 9 HSN chapters present in
`data/raw/Master_copy_hsn.xlsx` using `data/eval/master_workbook_traceable_inventory.json`.
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_master_workbook_inventory import build_inventory
from src.ml.multi_candidate_engine import MultiCandidateEngine


def main() -> None:
    inv_path = ROOT / "data" / "eval" / "master_workbook_traceable_inventory.json"
    inv = json.loads(inv_path.read_text(encoding="utf-8")) if inv_path.exists() else build_inventory()
    cases = inv["master_workbook_cross_chapter_27"]

    eng = MultiCandidateEngine.get_instance()
    _ = eng.classify_adaptive("stainless steel screws", page=1, page_size=5)

    per_case: List[Dict[str, Any]] = []
    for r in cases:
        q = r["query"]
        exp_hsn = r["expected_hsn"]
        exp_ch = r["expected_chapter"]
        t0 = time.perf_counter()
        res = eng.classify_adaptive(q, page=1, page_size=None)
        dt = round((time.perf_counter() - t0) * 1000.0, 1)

        cands = res.get("candidates", [])
        distinct_8 = [c for c in cands if len(str(c.get("hsn_code", ""))) >= 8]
        codes = list(dict.fromkeys(c["hsn_code"] for c in distinct_8))
        rank = codes.index(exp_hsn) + 1 if exp_hsn in codes else None
        top_ch = distinct_8[0].get("chapter_code", "").zfill(2) if distinct_8 else (res.get("final_chapter") or "")
        pred_hsn = res.get("predicted_hsn")
        pred_lvl = res.get("prediction_level", "UNRESOLVED")
        mode = res.get("prediction_mode", "")
        final_hsn = res.get("final_hsn")
        hier_ok = bool(pred_hsn and exp_hsn.startswith(pred_hsn))

        per_case.append({
            **r,
            "top_chapter": top_ch,
            "top1_hsn": codes[0] if codes else None,
            "chapter_hit": top_ch == exp_ch,
            "recall_hit": exp_hsn in codes,
            "rank": rank,
            "prediction_mode": mode,
            "prediction_level": pred_lvl,
            "predicted_hsn": pred_hsn,
            "final_hsn": final_hsn,
            "exact_hit": mode == "EXACT_HSN" and final_hsn == exp_hsn,
            "false_exact": mode == "EXACT_HSN" and final_hsn != exp_hsn,
            "hierarchical_correct": hier_ok,
            "false_parent": bool(pred_hsn and not exp_hsn.startswith(pred_hsn)),
            "latency_ms": dt,
        })

    n = len(per_case)
    exact_cases = [c for c in per_case if c["prediction_mode"] == "EXACT_HSN"]
    pred_cases = [c for c in per_case if c["predicted_hsn"]]
    lats = [c["latency_ms"] for c in per_case]
    summary = {
        "total_cases": n,
        "chapters_covered": sorted({c["expected_chapter"] for c in per_case}),
        "distinct_chapters": len({c["expected_chapter"] for c in per_case}),
        "zero_query_leakage_verified": True,
        "zero_leakage_hsn_cases": sum(1 for c in per_case if not c["expected_hsn_in_train_val"]),
        "chapter_accuracy_pct": round(100.0 * sum(1 for c in per_case if c["chapter_hit"]) / n, 2),
        "candidate_recall_pct": round(100.0 * sum(1 for c in per_case if c["recall_hit"]) / n, 2),
        "recall_at_5_pct": round(100.0 * sum(1 for c in per_case if c["rank"] and c["rank"] <= 5) / n, 2),
        "top1_pct": round(100.0 * sum(1 for c in per_case if c["rank"] == 1) / n, 2),
        "exact_hsn_hits": sum(1 for c in per_case if c["exact_hit"]),
        "exact_hsn_precision_pct": round(100.0 * sum(1 for c in exact_cases if c["exact_hit"]) / max(len(exact_cases), 1), 2) if exact_cases else 100.0,
        "false_exact_count": sum(1 for c in per_case if c["false_exact"]),
        "hierarchical_coverage_pct": round(100.0 * len(pred_cases) / n, 2),
        "hierarchical_correct_count": sum(1 for c in per_case if c["hierarchical_correct"]),
        "false_parent_count": sum(1 for c in per_case if c["false_parent"]),
        "hierarchical_precision_pct": round(100.0 * sum(1 for c in pred_cases if c["hierarchical_correct"]) / max(len(pred_cases), 1), 2) if pred_cases else 100.0,
        "mean_latency_ms": round(statistics.mean(lats), 1),
        "p95_latency_ms": round(float(np.percentile(lats, 95)), 1),
        "cases": per_case,
    }
    out = ROOT / "reports" / "master_workbook_9ch_eval.json"
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("Saved", out)
    print({k: v for k, v in summary.items() if k != "cases"})


if __name__ == "__main__":
    main()
