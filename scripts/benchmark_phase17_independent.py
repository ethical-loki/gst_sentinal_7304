"""
scripts/benchmark_phase17_independent.py
========================================
Phase 17 — 100-Case Zero-Leakage Independent Benchmark.
Every gold 8-digit HSN in the 100-case benchmark is verified:
  1. Present as an 8-digit leaf in `data/enriched_master_hsn.parquet`.
  2. ZERO HSN overlap with `full_pairs_train.parquet` or `full_pairs_val.parquet`.
  3. Independently authored commercial descriptions (never copied verbatim from statutory text).
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ml.multi_candidate_engine import MultiCandidateEngine


INDEPENDENT_100: List[Dict[str, str]] = [
    # --- Chapter 39 (18 zero-leakage HSNs) ---
    {"query": "halogenated vinyl chloride polymer resin granules", "expected_hsn": "39049000", "expected_chapter": "39", "category": "simple"},
    {"query": "vinyl acetate polymer dispersion in primary form", "expected_hsn": "39051920", "expected_chapter": "39", "category": "processing"},
    {"query": "polyvinyl alcohol powder soluble polymer resin", "expected_hsn": "39053000", "expected_chapter": "39", "category": "simple"},
    {"query": "vinyl acetate ethylene copolymer emulsion resin", "expected_hsn": "39059100", "expected_chapter": "39", "category": "multiple_materials"},
    {"query": "unplasticised cellulose acetate moulding powder", "expected_hsn": "39121120", "expected_chapter": "39", "category": "processing"},
    {"query": "recycled nylon polyamide plastic scrap and parings", "expected_hsn": "39159050", "expected_chapter": "39", "category": "processing"},
    {"query": "phenoplast thermoset plastic waste and scrap", "expected_hsn": "39159061", "expected_chapter": "39", "category": "simple"},
    {"query": "mixed post-industrial plastic trimmings and scrap", "expected_hsn": "39159079", "expected_chapter": "39", "category": "ambiguous"},
    {"query": "rigid polymer pipe for industrial fluid transfer", "expected_hsn": "39172990", "expected_chapter": "39", "category": "ambiguous"},
    {"query": "flexible plasticized pvc sausage casing tubing", "expected_hsn": "39173220", "expected_chapter": "39", "category": "multiple_materials"},
    {"query": "unreinforced non-cellular pet polyester film roll", "expected_hsn": "39206210", "expected_chapter": "39", "category": "processing"},
    {"query": "biaxially oriented polyester sheet for packaging", "expected_hsn": "39206932", "expected_chapter": "39", "category": "multiple_materials"},
    {"query": "regenerated cellulose non-cellular plastic sheet", "expected_hsn": "39207290", "expected_chapter": "39", "category": "processing"},
    {"query": "rigid plain polyvinyl butyral plastic sheet", "expected_hsn": "39209110", "expected_chapter": "39", "category": "processing"},
    {"query": "flexible plain unreinforced plastic film", "expected_hsn": "39209992", "expected_chapter": "39", "category": "ambiguous"},
    {"query": "multi-layer laminated plastic sheet for industrial use", "expected_hsn": "39219099", "expected_chapter": "39", "category": "processing"},
    {"query": "moulded plastic watch and jewellery presentation box", "expected_hsn": "39231020", "expected_chapter": "39", "category": "simple"},
    {"query": "polyurethane foam desk organizer for office supplies", "expected_hsn": "39261091", "expected_chapter": "39", "category": "multiple_materials"},

    # --- Chapter 61 (8 zero-leakage HSNs) ---
    {"query": "men knitted casual ensemble of linen blend", "expected_hsn": "61032990", "expected_chapter": "61", "category": "multiple_materials"},
    {"query": "men knitted 100% cotton round neck t-shirt", "expected_hsn": "61091000", "expected_chapter": "61", "category": "processing"},
    {"query": "knitted mulberry silk undershirt vest", "expected_hsn": "61099030", "expected_chapter": "61", "category": "multiple_materials"},
    {"query": "knitted merino wool winter cardigan sweater", "expected_hsn": "61101120", "expected_chapter": "61", "category": "processing"},
    {"query": "knitted viscose artificial fibre women top", "expected_hsn": "61143020", "expected_chapter": "61", "category": "multiple_materials"},
    {"query": "knitted bamboo fibre ankle socks", "expected_hsn": "61159990", "expected_chapter": "61", "category": "ambiguous"},
    {"query": "knitted cotton necktie accessory", "expected_hsn": "61172030", "expected_chapter": "61", "category": "simple"},
    {"query": "knitted cotton headband clothing accessory", "expected_hsn": "61178030", "expected_chapter": "61", "category": "ambiguous"},

    # --- Chapter 62 (7 zero-leakage HSNs) ---
    {"query": "men woven linen winter trench coat", "expected_hsn": "62019010", "expected_chapter": "62", "category": "processing"},
    {"query": "women woven cotton tailored blazer jacket", "expected_hsn": "62043290", "expected_chapter": "62", "category": "processing"},
    {"query": "women woven linen suit embroidered with lucknow chikan craft", "expected_hsn": "62043991", "expected_chapter": "62", "category": "complex_commercial"},
    {"query": "women woven silk evening dress", "expected_hsn": "62044990", "expected_chapter": "62", "category": "ambiguous"},
    {"query": "women woven ramie casual midi dress", "expected_hsn": "62044999", "expected_chapter": "62", "category": "ambiguous"},
    {"query": "women woven linen pleated midi skirt", "expected_hsn": "62045990", "expected_chapter": "62", "category": "processing"},
    {"query": "protective garment made from laminated nonwoven fabric", "expected_hsn": "62105000", "expected_chapter": "62", "category": "multiple_materials"},

    # --- Chapter 73 (7 zero-leakage HSNs) ---
    {"query": "welded stainless steel oil and gas line pipe", "expected_hsn": "73061100", "expected_chapter": "73", "category": "processing"},
    {"query": "non-circular rectangular hollow structural iron tube", "expected_hsn": "73066010", "expected_chapter": "73", "category": "simple"},
    {"query": "fabricated steel bridge girder section", "expected_hsn": "73081090", "expected_chapter": "73", "category": "simple"},
    {"query": "galvanised steel door and window frame assembly", "expected_hsn": "73089070", "expected_chapter": "73", "category": "multiple_components"},
    {"query": "heavy duty steel coach screw fastener", "expected_hsn": "73181190", "expected_chapter": "73", "category": "simple"},
    {"query": "cast iron domestic solid fuel cooking stove", "expected_hsn": "73211910", "expected_chapter": "73", "category": "simple"},
    {"query": "hot-dip galvanised iron household bucket and utensils", "expected_hsn": "73239910", "expected_chapter": "73", "category": "processing"},

    # --- Chapter 84 (28 zero-leakage HSNs: complete machines + parts) ---
    {"query": "petrol spark-ignition motorcycle engine 150cc", "expected_hsn": "84073290", "expected_chapter": "84", "category": "complete_machine"},
    {"query": "inlet and exhaust valves and piston rings for petrol engine", "expected_hsn": "84099113", "expected_chapter": "84", "category": "parts"},
    {"query": "diesel engine piston assembly spare part", "expected_hsn": "84099914", "expected_chapter": "84", "category": "parts"},
    {"query": "spare parts for marine outboard engine", "expected_hsn": "84099942", "expected_chapter": "84", "category": "parts"},
    {"query": "nickel superalloy turbine blade parts for aircraft turbojet", "expected_hsn": "84119100", "expected_chapter": "84", "category": "parts"},
    {"query": "retail fuel dispensing pump for petrol station", "expected_hsn": "84131191", "expected_chapter": "84", "category": "complete_machine"},
    {"query": "rotary positive displacement screw pump with cast iron casing", "expected_hsn": "84136020", "expected_chapter": "84", "category": "complete_machine"},
    {"query": "centrifugal water pump with electric motor", "expected_hsn": "84137010", "expected_chapter": "84", "category": "complete_machine"},
    {"query": "hydraulic ram water lifting pump", "expected_hsn": "84138120", "expected_chapter": "84", "category": "complete_machine"},
    {"query": "mechanical liquid elevator for industrial sump", "expected_hsn": "84138200", "expected_chapter": "84", "category": "complete_machine"},
    {"query": "spare parts for deep well turbine rotary pump", "expected_hsn": "84139130", "expected_chapter": "84", "category": "parts"},
    {"query": "stainless steel kitchen exhaust hood with fan", "expected_hsn": "84146000", "expected_chapter": "84", "category": "complete_machine"},
    {"query": "spare parts for industrial air compressor", "expected_hsn": "84149019", "expected_chapter": "84", "category": "parts"},
    {"query": "separately presented indoor split air conditioner unit", "expected_hsn": "84159010", "expected_chapter": "84", "category": "parts"},
    {"query": "household compression type refrigerator", "expected_hsn": "84182100", "expected_chapter": "84", "category": "complete_machine"},
    {"query": "instantaneous gas water heater for domestic bathroom", "expected_hsn": "84191190", "expected_chapter": "84", "category": "complete_machine"},
    {"query": "solar thermal water heater storage tank", "expected_hsn": "84191910", "expected_chapter": "84", "category": "complete_machine"},
    {"query": "industrial tray dryer for chemical processing", "expected_hsn": "84193900", "expected_chapter": "84", "category": "complete_machine"},
    {"query": "commercial espresso coffee brewing machine", "expected_hsn": "84198120", "expected_chapter": "84", "category": "complete_machine"},
    {"query": "stainless steel chemical distillation absorption column", "expected_hsn": "84198915", "expected_chapter": "84", "category": "complete_machine"},
    {"query": "laboratory autoclave sterilizer unit", "expected_hsn": "84198970", "expected_chapter": "84", "category": "complete_machine"},
    {"query": "spare parts for industrial heat exchanger plant", "expected_hsn": "84199010", "expected_chapter": "84", "category": "parts"},
    {"query": "replacement parts for industrial centrifuge filter", "expected_hsn": "84219900", "expected_chapter": "84", "category": "parts"},
    {"query": "electronic platform weighing scale 150 kg capacity", "expected_hsn": "84238210", "expected_chapter": "84", "category": "complete_machine"},
    {"query": "tractor mounted agricultural rotary hoe", "expected_hsn": "84322910", "expected_chapter": "84", "category": "complete_machine"},
    {"query": "agricultural seed drill planter machine", "expected_hsn": "84323900", "expected_chapter": "84", "category": "complete_machine"},
    {"query": "agricultural grain threshing machine", "expected_hsn": "84335300", "expected_chapter": "84", "category": "complete_machine"},
    {"query": "industrial paper pulp making machinery", "expected_hsn": "84392000", "expected_chapter": "84", "category": "complete_machine"},

    # --- Chapter 85 (21 zero-leakage HSNs) ---
    {"query": "wind-powered electric turbine generating set", "expected_hsn": "85023100", "expected_chapter": "85", "category": "complete_machine"},
    {"query": "gas turbine electric power generator set", "expected_hsn": "85023990", "expected_chapter": "85", "category": "complete_machine"},
    {"query": "dip bridge rectifier static power converter", "expected_hsn": "85044021", "expected_chapter": "85", "category": "simple"},
    {"query": "industrial dc power supply inverter unit", "expected_hsn": "85044090", "expected_chapter": "85", "category": "ambiguous"},
    {"query": "electric canister vacuum cleaner for home", "expected_hsn": "85086000", "expected_chapter": "85", "category": "complete_machine"},
    {"query": "automotive spark plug and ignition coil parts", "expected_hsn": "85119000", "expected_chapter": "85", "category": "parts"},
    {"query": "bicycle dynamo electric headlight and signalling lamp", "expected_hsn": "85121000", "expected_chapter": "85", "category": "complete_machine"},
    {"query": "industrial electron beam melting furnace", "expected_hsn": "85143100", "expected_chapter": "85", "category": "complete_machine"},
    {"query": "automatic electric resistance spot welding machine", "expected_hsn": "85152110", "expected_chapter": "85", "category": "complete_machine"},
    {"query": "carrier current line telecommunication equipment", "expected_hsn": "85175010", "expected_chapter": "85", "category": "simple"},
    {"query": "optical fibre line multiplexer telecom unit", "expected_hsn": "85176250", "expected_chapter": "85", "category": "simple"},
    {"query": "network ethernet router and packet switch", "expected_hsn": "85176270", "expected_chapter": "85", "category": "simple"},
    {"query": "telephone handset attachment cord accessory", "expected_hsn": "85178010", "expected_chapter": "85", "category": "parts"},
    {"query": "dual-driver wooden enclosure loudspeaker system", "expected_hsn": "85182290", "expected_chapter": "85", "category": "multiple_components"},
    {"query": "turntable record player deck without loudspeaker", "expected_hsn": "85192100", "expected_chapter": "85", "category": "complete_machine"},
    {"query": "magnetic audio cassette tape unrecorded", "expected_hsn": "85231129", "expected_chapter": "85", "category": "simple"},
    {"query": "blank magnetic stripe plastic smart card", "expected_hsn": "85232920", "expected_chapter": "85", "category": "simple"},
    {"query": "recordable compact disc blank optical media", "expected_hsn": "85239050", "expected_chapter": "85", "category": "simple"},
    {"query": "fm radio broadcast transmitter apparatus", "expected_hsn": "85251020", "expected_chapter": "85", "category": "complete_machine"},
    {"query": "vhf two-way walkie talkie radio transceiver", "expected_hsn": "85252011", "expected_chapter": "85", "category": "complete_machine"},
    {"query": "satellite earth station uplink transceiver", "expected_hsn": "85252091", "expected_chapter": "85", "category": "complete_machine"},

    # --- Chapter 87 (5 zero-leakage HSNs) ---
    {"query": "air-conditioned diesel passenger bus 30 seater", "expected_hsn": "87021021", "expected_chapter": "87", "category": "complete_machine"},
    {"query": "air-conditioned diesel mini bus for 14 passengers", "expected_hsn": "87021022", "expected_chapter": "87", "category": "complete_machine"},
    {"query": "diesel-electric hybrid passenger coach bus", "expected_hsn": "87022019", "expected_chapter": "87", "category": "complete_machine"},
    {"query": "petrol-electric hybrid passenger minibus", "expected_hsn": "87023018", "expected_chapter": "87", "category": "complete_machine"},
    {"query": "petrol passenger sedan car 1200cc engine", "expected_hsn": "87032291", "expected_chapter": "87", "category": "complete_machine"},

    # --- Chapter 94 (6 zero-leakage HSNs) ---
    {"query": "replacement seat cushion and metal frame parts", "expected_hsn": "94019900", "expected_chapter": "94", "category": "parts"},
    {"query": "steel office filing cabinet and desk furniture", "expected_hsn": "94031010", "expected_chapter": "94", "category": "simple"},
    {"query": "powder coated steel furniture legs and frame parts", "expected_hsn": "94039900", "expected_chapter": "94", "category": "parts"},
    {"query": "quilted cotton filled bed comforter and pillow", "expected_hsn": "94049099", "expected_chapter": "94", "category": "multiple_materials"},
    {"query": "decorative brass ceiling chandelier light fitting", "expected_hsn": "94051020", "expected_chapter": "94", "category": "multiple_materials"},
    {"query": "non-electrical brass gas lamp lighting fitting", "expected_hsn": "94055039", "expected_chapter": "94", "category": "multiple_materials"},
]


def main() -> None:
    master_df = pd.read_parquet(ROOT / "data" / "enriched_master_hsn.parquet")
    master_8digit = set(master_df.loc[master_df["code_length"] == 8, "hsn_code"].astype(str).str.strip())
    train_df = pd.read_parquet(ROOT / "data" / "training_pairs" / "full_pairs_train.parquet")
    val_df = pd.read_parquet(ROOT / "data" / "training_pairs" / "full_pairs_val.parquet")
    used_hsns = set(train_df["hsn_code"].astype(str).str.strip()) | set(val_df["hsn_code"].astype(str).str.strip())
    used_queries = set(train_df["query"].astype(str).str.lower().str.strip()) | set(val_df["query"].astype(str).str.lower().str.strip())

    assert len(INDEPENDENT_100) == 100, f"Expected 100 cases, got {len(INDEPENDENT_100)}"
    for r in INDEPENDENT_100:
        assert r["expected_hsn"] in master_8digit, f"{r['expected_hsn']} not in master 8-digit"
        assert r["expected_hsn"] not in used_hsns, f"Leakage: {r['expected_hsn']} in train/val"
        assert r["query"].lower().strip() not in used_queries, f"Query leakage: {r['query']}"

    eng = MultiCandidateEngine.get_instance()
    # Warm up once (excluded from steady-state latency? No, record cold+warm transparently!)
    per_case: List[Dict[str, Any]] = []
    for idx, r in enumerate(INDEPENDENT_100, start=1):
        q = r["query"]
        exp_hsn = r["expected_hsn"]
        exp_ch = r["expected_chapter"]
        exp_h4 = exp_hsn[:4]

        t0 = time.perf_counter()
        res = eng.classify_adaptive(q, page=1, page_size=None)
        dt = round((time.perf_counter() - t0) * 1000.0, 1)

        cands = res.get("candidates", [])
        distinct_8 = [c for c in cands if len(str(c.get("hsn_code", ""))) >= 8]
        codes = list(dict.fromkeys(c["hsn_code"] for c in distinct_8))
        rank = codes.index(exp_hsn) + 1 if exp_hsn in codes else None
        top_ch = distinct_8[0].get("chapter_code", "").zfill(2) if distinct_8 else (res.get("final_chapter") or "")
        same_h4 = sum(1 for c in distinct_8 if c["hsn_code"][:4] == exp_h4)
        mode = res.get("prediction_mode", "")
        final_hsn = res.get("final_hsn")
        exec_m = (res.get("audit") or {}).get("execution_metrics") or {}

        per_case.append({
            "case_id": idx,
            "category": r["category"],
            "query": q,
            "expected_hsn": exp_hsn,
            "expected_chapter": exp_ch,
            "top_chapter": top_ch,
            "chapter_hit": top_ch == exp_ch,
            "retained_8digit": len(codes),
            "same_h4": same_h4,
            "recall_hit": exp_hsn in codes,
            "rank": rank,
            "prediction_mode": mode,
            "final_hsn": final_hsn,
            "exact_hit": mode == "EXACT_HSN" and final_hsn == exp_hsn,
            "false_exact": mode == "EXACT_HSN" and final_hsn != exp_hsn,
            "correctly_abstained": (mode != "EXACT_HSN") or (final_hsn == exp_hsn),
            "latency_ms": dt,
            "reranking_time_ms": exec_m.get("reranking_time_ms", 0.0),
        })

    n = len(per_case)
    lats = [r["latency_ms"] for r in per_case]
    rets = [r["retained_8digit"] for r in per_case]
    summary = {
        "total_cases": n,
        "zero_hsn_leakage_verified": True,
        "zero_query_leakage_verified": True,
        "chapter_accuracy_pct": round(100.0 * sum(1 for r in per_case if r["chapter_hit"]) / n, 2),
        "candidate_recall_pct": round(100.0 * sum(1 for r in per_case if r["recall_hit"]) / n, 2),
        "recall_at_5_pct": round(100.0 * sum(1 for r in per_case if r["rank"] and r["rank"] <= 5) / n, 2),
        "recall_at_10_pct": round(100.0 * sum(1 for r in per_case if r["rank"] and r["rank"] <= 10) / n, 2),
        "top1_pct": round(100.0 * sum(1 for r in per_case if r["rank"] == 1) / n, 2),
        "same_heading_precision_pct": round(100.0 * sum(r["same_h4"] for r in per_case) / max(sum(rets), 1), 2),
        "exact_hsn_hits": sum(1 for r in per_case if r["exact_hit"]),
        "exact_hsn_accuracy_pct": round(100.0 * sum(1 for r in per_case if r["exact_hit"]) / n, 2),
        "false_exact_count": sum(1 for r in per_case if r["false_exact"]),
        "correct_abstention_pct": round(100.0 * sum(1 for r in per_case if r["correctly_abstained"]) / n, 2),
        "mean_retained": round(statistics.mean(rets), 2),
        "median_retained": round(statistics.median(rets), 2),
        "p95_retained": round(float(np.percentile(rets, 95)), 2),
        "mean_latency_ms": round(statistics.mean(lats), 1),
        "p95_latency_ms": round(float(np.percentile(lats, 95)), 1),
        "rerank_pair_cache_hits": eng.classifier.reranker.pair_cache_hits,
        "rerank_pair_cache_misses": eng.classifier.reranker.pair_cache_misses,
        "cases": per_case,
    }
    out = ROOT / "reports" / "phase17_independent_100.json"
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("Saved", out)
    print({k: v for k, v in summary.items() if k != "cases"})


if __name__ == "__main__":
    main()

