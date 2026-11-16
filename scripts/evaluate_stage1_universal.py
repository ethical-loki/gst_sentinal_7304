"""
scripts/evaluate_stage1_universal.py
====================================
Task 10 & 11 — Universal Dynamic Stage 1 Evaluation & Latency Benchmark.
Evaluates 20 diverse descriptions across all required categories (electrical, mechanical,
spare parts, textiles, food, plastics, iron/steel, vehicles, furniture, multi-component,
abbreviations, missing attributes, ambiguous, unseen terminology) including the VFD diagnostic.
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.nlp.product_intent_analyzer import analyze_product_intent


STAGE1_EVAL_CASES: List[Dict[str, Any]] = [
    {"cat": "electrical_abbrev", "q": "Variable Frequency Drive (VFD) for controlling AC motor speed", "exp_art": "variable frequency drive", "exp_alias": "VFD", "exp_mat": None, "exp_fn": "controlling ac motor speed"},
    {"cat": "electrical_power", "q": "3-phase 100 kVA diesel generating set with control panel", "exp_art": "diesel generating set", "exp_alias": None, "exp_mat": None, "exp_fn": None},
    {"cat": "electrical_unseen", "q": "Uninterruptible Power Supply (UPS) 5 kVA for server backup", "exp_art": "uninterruptible power supply", "exp_alias": "UPS", "exp_mat": None, "exp_fn": "server backup"},
    {"cat": "mechanical_multi", "q": "Stainless steel centrifugal pump fitted with 5 HP electric motor for water supply", "exp_art": "centrifugal pump", "exp_alias": None, "exp_mat": "stainless steel", "exp_fn": "water supply"},
    {"cat": "mechanical_cnc", "q": "Programmable Logic Controller (PLC) module for industrial automation", "exp_art": "programmable logic controller", "exp_alias": "PLC", "exp_mat": None, "exp_fn": "industrial automation"},
    {"cat": "spare_parts", "q": "spare parts for marine outboard engine", "exp_art": "marine outboard engine", "exp_alias": None, "exp_mat": None, "exp_fn": "marine outboard engine"},
    {"cat": "spare_parts", "q": "replacement impeller made of cast iron for centrifugal pump", "exp_art": "replacement impeller", "exp_alias": None, "exp_mat": "cast iron", "exp_fn": "centrifugal pump"},
    {"cat": "textiles", "q": "knitted cotton t-shirt with polyester collar in retail pouch", "exp_art": "t-shirt", "exp_alias": None, "exp_mat": "cotton", "exp_fn": None},
    {"cat": "textiles_missing", "q": "women tailored winter overcoat", "exp_art": "overcoat", "exp_alias": None, "exp_mat": None, "exp_fn": None},
    {"cat": "food", "q": "instant noodles made from wheat flour with spice sachet in retail packet", "exp_art": "instant noodles", "exp_alias": None, "exp_mat": "wheat flour", "exp_fn": None},
    {"cat": "food", "q": "sweet biscuits containing cocoa", "exp_art": "sweet biscuits", "exp_alias": None, "exp_mat": None, "exp_fn": None},
    {"cat": "plastics", "q": "high-density polyethylene (HDPE) jerrycan for chemical transport", "exp_art": "jerrycan", "exp_alias": "HDPE", "exp_mat": "polyethylene", "exp_fn": "chemical transport"},
    {"cat": "plastics_form", "q": "polypropylene granules in primary forms", "exp_art": "polypropylene granules", "exp_alias": None, "exp_mat": "polypropylene", "exp_fn": None},
    {"cat": "steel", "q": "304 grade seamless stainless steel boiler tubes, 25mm OD, for heat exchanger", "exp_art": "boiler tubes", "exp_alias": None, "exp_mat": "stainless steel", "exp_fn": "heat exchanger"},
    {"cat": "vehicles", "q": "automotive safety airbag module fitted with pyrotechnic inflator for passenger car", "exp_art": "airbag", "exp_alias": None, "exp_mat": None, "exp_fn": "passenger car"},
    {"cat": "furniture", "q": "wooden swivel office chair with pneumatic height adjustment", "exp_art": "office chair", "exp_alias": None, "exp_mat": "wood", "exp_fn": None},
    {"cat": "ambiguous", "q": "plastic storage container with fitted lid", "exp_art": "storage container", "exp_alias": None, "exp_mat": "plastic", "exp_fn": None},
    {"cat": "missing_attr", "q": "centrifugal pump", "exp_art": "centrifugal pump", "exp_alias": None, "exp_mat": None, "exp_fn": None},
    {"cat": "parenthetical", "q": "rotary screw air compressor (15 kW) for pneumatic tools", "exp_art": "air compressor", "exp_alias": None, "exp_mat": None, "exp_fn": "pneumatic tools"},
    {"cat": "unseen_multi", "q": "Automated Optical Inspection (AOI) machine equipped with high-resolution camera for PCB defect detection", "exp_art": "automated optical inspection", "exp_alias": "AOI", "exp_mat": None, "exp_fn": "pcb defect detection"},
]


def main() -> None:
    lats: List[float] = []
    art_hits = 0
    alias_checks = 0
    alias_hits = 0
    mat_sep_ok = 0
    fn_checks = 0
    fn_hits = 0
    rel_checks = 0
    rel_hits = 0
    unsupported = 0
    missing_ok = 0
    missing_checks = 0
    rows: List[Dict[str, Any]] = []

    for idx, tc in enumerate(STAGE1_EVAL_CASES, start=1):
        t0 = time.perf_counter()
        pi = analyze_product_intent(tc["q"])
        dt = (time.perf_counter() - t0) * 1000.0
        lats.append(dt)

        art_ok = tc["exp_art"] in pi.finished_article.lower()
        if art_ok:
            art_hits += 1

        if tc["exp_alias"]:
            alias_checks += 1
            if tc["exp_alias"] in pi.alternative_names_and_aliases and tc["exp_alias"] not in pi.constituent_materials:
                alias_hits += 1

        mats_low = " ".join(pi.constituent_materials).lower()
        if tc["exp_mat"] is None:
            # Must not hallucinate a material when unstated (and never put alias/product in materials)
            if not pi.constituent_materials:
                mat_sep_ok += 1
            else:
                unsupported += 1
            missing_checks += 1
            if "material" in pi.missing_critical_attributes:
                missing_ok += 1
        else:
            if tc["exp_mat"] in mats_low:
                mat_sep_ok += 1

        if tc["exp_fn"]:
            fn_checks += 1
            if pi.function_use and tc["exp_fn"] in pi.function_use.lower():
                fn_hits += 1
            rel_checks += 1
            if any(r["relation"] in ("CONTROLS", "USED_FOR", "PERFORMS_FUNCTION") for r in pi.relationship_graph):
                rel_hits += 1

        rows.append({
            "id": idx,
            "category": tc["cat"],
            "query": tc["q"],
            "finished_article": pi.finished_article,
            "aliases": pi.alternative_names_and_aliases,
            "materials": pi.constituent_materials,
            "components": pi.components_or_parts,
            "function_use": pi.function_use,
            "function_details": pi.function_details,
            "missing_critical": pi.missing_critical_attributes,
            "rel_graph_edges": len(pi.relationship_graph),
            "latency_ms": round(dt, 3),
            "art_ok": art_ok,
        })

    n = len(STAGE1_EVAL_CASES)
    summary = {
        "n_cases": n,
        "product_identity_accuracy_pct": round(100.0 * art_hits / n, 2),
        "alias_extraction_accuracy_pct": round(100.0 * alias_hits / max(alias_checks, 1), 2),
        "material_vs_component_separation_pct": round(100.0 * mat_sep_ok / n, 2),
        "function_extraction_accuracy_pct": round(100.0 * fn_hits / max(fn_checks, 1), 2),
        "relationship_extraction_accuracy_pct": round(100.0 * rel_hits / max(rel_checks, 1), 2),
        "unsupported_inference_rate_pct": round(100.0 * unsupported / n, 2),
        "missing_info_handling_pct": round(100.0 * missing_ok / max(missing_checks, 1), 2),
        "mean_stage1_latency_ms": round(statistics.mean(lats), 2),
        "p95_stage1_latency_ms": round(float(sorted(lats)[int(0.95 * n) - 1]), 2),
        "cases": rows,
    }
    out = ROOT / "reports" / "stage1_universal_eval.json"
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print({k: v for k, v in summary.items() if k != "cases"})


if __name__ == "__main__":
    main()

