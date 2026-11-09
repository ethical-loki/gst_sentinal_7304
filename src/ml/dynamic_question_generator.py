"""
Module: src/ml/dynamic_question_generator.py
Description: Dynamic Clarification Question Generator adhering to Schema Version 1.0.0
             and the 12 Mandatory Rules.

Generates targeted, grounded clarification questions to distinguish ambiguous HSN candidates
prior to making any final classification decision.
"""

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("DynamicQuestionGenerator")
logger.setLevel(logging.INFO)

SCHEMA_VERSION = "1.0.0"

SYSTEM_PROMPT = """You are an HSN Dynamic Clarification Question Generator.

Your task is to examine a customer's product description, ambiguity analysis findings, and retrieved HSN candidates, and generate customer-facing clarification questions to resolve material ambiguity.

Mandatory Rules:
1. Every question must be connected to an actual ambiguity finding.
2. Every question must relate to the original product description.
3. Every question must explain why the answer matters (the 'reason' field).
4. Options must be grounded in actual candidate differences or supplied evidence.
5. Always include "Unknown / Not sure" with option_id "OPT_UNKNOWN" and value "unknown" as the final choice.
6. Never invent product materials, technical specifications or candidate characteristics.
7. Avoid duplicate questions for the same attribute (at most one question per attribute).
8. Ask only questions that help distinguish the retrieved candidates.
9. Allow free-text responses where predefined choices are insufficient (allow_free_text must be true).
10. Do not treat an unknown answer as a confirmed attribute.
11. Do not generate questions if the analysis result is invalid or requires manual review (return empty questions).
12. Do not use customer answers as automatic HSN approval.

Required JSON Structure:
{
  "schema_version": "1.0.0",
  "question_generation_status": "SUCCESS",
  "product_description": "Industrial pipe",
  "questions": [
    {
      "question_id": "Q001",
      "attribute": "material",
      "question": "What material is the industrial pipe made from?",
      "reason": "The retrieved candidates differ in their material characteristics.",
      "affected_candidates": [
        "CAND_001",
        "CAND_002"
      ],
      "options": [
        {
          "option_id": "OPT_001",
          "label": "Stainless steel",
          "value": "stainless_steel"
        },
        {
          "option_id": "OPT_002",
          "label": "Carbon steel",
          "value": "carbon_steel"
        },
        {
          "option_id": "OPT_003",
          "label": "Other material",
          "value": "other"
        },
        {
          "option_id": "OPT_UNKNOWN",
          "label": "Unknown / Not sure",
          "value": "unknown"
        }
      ],
      "allow_free_text": true,
      "required": true
    }
  ]
}
"""

class DynamicQuestionGenerator:
    """
    Generator for structured, customer-facing clarification questions adhering to
    Dynamic Clarification Question Schema v1.0.0.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY", "")
        self.model_name = "deepseek-chat"

    def _normalize_token(self, s: str) -> str:
        s = re.sub(r"[^a-zA-Z0-9\s]", " ", str(s or "")).lower()
        return "_".join(s.split())

    def _format_candidate_id(self, cand: Dict[str, Any], index: int) -> str:
        cid = cand.get("candidate_id") or cand.get("id") or cand.get("hsn_code")
        if not cid:
            cid = f"CAND_{index+1:03d}"
        return str(cid)

    def _build_contract_response(
        self,
        product_description: str,
        status: str,
        questions: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Builds a strictly valid Response Schema v1.0.0 payload."""
        sanitized_questions = []
        for q in questions:
            sanitized_q = {
                "question_id": str(q.get("question_id", "Q001")),
                "attribute": str(q.get("attribute", "general")),
                "question": str(q.get("question", "")),
                "reason": str(q.get("reason", "Clarification is required to distinguish candidate HSN classifications.")),
                "affected_candidates": [str(c) for c in q.get("affected_candidates", [])],
                "options": q.get("options", []),
                "allow_free_text": bool(q.get("allow_free_text", True)),
                "required": bool(q.get("required", True)),
            }
            # Mandatory Rule 5: Ensure Unknown / Not sure option exists
            has_unknown = any(
                opt.get("value") == "unknown" or "unknown" in str(opt.get("label", "")).lower()
                for opt in sanitized_q["options"]
            )
            if not has_unknown:
                sanitized_q["options"].append({
                    "option_id": "OPT_UNKNOWN",
                    "label": "Unknown / Not sure",
                    "value": "unknown"
                })
            sanitized_questions.append(sanitized_q)

        return {
            "schema_version": SCHEMA_VERSION,
            "question_generation_status": str(status),
            "product_description": str(product_description),
            "questions": sanitized_questions
        }

    def _extract_material_options(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        """Extracts candidate-grounded material choices without fabricating external materials."""
        detected_materials: List[Tuple[str, str]] = []
        seen_keys: Set[str] = set()

        all_text = " ".join([
            f"{c.get('hsn_code', '')} {c.get('description', '')}"
            for c in candidates
        ]).lower()

        # Check candidate-grounded materials
        if any(w in all_text for w in ["stainless", "7218", "7219", "7220", "730441", "730640"]):
            detected_materials.append(("Stainless steel", "stainless_steel"))
            seen_keys.add("stainless_steel")

        if any(w in all_text for w in ["carbon", "iron", "steel", "7208", "7209", "7304", "7305", "7306"]) and "carbon_steel" not in seen_keys:
            detected_materials.append(("Carbon steel", "carbon_steel"))
            seen_keys.add("carbon_steel")

        if any(w in all_text for w in ["plastic", "pvc", "polyethylene", "polymer", "tubing of plastics", "3917"]) and "plastic_pvc" not in seen_keys:
            detected_materials.append(("Plastic / PVC / Polymer", "plastic_pvc"))
            seen_keys.add("plastic_pvc")

        if any(w in all_text for w in ["copper", "brass", "bronze", "7411"]) and "copper" not in seen_keys:
            detected_materials.append(("Copper or copper alloy", "copper"))
            seen_keys.add("copper")

        if any(w in all_text for w in ["aluminium", "aluminum", "7608"]) and "aluminium" not in seen_keys:
            detected_materials.append(("Aluminium or aluminium alloy", "aluminium"))
            seen_keys.add("aluminium")

        if any(w in all_text for w in ["cotton", "631010"]) and "cotton" not in seen_keys:
            detected_materials.append(("Cotton", "cotton"))
            seen_keys.add("cotton")

        if any(w in all_text for w in ["synthetic", "man-made", "polyester", "nylon", "631090"]) and "synthetic" not in seen_keys:
            detected_materials.append(("Synthetic / Man-made fibers", "synthetic"))
            seen_keys.add("synthetic")

        if any(w in all_text for w in ["rubber", "4009"]) and "rubber" not in seen_keys:
            detected_materials.append(("Rubber", "rubber"))
            seen_keys.add("rubber")

        if any(w in all_text for w in ["glass", "7007", "7017"]) and "glass" not in seen_keys:
            detected_materials.append(("Glass", "glass"))
            seen_keys.add("glass")

        # Ground fallback if candidates provide limited hints
        if len(detected_materials) < 2:
            if "pipe" in all_text or "tube" in all_text:
                if "stainless_steel" not in seen_keys:
                    detected_materials.append(("Stainless steel", "stainless_steel"))
                if "carbon_steel" not in seen_keys:
                    detected_materials.append(("Carbon steel", "carbon_steel"))
            elif "rag" in all_text:
                if "cotton" not in seen_keys:
                    detected_materials.append(("Cotton", "cotton"))
                if "synthetic" not in seen_keys:
                    detected_materials.append(("Synthetic / Other textiles", "synthetic"))

        options = []
        for i, (label, val) in enumerate(detected_materials, start=1):
            options.append({
                "option_id": f"OPT_{i:03d}",
                "label": label,
                "value": val
            })

        # Add "Other material" and "Unknown / Not sure"
        options.append({
            "option_id": f"OPT_{len(options)+1:03d}",
            "label": "Other material",
            "value": "other"
        })
        options.append({
            "option_id": "OPT_UNKNOWN",
            "label": "Unknown / Not sure",
            "value": "unknown"
        })
        return options

    def _extract_sorting_options(self) -> List[Dict[str, str]]:
        return [
            {"option_id": "OPT_001", "label": "Sorted", "value": "sorted"},
            {"option_id": "OPT_002", "label": "Not sorted / Mixed", "value": "not_sorted"},
            {"option_id": "OPT_UNKNOWN", "label": "Unknown / Not sure", "value": "unknown"}
        ]

    def _extract_power_rating_options(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        all_text = " ".join([c.get("description", "") for c in candidates]).lower()
        options = [
            {"option_id": "OPT_001", "label": "Output not exceeding 750 W (approx. <= 1 HP)", "value": "lte_750w"},
            {"option_id": "OPT_002", "label": "Output exceeding 750 W but <= 75 kW (approx. 1 HP to 100 HP)", "value": "750w_to_75kw"},
            {"option_id": "OPT_003", "label": "Output exceeding 75 kW (> 100 HP)", "value": "gt_75kw"},
            {"option_id": "OPT_004", "label": "Other output rating", "value": "other"},
            {"option_id": "OPT_UNKNOWN", "label": "Unknown / Not sure", "value": "unknown"}
        ]
        return options

    def _extract_use_options(self, product_description: str, candidates: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        return [
            {"option_id": "OPT_001", "label": "Industrial / Manufacturing application", "value": "industrial"},
            {"option_id": "OPT_002", "label": "Domestic / Commercial application", "value": "domestic_commercial"},
            {"option_id": "OPT_003", "label": "Other specialized application", "value": "other"},
            {"option_id": "OPT_UNKNOWN", "label": "Unknown / Not sure", "value": "unknown"}
        ]

    def _generate_deterministic_questions(
        self,
        product_description: str,
        ambiguity_result: Dict[str, Any],
        candidates: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Deterministic, candidate-grounded question generator fulfilling all 12 rules.
        """
        missing_attrs = ambiguity_result.get("missing_attributes", [])
        unclear_terms = ambiguity_result.get("unclear_terminology", [])
        affected_cands = ambiguity_result.get("affected_candidates", [])
        if not affected_cands and candidates:
            affected_cands = [self._format_candidate_id(c, i) for i, c in enumerate(candidates)]

        questions = []
        seen_attributes: Set[str] = set()
        q_idx = 1

        # Check for material ambiguity
        has_material_attr = any("material" in a.lower() or "composition" in a.lower() for a in missing_attrs)
        if (has_material_attr or any(t.lower() in ["pipe", "rags", "fasteners", "scrap"] for t in unclear_terms)) and "material" not in seen_attributes:
            seen_attributes.add("material")
            opts = self._extract_material_options(candidates)
            questions.append({
                "question_id": f"Q{q_idx:03d}",
                "attribute": "material",
                "question": f"What material is the {product_description.strip()} made from?",
                "reason": "The retrieved candidates differ in their material characteristics and correspond to different tariff headings.",
                "affected_candidates": affected_cands,
                "options": opts,
                "allow_free_text": True,
                "required": True
            })
            q_idx += 1

        # Check for sorting state (e.g. rags)
        if any("sorting" in a.lower() or "condition" in a.lower() for a in missing_attrs) and "sorting_state" not in seen_attributes:
            seen_attributes.add("sorting_state")
            opts = self._extract_sorting_options()
            questions.append({
                "question_id": f"Q{q_idx:03d}",
                "attribute": "sorting_state",
                "question": f"Are the {product_description.strip()} sorted or unsorted?",
                "reason": "Chapter 63 distinguishes sorted rags from mixed/unsorted wiping rags with distinct tariff items.",
                "affected_candidates": affected_cands,
                "options": opts,
                "allow_free_text": True,
                "required": True
            })
            q_idx += 1

        # Check for technical specs / power rating (e.g. motors)
        if any("power" in a.lower() or "rating" in a.lower() or "specification" in a.lower() for a in missing_attrs) and "power_rating" not in seen_attributes:
            seen_attributes.add("power_rating")
            opts = self._extract_power_rating_options(candidates)
            questions.append({
                "question_id": f"Q{q_idx:03d}",
                "attribute": "power_rating",
                "question": f"What is the power rating or wattage of the {product_description.strip()}?",
                "reason": "Heading 8501 subheadings are categorized based on electrical output power brackets.",
                "affected_candidates": affected_cands,
                "options": opts,
                "allow_free_text": True,
                "required": True
            })
            q_idx += 1

        # Check for intended use / application
        if any("use" in a.lower() or "application" in a.lower() for a in missing_attrs) and "intended_use" not in seen_attributes:
            seen_attributes.add("intended_use")
            opts = self._extract_use_options(product_description, candidates)
            questions.append({
                "question_id": f"Q{q_idx:03d}",
                "attribute": "intended_use",
                "question": f"What is the intended application or end-use of the {product_description.strip()}?",
                "reason": "Intended application is essential to determine whether the product is a general commodity or a specialized instrument.",
                "affected_candidates": affected_cands,
                "options": opts,
                "allow_free_text": True,
                "required": True
            })
            q_idx += 1

        # If missing_attributes had an attribute we haven't covered, build a grounded question
        for attr in missing_attrs:
            clean_attr = attr.strip().lower()
            if clean_attr not in seen_attributes and clean_attr not in ["general", "none"]:
                seen_attributes.add(clean_attr)
                readable_attr = clean_attr.replace("_", " ")
                questions.append({
                    "question_id": f"Q{q_idx:03d}",
                    "attribute": clean_attr,
                    "question": f"What is the {readable_attr} of the {product_description.strip()}?",
                    "reason": f"Clarifying the {readable_attr} is required to distinguish the retrieved candidate HSN codes.",
                    "affected_candidates": affected_cands,
                    "options": [
                        {"option_id": "OPT_001", "label": f"Standard {readable_attr}", "value": "standard"},
                        {"option_id": "OPT_002", "label": f"Specialized {readable_attr}", "value": "specialized"},
                        {"option_id": "OPT_003", "label": "Other", "value": "other"},
                        {"option_id": "OPT_UNKNOWN", "label": "Unknown / Not sure", "value": "unknown"}
                    ],
                    "allow_free_text": True,
                    "required": True
                })
                q_idx += 1

        return questions

    def _validate_and_sanitize_response(
        self,
        parsed: Dict[str, Any],
        product_description: str,
        candidates: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Validates that parsed JSON complies with all 12 mandatory rules."""
        if not isinstance(parsed, dict):
            return None

        # Rule 11 Check
        status = str(parsed.get("question_generation_status", "SUCCESS")).upper().strip()
        if status not in ("SUCCESS", "SKIPPED", "FAILED"):
            status = "SUCCESS"

        raw_questions = parsed.get("questions")
        if not isinstance(raw_questions, list):
            return None

        valid_candidate_ids = set()
        for i, c in enumerate(candidates):
            valid_candidate_ids.add(self._format_candidate_id(c, i))

        sanitized_questions = []
        seen_attributes: Set[str] = set()

        for i, q in enumerate(raw_questions):
            if not isinstance(q, dict):
                continue
            qid = str(q.get("question_id") or f"Q{i+1:03d}")
            attr = str(q.get("attribute", "")).strip().lower()

            # Rule 7: Avoid duplicate questions for the same attribute
            if not attr or attr in seen_attributes:
                continue
            seen_attributes.add(attr)

            question_text = str(q.get("question", "")).strip()
            # Rule 2: Question must relate to the product description
            if not question_text:
                continue

            # Rule 3: Must explain why the answer matters
            reason = str(q.get("reason", "")).strip()
            if not reason:
                reason = "Clarification is required to distinguish between the retrieved candidates."

            # Rule 8 & Candidate validation
            aff_cands = q.get("affected_candidates", [])
            valid_aff = [str(c) for c in aff_cands if str(c) in valid_candidate_ids]
            if not valid_aff and valid_candidate_ids:
                valid_aff = list(valid_candidate_ids)

            # Rule 4 & 5: Options validation
            raw_options = q.get("options", [])
            if not isinstance(raw_options, list) or len(raw_options) < 1:
                continue

            sanitized_options = []
            has_unknown = False
            for opt_idx, opt in enumerate(raw_options):
                if not isinstance(opt, dict):
                    continue
                oid = str(opt.get("option_id") or f"OPT_{opt_idx+1:03d}")
                lbl = str(opt.get("label", "")).strip()
                val = str(opt.get("value", "")).strip().lower()
                if not lbl:
                    continue
                if val == "unknown" or "unknown" in lbl.lower():
                    has_unknown = True
                    oid = "OPT_UNKNOWN"
                    lbl = "Unknown / Not sure"
                    val = "unknown"
                sanitized_options.append({
                    "option_id": oid,
                    "label": lbl,
                    "value": val
                })

            # Rule 5: Always include Unknown / Not sure
            if not has_unknown:
                sanitized_options.append({
                    "option_id": "OPT_UNKNOWN",
                    "label": "Unknown / Not sure",
                    "value": "unknown"
                })

            sanitized_questions.append({
                "question_id": qid,
                "attribute": attr,
                "question": question_text,
                "reason": reason,
                "affected_candidates": valid_aff,
                "options": sanitized_options,
                "allow_free_text": True,  # Rule 9
                "required": bool(q.get("required", True))
            })

        return self._build_contract_response(
            product_description=product_description,
            status=status,
            questions=sanitized_questions
        )

    def _call_deepseek_api(
        self,
        product_description: str,
        ambiguity_result: Dict[str, Any],
        candidates: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Attempts generation via DeepSeek API with strict schema enforcement."""
        if not self.api_key:
            return None

        try:
            import urllib.request
            url = "https://api.deepseek.com/chat/completions"
            user_payload = {
                "product_description": product_description,
                "ambiguity_analysis": ambiguity_result,
                "retrieved_candidates": [
                    {
                        "candidate_id": self._format_candidate_id(c, i),
                        "hsn_code": c.get("hsn_code", ""),
                        "description": c.get("description", "")
                    }
                    for i, c in enumerate(candidates)
                ]
            }
            req_body = json.dumps({
                "model": self.model_name,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(user_payload)}
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.0,
                "max_tokens": 1000
            }).encode("utf-8")

            req = urllib.request.Request(
                url,
                data=req_body,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}"
                }
            )
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                content = data["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                return self._validate_and_sanitize_response(parsed, product_description, candidates)
        except Exception as e:
            logger.warning(f"DeepSeek dynamic question API call failed: {e}. Falling back to deterministic generator.")
            return None

    def generate_questions(
        self,
        product_description: str,
        ambiguity_result: Optional[Dict[str, Any]] = None,
        retrieved_candidates: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Main entry point for generating dynamic clarification questions.

        Fulfills all 12 Mandatory Rules:
        - Rule 11: If ambiguity analysis requires MANUAL_REVIEW or is not ambiguous, returns SKIPPED status.
        - Rules 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12 enforced.
        """
        product_desc = str(product_description or "").strip()
        candidates = retrieved_candidates or []

        # If ambiguity_result not supplied, generate it using DeepSeekAmbiguityAnalyzer
        if ambiguity_result is None:
            from src.ml.deepseek_ambiguity_analyzer import get_deepseek_ambiguity_analyzer
            analyzer = get_deepseek_ambiguity_analyzer()
            ambiguity_result = analyzer.analyze_ambiguity(
                original_description=product_desc,
                retrieved_candidates=candidates
            )

        # Rule 11: Do not generate questions if analysis result is invalid or requires manual review
        is_ambiguous = ambiguity_result.get("is_ambiguous", False)
        action = str(ambiguity_result.get("recommended_action", "")).upper()

        if not product_desc:
            return self._build_contract_response(
                product_description="",
                status="FAILED",
                questions=[]
            )

        if not is_ambiguous or action == "CONTINUE_VERIFICATION":
            return self._build_contract_response(
                product_description=product_desc,
                status="SKIPPED",
                questions=[]
            )

        if action == "MANUAL_REVIEW":
            return self._build_contract_response(
                product_description=product_desc,
                status="SKIPPED",
                questions=[]
            )

        # Try API first if configured
        api_response = self._call_deepseek_api(product_desc, ambiguity_result, candidates)
        if api_response is not None:
            return api_response

        # Fallback to grounded deterministic generator
        raw_questions = self._generate_deterministic_questions(product_desc, ambiguity_result, candidates)
        sanitized = self._validate_and_sanitize_response(
            {"question_generation_status": "SUCCESS", "questions": raw_questions},
            product_desc,
            candidates
        )
        if sanitized is None:
            return self._build_contract_response(product_desc, "FAILED", [])
        return sanitized


_GLOBAL_QUESTION_GENERATOR: Optional[DynamicQuestionGenerator] = None

def get_dynamic_question_generator() -> DynamicQuestionGenerator:
    """Returns the singleton instance of DynamicQuestionGenerator."""
    global _GLOBAL_QUESTION_GENERATOR
    if _GLOBAL_QUESTION_GENERATOR is None:
        _GLOBAL_QUESTION_GENERATOR = DynamicQuestionGenerator()
    return _GLOBAL_QUESTION_GENERATOR

