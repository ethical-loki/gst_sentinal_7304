"""
Counterfactual Generation Engine for HSN Misclassification: src/ml/counterfactual_generator.py
Simulates alternative candidate HSN codes from Day 05 retrieval through dynamic feature
recomputation and calibrated Day 06 re-scoring to surface the minimal corrective intervention
satisfying P(Error | h) < 0.05 without mutating draft invoice records.
"""

import copy
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd

from src.ml.explainability_engine import HSNExplainabilityEngine
from src.ml.misclassification_features import (
    FEATURE_COLUMNS,
    compute_token_entropy,
    extract_features,
    load_metadata_tables,
)
from src.ml.misclassification_scorer import HSNMisclassificationScorer

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_ARTIFACTS_DIR = ROOT_DIR / "artifacts"


class HSNCounterfactualGenerator:
    """
    Simulation engine testing candidate HSNs through feature recomputation and Day 06 re-scoring
    to find the minimal corrective intervention satisfying P(Error | h) < 0.05.
    """

    def __init__(
        self,
        scorer: Optional[HSNMisclassificationScorer] = None,
        explainer: Optional[HSNExplainabilityEngine] = None,
        artifacts_dir: Optional[Union[str, Path]] = None,
        safety_threshold: float = 0.05,
        flag_threshold: float = 0.15,
    ):
        self.artifacts_dir = Path(artifacts_dir or DEFAULT_ARTIFACTS_DIR)
        self.safety_threshold = float(safety_threshold)
        self.flag_threshold = float(flag_threshold)

        # Scorer & Explainer
        self.scorer = scorer or HSNMisclassificationScorer(artifacts_dir=self.artifacts_dir)
        self.explainer = explainer or HSNExplainabilityEngine(
            model=self.scorer.model,
            artifacts_dir=self.artifacts_dir,
            hsn_medians=self.scorer.hsn_medians,
            chapter_medians=self.scorer.chapter_medians,
            global_median_price=self.scorer.global_median_price,
        )

        # Cache metadata tables
        self.hsn_medians = self.scorer.hsn_medians
        self.chapter_medians = self.scorer.chapter_medians
        self.supplier_priors = self.scorer.supplier_priors
        self.global_median_price = self.scorer.global_median_price

    def _get_statutory_median(self, hsn_code: str) -> float:
        """Looks up the benchmark median unit price for an HSN code."""
        h_clean = str(hsn_code).strip()
        if h_clean in self.hsn_medians:
            return float(self.hsn_medians[h_clean])
        if len(h_clean) >= 4 and h_clean[:4] in self.hsn_medians:
            return float(self.hsn_medians[h_clean[:4]])
        chap = h_clean[:2] if len(h_clean) >= 2 else ""
        if chap in self.chapter_medians:
            return float(self.chapter_medians[chap])
        return float(self.global_median_price)

    def _normalize_candidates(self, candidates_input: Any) -> List[Dict[str, Any]]:
        """Standardizes candidates into a list of uniform dictionaries."""
        if candidates_input is None:
            return []

        candidates: List[Dict[str, Any]] = []
        raw_list = []
        if isinstance(candidates_input, list):
            raw_list = candidates_input
        elif isinstance(candidates_input, dict):
            raw_list = candidates_input.get("matches", candidates_input.get("candidates", [candidates_input]))
        elif hasattr(candidates_input, "matches"):
            raw_list = getattr(candidates_input, "matches")

        for item in raw_list:
            if isinstance(item, str):
                candidates.append({
                    "hsn_code": item.strip(),
                    "description": f"HSN {item.strip()}",
                    "score": 0.90,
                    "chapter": item.strip()[:2] if len(item.strip()) >= 2 else "00",
                })
            elif isinstance(item, dict):
                h_code = str(item.get("hsn_code", item.get("hsn", item.get("predicted_hsn", "")))).strip()
                score = float(item.get("score", item.get("similarity_score", 0.90)))
                desc = str(item.get("description", item.get("clean_description", f"HSN {h_code}"))).strip()
                chap = str(item.get("chapter", h_code[:2] if len(h_code) >= 2 else "00")).strip()
                candidates.append({
                    "hsn_code": h_code,
                    "description": desc,
                    "score": score,
                    "chapter": chap,
                    "raw": item,
                })
        return candidates

    def simulate_candidate(
        self,
        invoice_line: Dict[str, Any],
        candidate: Dict[str, Any],
        all_candidates: List[Dict[str, Any]],
        static_entropy: float,
        static_supplier_prior: float,
    ) -> Dict[str, Any]:
        """
        Simulates an alternative candidate HSN code h through feature recomputation
        and Day 06 calibrated re-scoring:
        1. Dynamic features: margin_top1_top2, chapter_match_flag (against vendor profile),
           and unit_price_deviation (against statutory median for candidate h).
        2. Query-level static features intact: token_entropy, supplier_prior_error_freq.
        3. Day 06 re-scoring: Calibrated P(Error | h).
        """
        cand_hsn = str(candidate["hsn_code"]).strip()
        cand_score = float(candidate.get("score", 0.90))
        cand_chapter = str(candidate.get("chapter", cand_hsn[:2])).zfill(2)

        # 1. Dynamic Feature: margin_top1_top2
        # Bound simulated margin to realistic retrieval distribution (median ~0.006, 95th pct ~0.048)
        if "margin" in candidate:
            margin = float(candidate["margin"])
        elif "margin_top1_top2" in candidate:
            margin = float(candidate["margin_top1_top2"])
        else:
            competing_scores = [
                float(c.get("score", 0.0))
                for c in all_candidates
                if str(c.get("hsn_code", "")).strip() != cand_hsn
            ]
            if competing_scores:
                best_comp = max(competing_scores)
                margin = min(0.04, max(0.005, abs(cand_score - best_comp)))
            else:
                margin = 0.015

        # 2. Dynamic Feature: chapter_match_flag
        # Under the corrective counterfactual intervention, adopting candidate h reclassifies the item
        # into candidate h's statutory chapter: h[:2] == h[:2] -> 1.0
        # (Candidate h must NOT be forced to match the original erroneous declared chapter!)
        chapter_match_flag = 1.0

        # 3. Dynamic Feature: unit_price_deviation against statutory median for candidate h
        unit_price = float(
            invoice_line.get("unit_price", invoice_line.get("price", invoice_line.get("rate", 0.0))) or 0.0
        )
        cand_median = self._get_statutory_median(cand_hsn)
        unit_price_deviation = abs(unit_price - cand_median) / (cand_median + 1e-5)

        # 4. Assemble updated feature vector
        feats_dict = {
            "top1_similarity_score": np.float32(cand_score),
            "margin_top1_top2": np.float32(margin),
            "chapter_match_flag": np.float32(chapter_match_flag),
            "token_entropy": np.float32(static_entropy),
            "unit_price_deviation": np.float32(unit_price_deviation),
            "supplier_prior_error_freq": np.float32(static_supplier_prior),
        }

        # 5. Model Inference through calibrated pipeline
        X = pd.DataFrame([[feats_dict[c] for c in FEATURE_COLUMNS]], columns=FEATURE_COLUMNS).astype(np.float32)
        scorer = self.scorer.calibrator if self.scorer.calibrator is not None else self.scorer.model
        prob_arr = scorer.predict_proba(X)
        error_prob = float(prob_arr[0, 1])
        error_prob = max(0.0, min(1.0, error_prob))

        return {
            "hsn_code": cand_hsn,
            "description": candidate.get("description", f"HSN {cand_hsn}"),
            "calibrated_error_probability": float(round(error_prob, 4)),
            "features": feats_dict,
            "statutory_median": cand_median,
        }

    def generate(
        self,
        invoice_line: Dict[str, Any],
        candidates: Any,
        safety_threshold: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Main optimization and counterfactual generation interface.
        Evaluates baseline risk, extracts Tree SHAP explanations, simulates alternative candidate HSNs,
        and surfaces the minimal corrective intervention satisfying P(Error | h) < 0.05.

        Adheres strictly to the read-only safety invariant: input invoice_line is never mutated.
        """
        # Read-Only Safety Invariant: deep copy input record upfront
        line_clean = copy.deepcopy(invoice_line)
        threshold = self.safety_threshold if safety_threshold is None else float(safety_threshold)

        norm_candidates = self._normalize_candidates(candidates)

        # 1. Baseline Evaluation on original line item & declared HSN
        baseline_risk = self.scorer.predict_risk(line_clean, norm_candidates)
        orig_prob = float(baseline_risk["error_probability"])
        orig_hsn = str(
            line_clean.get("declared_hsn")
            or baseline_risk.get("predicted_hsn")
            or (norm_candidates[0]["hsn_code"] if norm_candidates else "UNKNOWN")
        ).strip()
        orig_risk_level = baseline_risk["risk_level"]

        # Flag determination: flagged if error probability >= flag_threshold (0.15) or declared HSN diverges
        is_flagged = bool(orig_prob >= self.flag_threshold or orig_risk_level == "HIGH")

        # 2. Tree SHAP Explanations deconstruction
        explain_res = self.explainer.explain_prediction(
            invoice_line=line_clean,
            day5_retrieval_output=norm_candidates,
            features_dict=baseline_risk.get("features"),
        )
        explanations = explain_res.get("explanations", [])
        shap_values = explain_res.get("shap_values", {})

        # Extract static query features for simulation
        desc_text = (
            line_clean.get("product_description")
            or line_clean.get("clean_description")
            or line_clean.get("description")
            or ""
        )
        if "token_entropy" in line_clean and line_clean["token_entropy"] is not None:
            static_entropy = float(line_clean["token_entropy"])
        else:
            static_entropy = compute_token_entropy(desc_text)

        supplier_key = (
            line_clean.get("supplier_gstin")
            or line_clean.get("vendor_id")
            or line_clean.get("supplier_id")
        )
        static_supplier_prior = self.scorer.default_prior
        if supplier_key:
            s_clean = str(supplier_key).strip()
            if s_clean in self.supplier_priors:
                static_supplier_prior = self.supplier_priors[s_clean]

        # 3. Candidate Simulation & Optimization:
        # Counterfactual h* = argmin_{h in Candidates} P(Error | h) subject to P(Error | h) < 0.05
        simulated_results: List[Dict[str, Any]] = []
        for cand in norm_candidates:
            sim_item = self.simulate_candidate(
                invoice_line=line_clean,
                candidate=cand,
                all_candidates=norm_candidates,
                static_entropy=static_entropy,
                static_supplier_prior=static_supplier_prior,
            )
            simulated_results.append(sim_item)

        counterfactual_recommendation: Optional[Dict[str, Any]] = None
        suggested_action: Optional[Dict[str, Any]] = None

        if is_flagged:
            # Filter candidates satisfying P(Error | h) < 0.05
            safe_candidates = [
                item for item in simulated_results
                if item["calibrated_error_probability"] < threshold
            ]

            # Identify the primary statutory target chapter from retrieval (top candidate)
            target_chapter = norm_candidates[0]["chapter"] if norm_candidates else None

            # User-locked HSN anchor: the recommendation must stay on the HSN the user
            # highlighted. Price / chapter inputs only decide whether that HSN is safe as-is
            # (SAFE_REPLACEMENT_FOUND) or needs benchmark alignment (UNRESOLVED_MANUAL_REVIEW);
            # they must never swap in a different HSN that merely fits the price better.
            anchor_hsn = str(line_clean.get("locked_hsn") or "").strip()
            anchor_sim = next(
                (s for s in simulated_results if str(s["hsn_code"]).strip() == anchor_hsn),
                None,
            ) if anchor_hsn else None

            if anchor_sim is not None:
                best_cand = anchor_sim
                status_str = (
                    "SAFE_REPLACEMENT_FOUND"
                    if anchor_sim["calibrated_error_probability"] < threshold
                    else "UNRESOLVED_MANUAL_REVIEW"
                )
            elif safe_candidates:
                # If there are safe candidates matching the statutory chapter of the product, prioritize them!
                chapter_aligned_safe = [
                    c for c in safe_candidates 
                    if target_chapter and str(c["hsn_code"]).startswith(str(target_chapter))
                ]
                candidates_pool = chapter_aligned_safe if chapter_aligned_safe else safe_candidates

                # Prioritize highest semantic similarity to the product description, breaking ties by lowest error probability
                candidates_pool.sort(
                    key=lambda x: (-x["features"]["top1_similarity_score"], x["calibrated_error_probability"])
                )
                best_cand = candidates_pool[0]
                status_str = "SAFE_REPLACEMENT_FOUND"
            elif simulated_results:
                # Fallback: prioritize candidates matching statutory chapter, then lowest error probability
                simulated_results.sort(
                    key=lambda x: (
                        0 if (target_chapter and str(x["hsn_code"]).startswith(str(target_chapter))) else 1,
                        x["calibrated_error_probability"],
                        -x["features"]["top1_similarity_score"],
                    )
                )
                best_cand = simulated_results[0]
                status_str = "UNRESOLVED_MANUAL_REVIEW"
            else:
                best_cand = {
                    "hsn_code": orig_hsn,
                    "description": desc_text,
                    "calibrated_error_probability": orig_prob,
                }
                status_str = "UNRESOLVED_MANUAL_REVIEW"

            cand_prob = float(best_cand["calibrated_error_probability"])
            risk_drop = float(round(max(0.0, orig_prob - cand_prob), 4))

            counterfactual_recommendation = {
                "recommended_hsn": best_cand["hsn_code"],
                "description": best_cand["description"],
                "calibrated_error_probability": cand_prob,
                "risk_drop": risk_drop,
                "status": status_str,
            }

            if status_str == "SAFE_REPLACEMENT_FOUND":
                suggested_action = {
                    "action_type": "REPLACE_HSN",
                    "replacement_hsn": best_cand["hsn_code"],
                    "statutory_description": best_cand["description"],
                    "post_intervention_risk": cand_prob,
                    "risk_delta": risk_drop,
                    "explanation": (
                        f"One-click intervention: Reclassify item to HSN {best_cand['hsn_code']} "
                        f"to reduce audit risk by {risk_drop * 100:.1f}% (down to {cand_prob * 100:.1f}%)."
                    ),
                }
            else:
                suggested_action = {
                    "action_type": "MANUAL_INSPECTION",
                    "replacement_hsn": best_cand["hsn_code"],
                    "statutory_description": best_cand["description"],
                    "post_intervention_risk": cand_prob,
                    "risk_delta": risk_drop,
                    "explanation": (
                        "Intervention could not reduce risk below 5.0% statutory safety threshold. "
                        "Flagged for manual review by GST auditor."
                    ),
                }

        else:
            # AUTO_APPROVED: No intervention necessary
            suggested_action = {
                "action_type": "NO_ACTION_REQUIRED",
                "replacement_hsn": None,
                "statutory_description": None,
                "post_intervention_risk": orig_prob,
                "risk_delta": 0.0,
                "explanation": "No intervention required. Invoice item meets statutory auto-filing criteria.",
            }

        status_badge = "FLAGGED" if is_flagged else "AUTO_APPROVED"
        human_readable_reasons = (
            explanations if is_flagged else (baseline_risk.get("risk_factors") or ["✓ Item classification complies with statutory benchmarks. Safe to auto-file."])
        )

        return {
            "flagged": is_flagged,
            "status_badge": status_badge,
            "original_prediction": {
                "hsn": orig_hsn,
                "error_probability": orig_prob,
                "risk_level": orig_risk_level,
            },
            "explanations": explanations,
            "human_readable_reasons": human_readable_reasons,
            "counterfactual_recommendation": counterfactual_recommendation,
            "suggested_action": suggested_action,
            "shap_attributions": shap_values,
        }
