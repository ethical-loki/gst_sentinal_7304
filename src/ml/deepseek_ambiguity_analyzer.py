"""
src/ml/deepseek_ambiguity_analyzer.py — DeepSeek-Powered HSN Ambiguity Analysis Engine.

Response Schema:
Schema version: 1.0.0
Model: DeepSeek (deepseek-chat / deepseek-reasoner)
Purpose: Identify insufficient, conflicting, or unclear product information that prevents
         reliable distinction between retrieved HSN candidates before making an unreliable classification.
"""

import os
import re
import json
import logging
from typing import Dict, Any, List, Optional
import urllib.request
import urllib.error

logger = logging.getLogger("gst_sentinel.deepseek_ambiguity")

SCHEMA_VERSION = "1.0.0"
ALLOWED_ACTIONS = {"CONTINUE_VERIFICATION", "REQUEST_CLARIFICATION", "MANUAL_REVIEW"}

SYSTEM_PROMPT = """You are an HSN Product Ambiguity Analysis Assistant.

Your responsibility is to examine a customer's original product description, available product attributes and retrieved HSN candidates.

Your task is ONLY to identify whether the available information is sufficient to distinguish the supplied HSN candidates.

You are NOT responsible for independently deciding or approving the final HSN classification.

### 1. Analysis responsibilities

Identify the following categories:

A. Missing attributes
Identify important product attributes that have not been supplied (material, composition, grade, application, condition, dimensions, specifications).
Do not report every absent attribute. Report only attributes that are relevant to distinguishing the supplied candidates.

B. Conflicting facts
Identify contradictions between supplied product information (e.g. description says stainless steel, attribute says carbon steel).
Do not assume which conflicting value is correct.

C. Unclear terminology
Identify words or expressions that could have multiple technical or commercial meanings (e.g. Rags, Pipe, Motor, Parts, Scrap, Components).
Explain the possible interpretations only when supported by the supplied context.

D. Candidate distinction
Identify which retrieved candidate IDs are affected, what distinguishes them, and whether available information is sufficient to continue verification.
Only refer to candidate IDs included in the input.

### 2. Strict constraints

1. Never invent HSN codes or candidate descriptions.
2. Never create additional HSN candidates.
3. Never assume missing product attributes.
4. Never resolve conflicting facts by selecting one value without evidence.
5. Never treat a product name alone as proof of its material, function or intended use.
6. Never change the original customer description.
7. Never approve an HSN classification through ambiguity analysis.
8. Do not treat retrieval scores as proof of classification correctness.
9. Do not request clarification for irrelevant missing attributes.
10. If candidate information is insufficient, explicitly report that the distinction cannot be established.
11. If no candidates are supplied, report that candidate comparison cannot be performed.
12. If the input is invalid or incomplete, report the limitation rather than fabricating an analysis.

### 3. Allowed actions
- CONTINUE_VERIFICATION: No material ambiguity prevents the existing HSN verification process from continuing.
- REQUEST_CLARIFICATION: Relevant product information is missing, conflicting or unclear, and customer input could resolve the distinction. Requires at least one clarification question.
- MANUAL_REVIEW: Candidate information or available evidence is insufficient for reliable automated analysis, or the issue requires specialist review.

Do not interpret CONTINUE_VERIFICATION as HSN approval.

### 4. Output requirements

Return valid JSON only adhering strictly to this schema:
{
  "schema_version": "1.0.0",
  "is_ambiguous": true,
  "ambiguity_reason": "The product description does not specify the material required to distinguish the retrieved candidates.",
  "missing_attributes": [
    "material",
    "intended_use"
  ],
  "conflicting_facts": [],
  "unclear_terminology": [],
  "clarification_questions": [
    "What material is the product made from?",
    "What is the intended application of the product?"
  ],
  "affected_candidates": [
    "CAND_001",
    "CAND_002"
  ],
  "can_continue_verification": false,
  "recommended_action": "REQUEST_CLARIFICATION"
}

All 10 fields are required. Boolean fields must be true or false. Array fields must contain strings only."""


class DeepSeekAmbiguityAnalyzer:
    """
    Analyzes commercial product queries against retrieved HSN candidates for ambiguity
    before making an unreliable classification decision.
    Adheres strictly to Response Schema version 1.0.0.
    """
    _instance: Optional["DeepSeekAmbiguityAnalyzer"] = None

    def __init__(self):
        self.api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()

    @classmethod
    def get_instance(cls) -> "DeepSeekAmbiguityAnalyzer":
        if cls._instance is None:
            cls._instance = DeepSeekAmbiguityAnalyzer()
        return cls._instance

    def analyze_ambiguity(
        self,
        original_description: str,
        extracted_attributes: Optional[Dict[str, Any]] = None,
        retrieved_candidates: Optional[List[Dict[str, Any]]] = None,
        normalized_description: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes DeepSeek Ambiguity Analysis adhering strictly to Response Schema version 1.0.0.
        """
        desc_clean = (original_description or "").strip()
        candidates = retrieved_candidates or []
        attrs = extracted_attributes or {}
        norm_desc = normalized_description or desc_clean.lower()

        # Input validation: Empty query
        if not desc_clean:
            return self._build_contract_response(
                is_ambiguous=True,
                ambiguity_reason="Original product description is empty; classification cannot proceed.",
                missing_attributes=["product_description"],
                conflicting_facts=[],
                unclear_terminology=[],
                clarification_questions=["Please provide a valid commercial product description."],
                affected_candidates=[],
                can_continue_verification=False,
                recommended_action="REQUEST_CLARIFICATION"
            )

        # Rule 11: If no candidates are supplied, report that comparison cannot be performed
        if not candidates:
            return self._build_contract_response(
                is_ambiguous=True,
                ambiguity_reason="No retrieved HSN candidates were supplied; candidate comparison cannot be performed.",
                missing_attributes=[],
                conflicting_facts=[],
                unclear_terminology=[],
                clarification_questions=[],
                affected_candidates=[],
                can_continue_verification=False,
                recommended_action="MANUAL_REVIEW"
            )

        # Attempt Cloud DeepSeek API call if key is configured
        api_result = self._call_deepseek_api(desc_clean, norm_desc, attrs, candidates)
        if api_result is not None:
            validated = self._validate_and_sanitize_response(api_result, candidates)
            if validated is not None:
                return validated

        # Deterministic Offline Ambiguity Analyzer (Fallback adhering to Response Schema v1.0.0)
        return self._offline_ambiguity_analysis(desc_clean, norm_desc, attrs, candidates)

    def _build_contract_response(
        self,
        is_ambiguous: bool,
        ambiguity_reason: str,
        missing_attributes: List[str],
        conflicting_facts: List[str],
        unclear_terminology: List[str],
        clarification_questions: List[str],
        affected_candidates: List[str],
        can_continue_verification: bool,
        recommended_action: str
    ) -> Dict[str, Any]:
        """Builds and strictly enforces the Response Schema version 1.0.0 contract."""
        action = recommended_action.upper().strip()
        if action not in ALLOWED_ACTIONS:
            action = "MANUAL_REVIEW"

        # Validation Rule 6: REQUEST_CLARIFICATION requires at least one clarification question
        if action == "REQUEST_CLARIFICATION" and not clarification_questions:
            clarification_questions = ["Please provide additional technical specifications or constituent material details for this item."]

        return {
            "schema_version": SCHEMA_VERSION,
            "is_ambiguous": bool(is_ambiguous),
            "ambiguity_reason": str(ambiguity_reason or ""),
            "missing_attributes": [str(x) for x in missing_attributes if isinstance(x, (str, int, float))],
            "conflicting_facts": [str(x) for x in conflicting_facts if isinstance(x, (str, int, float))],
            "unclear_terminology": [str(x) for x in unclear_terminology if isinstance(x, (str, int, float))],
            "clarification_questions": [str(x) for x in clarification_questions if isinstance(x, (str, int, float))],
            "affected_candidates": [str(x) for x in affected_candidates if isinstance(x, (str, int, float))],
            "can_continue_verification": bool(can_continue_verification),
            "recommended_action": action
        }

    def _call_deepseek_api(
        self,
        orig_desc: str,
        norm_desc: str,
        attrs: Dict[str, Any],
        candidates: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip() or self.api_key
        if not api_key:
            return None

        # Format candidates with clear IDs
        cands_formatted = []
        for i, c in enumerate(candidates):
            cid = str(c.get("candidate_id") or c.get("hsn_code") or f"CAND_{i+1:03d}")
            cands_formatted.append({
                "candidate_id": cid,
                "hsn_code": str(c.get("hsn_code", "")),
                "official_description": str(c.get("description", c.get("official_description", "")))[:160],
                "hierarchical_text": str(c.get("hierarchical_text", ""))[:180],
                "chapter": str(c.get("chapter", "")),
                "heading": str(c.get("heading", c.get("hsn_4digit", ""))),
                "standard_rate": (float(c["standard_rate"]) if c.get("standard_rate") is not None else None)
            })

        user_content = json.dumps({
            "original_description": orig_desc,
            "normalized_description": norm_desc,
            "extracted_attributes": attrs,
            "retrieved_candidates": cands_formatted
        }, indent=2)

        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Analyze ambiguity for the following input:\n{user_content}"}
            ],
            "temperature": 0.0,
            "max_tokens": 500,
            "response_format": {"type": "json_object"}
        }

        req = urllib.request.Request(
            "https://api.deepseek.com/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }
        )

        try:
            with urllib.request.urlopen(req, timeout=12) as response:
                res_data = json.loads(response.read().decode("utf-8"))
                choice = res_data["choices"][0]["message"]["content"]
                parsed = json.loads(choice)
                return parsed
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError, Exception) as e:
            logger.warning(f"DeepSeek Ambiguity API invocation failed or timed out: {e}")
            return None

    def _validate_and_sanitize_response(
        self,
        parsed: Dict[str, Any],
        candidates: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Strict validation against all 10 rules of Response Schema version 1.0.0."""
        try:
            if not isinstance(parsed, dict):
                return None

            # Rule 1: All required fields must exist
            required_keys = [
                "schema_version", "is_ambiguous", "ambiguity_reason", "missing_attributes",
                "conflicting_facts", "unclear_terminology", "clarification_questions",
                "affected_candidates", "can_continue_verification", "recommended_action"
            ]
            for k in required_keys:
                if k not in parsed:
                    # Backward compatibility fallback if model returned previous property names
                    if k == "is_ambiguous" and "ambiguity_detected" in parsed:
                        parsed["is_ambiguous"] = parsed["ambiguity_detected"]
                    elif k == "can_continue_verification" and "can_distinguish_candidates" in parsed:
                        parsed["can_continue_verification"] = parsed["can_distinguish_candidates"]
                    elif k == "schema_version" and "prompt_version" in parsed:
                        parsed["schema_version"] = parsed["prompt_version"]
                    elif k in ("conflicting_facts", "unclear_terminology", "clarification_questions", "affected_candidates", "missing_attributes"):
                        parsed[k] = []
                    else:
                        return None

            # Rule 4: Action validation
            action = str(parsed.get("recommended_action", "")).upper().strip()
            if action not in ALLOWED_ACTIONS:
                return None

            # Rule 8: Candidate IDs must come from actual input candidates
            valid_cand_ids = set()
            for i, c in enumerate(candidates):
                cid = str(c.get("candidate_id") or c.get("hsn_code") or f"CAND_{i+1:03d}")
                valid_cand_ids.add(cid)
                if c.get("hsn_code"):
                    valid_cand_ids.add(str(c.get("hsn_code")))

            raw_affected = parsed.get("affected_candidates") or []
            sanitized_affected = [str(cid) for cid in raw_affected if str(cid) in valid_cand_ids]

            # Rule 2 & 3: Type checks
            return self._build_contract_response(
                is_ambiguous=bool(parsed["is_ambiguous"]),
                ambiguity_reason=str(parsed.get("ambiguity_reason", "")),
                missing_attributes=[str(x) for x in parsed.get("missing_attributes", []) if isinstance(x, str)],
                conflicting_facts=[str(x) for x in parsed.get("conflicting_facts", []) if isinstance(x, str)],
                unclear_terminology=[str(x) for x in parsed.get("unclear_terminology", []) if isinstance(x, str)],
                clarification_questions=[str(x) for x in parsed.get("clarification_questions", []) if isinstance(x, str)],
                affected_candidates=sanitized_affected,
                can_continue_verification=bool(parsed["can_continue_verification"]),
                recommended_action=action
            )
        except Exception as e:
            logger.warning(f"Error validating DeepSeek ambiguity schema: {e}")
            return None

    def _offline_ambiguity_analysis(
        self,
        orig_desc: str,
        norm_desc: str,
        attrs: Dict[str, Any],
        candidates: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Deterministic statutory ambiguity analyzer adhering strictly to Response Schema v1.0.0.
        """
        q_lower = orig_desc.lower()
        words = set(re.findall(r"\b[a-z]{2,}\b", q_lower))

        # Format input candidate IDs
        cand_ids = []
        chapters = set()
        for idx, c in enumerate(candidates):
            cid = str(c.get("candidate_id") or c.get("hsn_code") or f"CAND_{idx+1:03d}")
            cand_ids.append(cid)
            chap = str(c.get("chapter", ""))
            if chap:
                chapters.add(chap)

        # -------------------------------------------------------------------------
        # Category A & C: Unclear Terminology & Missing Attributes
        # -------------------------------------------------------------------------

        # 1. Generic term: "Rags"
        if "rags" in words or "rag" in words:
            has_textile_spec = any(w in words for w in ["cotton", "synthetic", "wool", "silk", "nylon", "polyester", "worn", "clothing"])
            has_sorting_spec = any(w in words for w in ["sorted", "unsorted", "scrap", "new", "used", "wiping"])

            if not has_textile_spec or not has_sorting_spec:
                missing = []
                questions = []
                if not has_textile_spec:
                    missing.append("textile_material")
                    questions.append("What is the textile material composition (e.g., cotton, synthetic, or wool)?")
                if not has_sorting_spec:
                    missing.append("sorting_state")
                    questions.append("Are these rags sorted or unsorted?")

                return self._build_contract_response(
                    is_ambiguous=True,
                    ambiguity_reason="The product description 'Rags' does not specify sorting state or textile material required to distinguish Chapter 63 tariff lines.",
                    missing_attributes=missing,
                    conflicting_facts=[],
                    unclear_terminology=["Rags"],
                    clarification_questions=questions,
                    affected_candidates=cand_ids[:2],
                    can_continue_verification=False,
                    recommended_action="REQUEST_CLARIFICATION"
                )

        # 2. Material Ambiguity: "Industrial pipe"
        is_pipe = ("pipe" in words or "pipes" in words or "tubing" in words)
        has_material = any(w in words for w in [
            "steel", "iron", "copper", "brass", "pvc", "plastic", "hdpe",
            "aluminium", "aluminum", "rubber", "concrete", "ss", "gi", "ms"
        ]) or bool(attrs.get("material"))

        if is_pipe and not has_material:
            return self._build_contract_response(
                is_ambiguous=True,
                ambiguity_reason="The product description does not specify the material required to distinguish between iron/steel (Ch 73), copper (Ch 74), or plastic (Ch 39) pipes.",
                missing_attributes=["material"],
                conflicting_facts=[],
                unclear_terminology=["pipe"],
                clarification_questions=["What material is the product made from (e.g., stainless steel, mild steel, PVC/plastic, or copper)?"],
                affected_candidates=cand_ids[:2],
                can_continue_verification=False,
                recommended_action="REQUEST_CLARIFICATION"
            )

        # 3. Specification Ambiguity: "Industrial motor" without power rating
        is_motor = ("motor" in words or "motors" in words) and not any(w in words for w in ["vehicle", "car", "bike", "cycle"])
        has_power_spec = any(w in words for w in ["kw", "hp", "watt", "watts", "w", "kva", "v", "volt", "volts", "phase", "rpm", "servo", "stepper"]) or bool(attrs.get("power_rating"))

        if is_motor and not has_power_spec:
            return self._build_contract_response(
                is_ambiguous=True,
                ambiguity_reason="The product description does not specify the power output rating required to distinguish Heading 8501 subheadings.",
                missing_attributes=["power_rating", "phase_specification"],
                conflicting_facts=[],
                unclear_terminology=["motor"],
                clarification_questions=["What is the rated power output (in HP or kW) and phase (single-phase or 3-phase) of the motor?"],
                affected_candidates=cand_ids[:2],
                can_continue_verification=False,
                recommended_action="REQUEST_CLARIFICATION"
            )

        # -------------------------------------------------------------------------
        # Category B: Conflicting Facts
        # -------------------------------------------------------------------------
        supplied_mat = str(attrs.get("material", "")).lower()
        if supplied_mat and ("stainless" in q_lower or "ss" in words) and ("carbon" in supplied_mat or "mild" in supplied_mat):
            return self._build_contract_response(
                is_ambiguous=True,
                ambiguity_reason="Contradiction between product description (stainless steel) and supplied material attribute (carbon/mild steel).",
                missing_attributes=[],
                conflicting_facts=[f"Product description indicates stainless steel, but supplied material attribute states '{supplied_mat}'."],
                unclear_terminology=[],
                clarification_questions=["Is the product manufactured from stainless steel or carbon/mild steel?"],
                affected_candidates=cand_ids[:2],
                can_continue_verification=False,
                recommended_action="REQUEST_CLARIFICATION"
            )

        # -------------------------------------------------------------------------
        # Category D: Candidate Conflict Across Unrelated Chapters
        # -------------------------------------------------------------------------
        if len(candidates) >= 2:
            c1, c2 = candidates[0], candidates[1]
            s1 = float(c1.get("score", 0.0))
            s2 = float(c2.get("score", 0.0))
            chap1 = str(c1.get("chapter", ""))
            chap2 = str(c2.get("chapter", ""))

            if chap1 and chap2 and chap1 != chap2 and abs(s1 - s2) < 0.04:
                return self._build_contract_response(
                    is_ambiguous=True,
                    ambiguity_reason=f"Retrieved candidates span competing statutory chapters ({chap1} vs {chap2}) with unresolved similarity scores.",
                    missing_attributes=["technical_function", "end_use"],
                    conflicting_facts=[],
                    unclear_terminology=[],
                    clarification_questions=[],
                    affected_candidates=[cand_ids[0], cand_ids[1]],
                    can_continue_verification=False,
                    recommended_action="MANUAL_REVIEW"
                )

        # -------------------------------------------------------------------------
        # Case A: Clear Product Description (Evidence is sufficient)
        # -------------------------------------------------------------------------
        return self._build_contract_response(
            is_ambiguous=False,
            ambiguity_reason=f"Product description '{orig_desc}' contains sufficient technical evidence to distinguish the supplied candidates.",
            missing_attributes=[],
            conflicting_facts=[],
            unclear_terminology=[],
            clarification_questions=[],
            affected_candidates=[],
            can_continue_verification=True,
            recommended_action="CONTINUE_VERIFICATION"
        )


def get_deepseek_ambiguity_analyzer() -> DeepSeekAmbiguityAnalyzer:
    """Singleton getter for DeepSeekAmbiguityAnalyzer."""
    return DeepSeekAmbiguityAnalyzer.get_instance()
