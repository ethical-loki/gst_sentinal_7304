"""
scripts/benchmark_phase16_100plus.py
====================================
Phase 16 — 100+ Case Complex Description Benchmark & Performance Profiling.
Covers all 10 required test categories across all 9 active chapters (19, 39, 61, 62, 73, 84, 85, 87, 94),
separating independent evaluation cases from training/validation HSN overlaps.
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ml.multi_candidate_engine import MultiCandidateEngine
from src.nlp.product_intent_analyzer import analyze_product_intent


def _build_102_cases(df_indep: pd.DataFrame) -> List[Dict[str, str]]:
    cases: List[Dict[str, str]] = [
        {**dict(r), "source": "independent_12", "category": "complex_commercial"}
        for r in df_indep.to_dict(orient="records")
    ]
    extra: List[Dict[str, str]] = [
        # --- Simple (10) ---
        {"query": "stainless steel screws and bolts", "expected_hsn": "73181500", "expected_chapter": "73", "category": "simple"},
        {"query": "tapioca starch flakes and pearls", "expected_hsn": "19030000", "expected_chapter": "19", "category": "simple"},
        {"query": "polypropylene granules in primary forms", "expected_hsn": "39021000", "expected_chapter": "39", "category": "simple"},
        {"query": "linear low density polyethylene resin in primary form", "expected_hsn": "39011010", "expected_chapter": "39", "category": "simple"},
        {"query": "steel sheet piling for construction", "expected_hsn": "73011000", "expected_chapter": "73", "category": "simple"},
        {"query": "cast iron rain water pipe", "expected_hsn": "73030010", "expected_chapter": "73", "category": "simple"},
        {"query": "central heating boilers of iron or steel", "expected_hsn": "84031000", "expected_chapter": "84", "category": "simple"},
        {"query": "pedestrian controlled agricultural tractor", "expected_hsn": "87011000", "expected_chapter": "87", "category": "simple"},
        {"query": "electric passenger motor car", "expected_hsn": "87031010", "expected_chapter": "87", "category": "simple"},
        {"query": "metal office furniture of steel", "expected_hsn": "94031010", "expected_chapter": "94", "category": "simple"},

        # --- Multiple materials (10) ---
        {"query": "cotton knitted T-shirt with polyester collar", "expected_hsn": "61091000", "expected_chapter": "61", "category": "multiple_materials"},
        {"query": "plastic water bottle made of polyethylene", "expected_hsn": "39233090", "expected_chapter": "39", "category": "multiple_materials"},
        {"query": "knitted woollen sweater pullover", "expected_hsn": "61101110", "expected_chapter": "61", "category": "multiple_materials"},
        {"query": "woven cotton shirt for men", "expected_hsn": "62052000", "expected_chapter": "62", "category": "multiple_materials"},
        {"query": "men knitted woollen overcoat", "expected_hsn": "61011010", "expected_chapter": "61", "category": "multiple_materials"},
        {"query": "knitted silk suits for men", "expected_hsn": "61031010", "expected_chapter": "61", "category": "multiple_materials"},
        {"query": "men woven woollen overcoat", "expected_hsn": "62011100", "expected_chapter": "62", "category": "multiple_materials"},
        {"query": "men woven woollen suit", "expected_hsn": "62031100", "expected_chapter": "62", "category": "multiple_materials"},
        {"query": "wooden bedroom furniture bed", "expected_hsn": "94035010", "expected_chapter": "94", "category": "multiple_materials"},
        {"query": "wooden dining table for household use", "expected_hsn": "94036000", "expected_chapter": "94", "category": "multiple_materials"},

        # --- Multiple ingredients (10) ---
        {"query": "instant noodles made from wheat flour", "expected_hsn": "19023010", "expected_chapter": "19", "category": "multiple_ingredients"},
        {"query": "wheat noodles containing seasoning and vegetable additives", "expected_hsn": "19023010", "expected_chapter": "19", "category": "multiple_ingredients"},
        {"query": "sweet biscuits containing cocoa", "expected_hsn": "19053100", "expected_chapter": "19", "category": "multiple_ingredients"},
        {"query": "uncooked pasta containing eggs not stuffed", "expected_hsn": "19021100", "expected_chapter": "19", "category": "multiple_ingredients"},
        {"query": "malt extract food preparation of flour and starch", "expected_hsn": "19011010", "expected_chapter": "19", "category": "multiple_ingredients"},
        {"query": "crispy savoury cornflakes breakfast cereal", "expected_hsn": "19041010", "expected_chapter": "19", "category": "multiple_ingredients"},
        {"query": "waffles and wafers coated with chocolate", "expected_hsn": "19053211", "expected_chapter": "19", "category": "multiple_ingredients"},
        {"query": "salted butter biscuits baked from wheat flour", "expected_hsn": "19059020", "expected_chapter": "19", "category": "multiple_ingredients"},
        {"query": "papad made from lentil flour and spices", "expected_hsn": "19059040", "expected_chapter": "19", "category": "multiple_ingredients"},
        {"query": "vermicelli pasta prepared from durum wheat semolina", "expected_hsn": "19021900", "expected_chapter": "19", "category": "multiple_ingredients"},

        # --- Parenthetical (8) ---
        {"query": "industrial centrifugal pump (cast iron casing, 5 hp electric motor)", "expected_hsn": "84137010", "expected_chapter": "84", "category": "parenthetical"},
        {"query": "rotary screw air compressor (oil-injected, 15 kw)", "expected_hsn": "84148011", "expected_chapter": "84", "category": "parenthetical"},
        {"query": "static converter (single-phase bridge rectifier)", "expected_hsn": "85044021", "expected_chapter": "85", "category": "parenthetical"},
        {"query": "expandable polystyrene beads (in primary forms)", "expected_hsn": "39031100", "expected_chapter": "39", "category": "parenthetical"},
        {"query": "automotive brake pads (asbestos-free friction lining)", "expected_hsn": "87083000", "expected_chapter": "87", "category": "parenthetical"},
        {"query": "flexible pvc hoses (reinforced with textile braiding)", "expected_hsn": "39173220", "expected_chapter": "39", "category": "parenthetical"},
        {"query": "swivel office chair (with variable height gas lift)", "expected_hsn": "94013000", "expected_chapter": "94", "category": "parenthetical"},
        {"query": "medical examination table (adjustable steel frame)", "expected_hsn": "94021010", "expected_chapter": "94", "category": "parenthetical"},

        # --- Multiple components (10) ---
        {"query": "stainless steel industrial pump with electric motor", "expected_hsn": "84137010", "expected_chapter": "84", "category": "multiple_components"},
        {"query": "safety air bags with inflator system for motor vehicles", "expected_hsn": "87089500", "expected_chapter": "87", "category": "multiple_components"},
        {"query": "brake pads for passenger motor cars", "expected_hsn": "87083000", "expected_chapter": "87", "category": "multiple_components"},
        {"query": "watertube steam generating boiler exceeding 45 tonnes per hour", "expected_hsn": "84021100", "expected_chapter": "84", "category": "multiple_components"},
        {"query": "diesel electric generating set not exceeding 75 kva", "expected_hsn": "85021100", "expected_chapter": "85", "category": "multiple_components"},
        {"query": "electric micro motor not exceeding 37.5 W", "expected_hsn": "85011011", "expected_chapter": "85", "category": "multiple_components"},
        {"query": "parts of ac electric generator rotor assembly", "expected_hsn": "85030010", "expected_chapter": "85", "category": "multiple_components"},
        {"query": "motor vehicle radiator with aluminium cooling fins", "expected_hsn": "87089100", "expected_chapter": "87", "category": "multiple_components"},
        {"query": "clutch assembly with pressure plate for tractors", "expected_hsn": "87089300", "expected_chapter": "87", "category": "multiple_components"},
        {"query": "vacuum cleaner with electric suction motor", "expected_hsn": "85086000", "expected_chapter": "85", "category": "multiple_components"},

        # --- Processing (10) ---
        {"query": "knitted cotton t-shirt for men", "expected_hsn": "61091000", "expected_chapter": "61", "category": "processing"},
        {"query": "seamless stainless steel tubes and pipes", "expected_hsn": "73044900", "expected_chapter": "73", "category": "processing"},
        {"query": "galvanised iron household bucket", "expected_hsn": "73239910", "expected_chapter": "73", "category": "processing"},
        {"query": "welded stainless steel pipe for industrial piping", "expected_hsn": "73064000", "expected_chapter": "73", "category": "processing"},
        {"query": "laminated bopp packaging film roll", "expected_hsn": "39202020", "expected_chapter": "39", "category": "processing"},
        {"query": "extruded rigid pvc pipe for water supply", "expected_hsn": "39172310", "expected_chapter": "39", "category": "processing"},
        {"query": "knitted polyester polo shirt for men", "expected_hsn": "61052010", "expected_chapter": "61", "category": "processing"},
        {"query": "woven cotton trousers for men", "expected_hsn": "62034200", "expected_chapter": "62", "category": "processing"},
        {"query": "forged carbon steel hex nuts", "expected_hsn": "73181600", "expected_chapter": "73", "category": "processing"},
        {"query": "dried instant vermicelli noodles", "expected_hsn": "19023010", "expected_chapter": "19", "category": "processing"},

        # --- Ambiguous (10) ---
        {"query": "plastic storage container with fitted lid", "expected_hsn": "39241090", "expected_chapter": "39", "category": "ambiguous"},
        {"query": "plastic water bottle", "expected_hsn": "39233090", "expected_chapter": "39", "category": "ambiguous"},
        {"query": "cotton shirt", "expected_hsn": "62052000", "expected_chapter": "62", "category": "ambiguous"},
        {"query": "steel tubes and pipes", "expected_hsn": "73044900", "expected_chapter": "73", "category": "ambiguous"},
        {"query": "electric water pump", "expected_hsn": "84137010", "expected_chapter": "84", "category": "ambiguous"},
        {"query": "ac electric generator", "expected_hsn": "85016100", "expected_chapter": "85", "category": "ambiguous"},
        {"query": "wooden office chair", "expected_hsn": "94016900", "expected_chapter": "94", "category": "ambiguous"},
        {"query": "plastic film sheet", "expected_hsn": "39206210", "expected_chapter": "39", "category": "ambiguous"},
        {"query": "metal fasteners screws", "expected_hsn": "73181500", "expected_chapter": "73", "category": "ambiguous"},
        {"query": "pasta noodles", "expected_hsn": "19023010", "expected_chapter": "19", "category": "ambiguous"},

        # --- Incomplete (8) ---
        {"query": "t-shirt", "expected_hsn": "61091000", "expected_chapter": "61", "category": "incomplete"},
        {"query": "screws and bolts", "expected_hsn": "73181500", "expected_chapter": "73", "category": "incomplete"},
        {"query": "swivel chair", "expected_hsn": "94013000", "expected_chapter": "94", "category": "incomplete"},
        {"query": "sweet biscuits", "expected_hsn": "19053100", "expected_chapter": "19", "category": "incomplete"},
        {"query": "brake pads", "expected_hsn": "87083000", "expected_chapter": "87", "category": "incomplete"},
        {"query": "vacuum cleaner", "expected_hsn": "85086000", "expected_chapter": "85", "category": "incomplete"},
        {"query": "centrifugal pump", "expected_hsn": "84137010", "expected_chapter": "84", "category": "incomplete"},
        {"query": "women embroidered suit", "expected_hsn": "62043991", "expected_chapter": "62", "category": "incomplete"},

        # --- Similar products with different functions (8) ---
        {"query": "plastic household food storage container with lid", "expected_hsn": "39241090", "expected_chapter": "39", "category": "similar_products"},
        {"query": "hdpe jerrycan for industrial chemical packing and transport", "expected_hsn": "39239090", "expected_chapter": "39", "category": "similar_products"},
        {"query": "seats of a kind used for aircraft", "expected_hsn": "94011000", "expected_chapter": "94", "category": "similar_products"},
        {"query": "seats of a kind used for motor vehicles", "expected_hsn": "94012000", "expected_chapter": "94", "category": "similar_products"},
        {"query": "submersible centrifugal pump for borewell water", "expected_hsn": "84137010", "expected_chapter": "84", "category": "similar_products"},
        {"query": "fuel injection pump for diesel engine", "expected_hsn": "84133010", "expected_chapter": "84", "category": "similar_products"},
        {"query": "insulated plastic water flask for beverages", "expected_hsn": "39233010", "expected_chapter": "39", "category": "similar_products"},
        {"query": "non-insulated hdpe carboy for chemical storage", "expected_hsn": "39233090", "expected_chapter": "39", "category": "similar_products"},

        # --- Complex commercial invoice descriptions (6) ---
        {"query": "304 grade seamless stainless steel boiler tubes, cold drawn, 25mm OD, for heat exchanger", "expected_hsn": "73044900", "expected_chapter": "73", "category": "complex_commercial"},
        {"query": "mens 100% combed cotton single jersey knitted round neck t-shirt in retail polybag", "expected_hsn": "61091000", "expected_chapter": "61", "category": "complex_commercial"},
        {"query": "instant wheat noodles with masala seasoning sachet in 70g retail pouch", "expected_hsn": "19023010", "expected_chapter": "19", "category": "complex_commercial"},
        {"query": "commercial 3-phase 100 kva ac generator powered by diesel engine", "expected_hsn": "85021200", "expected_chapter": "85", "category": "complex_commercial"},
        {"query": "automotive safety airbag module with pyrotechnic inflator for passenger car", "expected_hsn": "87089500", "expected_chapter": "87", "category": "complex_commercial"},
        {"query": "ergonomic mesh swivel office chair with pneumatic height adjustment and armrests", "expected_hsn": "94013000", "expected_chapter": "94", "category": "complex_commercial"},
    ]
    for item in extra:
        cases.append({**item, "source": "benchmark_90"})
    return cases


def main() -> None:
    master_df = pd.read_parquet(ROOT / "data" / "enriched_master_hsn.parquet")
    master_8digit = set(
        master_df.loc[master_df["code_length"] == 8, "hsn_code"].astype(str).str.strip()
    )
    train_df = pd.read_parquet(ROOT / "data" / "training_pairs" / "full_pairs_train.parquet")
    val_df = pd.read_parquet(ROOT / "data" / "training_pairs" / "full_pairs_val.parquet")
    train_q = set(train_df["query"].astype(str).str.lower().str.strip()) if "query" in train_df.columns else set()
    val_q = set(val_df["query"].astype(str).str.lower().str.strip()) if "query" in val_df.columns else set()
    train_hsn = set(train_df["hsn_code"].astype(str).str.strip()) if "hsn_code" in train_df.columns else set()
    val_hsn = set(val_df["hsn_code"].astype(str).str.strip()) if "hsn_code" in val_df.columns else set()

    df_indep = pd.read_parquet(ROOT / "data" / "eval" / "independent_exact_hsn_eval.parquet")
    all_cases = _build_102_cases(df_indep)

    # Filter/verify gold HSNs exist in master_8digit
    valid_cases = [c for c in all_cases if str(c["expected_hsn"]).strip() in master_8digit]
    print(f"Running Phase 16 benchmark on {len(valid_cases)}/{len(all_cases)} master-verified cases...")

    eng = MultiCandidateEngine.get_instance()
    per_case: List[Dict[str, Any]] = []
    for idx, r in enumerate(valid_cases, start=1):
        q = str(r["query"])
        exp_hsn = str(r["expected_hsn"]).strip()
        exp_ch = str(r["expected_chapter"]).strip().zfill(2)
        exp_h4 = exp_hsn[:4]

        pi = analyze_product_intent(q)
        t0 = time.perf_counter()
        res = eng.classify_adaptive(q, page=1, page_size=None)
        dt = round((time.perf_counter() - t0) * 1000.0, 1)

        cands = res.get("candidates", [])
        distinct_8 = [c for c in cands if len(str(c.get("hsn_code", ""))) >= 8]
        codes = list(dict.fromkeys(c["hsn_code"] for c in distinct_8))
        rank = codes.index(exp_hsn) + 1 if exp_hsn in codes else None
        top_ch = distinct_8[0].get("chapter_code", "").zfill(2) if distinct_8 else (res.get("final_chapter") or "")

        same_h4 = sum(1 for c in distinct_8 if c["hsn_code"][:4] == exp_h4)
        mat_only = sum(
            1 for c in distinct_8
            if not (c.get("evidence_trace") or {}).get("article_matches")
            and (c.get("evidence_trace") or {}).get("material_matches")
        )
        mode = res.get("prediction_mode", "")
        final_hsn = res.get("final_hsn")
        clar = res.get("clarification") or {}
        exec_m = (res.get("audit") or {}).get("execution_metrics") or {}

        q_norm = q.lower().strip()
        per_case.append({
            "case_id": idx,
            "source": r["source"],
            "category": r["category"],
            "query": q,
            "finished_article": pi.finished_article,
            "expected_hsn": exp_hsn,
            "expected_chapter": exp_ch,
            "top_chapter": top_ch,
            "chapter_hit": top_ch == exp_ch,
            "query_overlap": (q_norm in train_q) or (q_norm in val_q),
            "hsn_overlap": (exp_hsn in train_hsn) or (exp_hsn in val_hsn),
            "retained_8digit": len(codes),
            "same_h4": same_h4,
            "material_only": mat_only,
            "recall_hit": exp_hsn in codes,
            "rank": rank,
            "prediction_mode": mode,
            "final_hsn": final_hsn,
            "exact_hit": mode == "EXACT_HSN" and final_hsn == exp_hsn,
            "false_exact": mode == "EXACT_HSN" and final_hsn != exp_hsn,
            "correctly_abstained": (mode != "EXACT_HSN") or (final_hsn == exp_hsn),
            "clarification_effective": (mode == "EXACT_HSN") or bool(clar.get("questions") or clar.get("separating_attributes")),
            "latency_ms": dt,
            "stage1_intent_ms": exec_m.get("stage1_intent_ms", 0.0),
            "retrieval_time_ms": exec_m.get("retrieval_time_ms", 0.0),
            "reranking_time_ms": exec_m.get("reranking_time_ms", 0.0),
            "stage3_evidence_ms": exec_m.get("stage3_evidence_ms", 0.0),
            "stage3_statutory_ms": exec_m.get("stage3_statutory_ms", 0.0),
        })

    def _agg(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        n = len(rows)
        if not n:
            return {}
        lats = [r["latency_ms"] for r in rows]
        rets = [r["retained_8digit"] for r in rows]
        tot_ret = sum(rets)
        return {
            "n": n,
            "chapter_accuracy_pct": round(100.0 * sum(1 for r in rows if r["chapter_hit"]) / n, 2),
            "candidate_recall_pct": round(100.0 * sum(1 for r in rows if r["recall_hit"]) / n, 2),
            "recall_at_5_pct": round(100.0 * sum(1 for r in rows if r["rank"] and r["rank"] <= 5) / n, 2),
            "recall_at_10_pct": round(100.0 * sum(1 for r in rows if r["rank"] and r["rank"] <= 10) / n, 2),
            "top1_pct": round(100.0 * sum(1 for r in rows if r["rank"] == 1) / n, 2),
            "same_heading_precision_pct": round(100.0 * sum(r["same_h4"] for r in rows) / max(tot_ret, 1), 2),
            "material_only_count": sum(r["material_only"] for r in rows),
            "exact_hsn_hits": sum(1 for r in rows if r["exact_hit"]),
            "exact_hsn_accuracy_pct": round(100.0 * sum(1 for r in rows if r["exact_hit"]) / n, 2),
            "false_exact_count": sum(1 for r in rows if r["false_exact"]),
            "correct_abstention_pct": round(100.0 * sum(1 for r in rows if r["correctly_abstained"]) / n, 2),
            "clarification_effectiveness_pct": round(100.0 * sum(1 for r in rows if r["clarification_effective"]) / n, 2),
            "mean_retained": round(statistics.mean(rets), 2),
            "median_retained": round(statistics.median(rets), 2),
            "p95_retained": round(float(np.percentile(rets, 95)), 2),
            "mean_latency_ms": round(statistics.mean(lats), 1),
            "p95_latency_ms": round(float(np.percentile(lats, 95)), 1),
        }

    indep_rows = [r for r in per_case if r["source"] == "independent_12"]
    non_indep_rows = [r for r in per_case if r["source"] != "independent_12"]
    by_cat = {cat: _agg([r for r in per_case if r["category"] == cat]) for cat in sorted({r["category"] for r in per_case})}

    summary = {
        "total_cases": len(per_case),
        "integrity": {
            "all_in_master_8digit": True,
            "query_overlap_count": sum(1 for r in per_case if r["query_overlap"]),
            "independent_12_hsn_overlap": sum(1 for r in indep_rows if r["hsn_overlap"]),
            "benchmark_hsn_overlap": sum(1 for r in non_indep_rows if r["hsn_overlap"]),
        },
        "independent_12": _agg(indep_rows),
        "benchmark_non_indep": _agg(non_indep_rows),
        "overall": _agg(per_case),
        "by_category": by_cat,
        "stage_latency_means_ms": {
            "stage1_intent_ms": round(statistics.mean(r["stage1_intent_ms"] for r in per_case), 2),
            "retrieval_time_ms": round(statistics.mean(r["retrieval_time_ms"] for r in per_case), 2),
            "reranking_time_ms": round(statistics.mean(r["reranking_time_ms"] for r in per_case), 2),
            "stage3_evidence_ms": round(statistics.mean(r["stage3_evidence_ms"] for r in per_case), 2),
            "stage3_statutory_ms": round(statistics.mean(r["stage3_statutory_ms"] for r in per_case), 2),
        },
        "cases": per_case,
    }
    out = ROOT / "reports" / "phase16_benchmark_100plus.json"
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("Saved", out)
    print("OVERALL:", json.dumps(summary["overall"]))
    print("INDEPENDENT_12:", json.dumps(summary["independent_12"]))
    print("STAGE_LATENCIES:", json.dumps(summary["stage_latency_means_ms"]))
    print("INTEGRITY:", json.dumps(summary["integrity"]))


if __name__ == "__main__":
    main()

