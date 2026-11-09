"""
Module: src/ml/deepseek_description_enricher.py
Description: Controlled AI-based product description enrichment and fact-grounding validation
             powered by DeepSeek (Prompt ID: HSN_DESCRIPTION_ENRICHMENT v1.0.0).

Strictly improves incomplete descriptions using ONLY original customer text and customer-confirmed
clarification answers, with zero hallucination of grades, dimensions, or unconfirmed specs.
"""

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Set, Tuple
from pydantic import BaseModel, Field

logger = logging.getLogger("gst_sentinel.description_enricher")
logger.setLevel(logging.INFO)

PROMPT_ID = "HSN_DESCRIPTION_ENRICHMENT"
PROMPT_VERSION = "1.0.0"
SCHEMA_VERSION = "1.0"

SYSTEM_PROMPT = """You are a product-description enrichment assistant for an HSN classification workflow.

Your task is to improve the clarity and completeness of the supplied product description using only facts explicitly present in the original customer description and customer-confirmed clarification answers.

You must not infer, assume, invent or introduce additional product attributes.

If an attribute is unknown or unconfirmed, leave it unspecified.

Do not generate an HSN code, determine a tariff heading or make a classification decision.

Return only the requested structured JSON output.

### Output Schema:
{
  "schema_version": "1.0",
  "enrichment_status": "SUCCESS",
  "original_description": "Industrial pipe",
  "confirmed_attributes": {
    "material": "Stainless steel",
    "construction": "Seamless",
    "intended_use": "Industrial fluid transportation"
  },
  "enriched_description": "Seamless stainless-steel pipe intended for industrial fluid transportation.",
  "added_facts": [
    {
      "attribute": "material",
      "value": "Stainless steel",
      "source": "CUSTOMER_CONFIRMED_ANSWER"
    }
  ],
  "unsupported_facts_detected": [],
  "ready_for_reclassification": true
}

### Valid Example:
Input:
  Original: "Industrial pipe"
  Confirmed Answers: {"material": "Stainless steel", "construction": "Seamless"}
Output:
  Enriched: "Seamless stainless-steel industrial pipe."
  Added facts: material, construction.

### Invalid Example (REJECTED):
Input:
  Original: "Industrial pipe"
  Confirmed Answers: {"material": "Stainless steel"}
Output with Invented Specs:
  Enriched: "304-grade seamless stainless-steel pipe." -> INVALID! (Invented "304-grade" and "seamless" not in confirmed answers).
"""


class AddedFact(BaseModel):
    attribute: str
    value: str
    source: str = "CUSTOMER_CONFIRMED_ANSWER"


class EnrichmentOutput(BaseModel):
    schema_version: str = "1.0"
    enrichment_status: str  # SUCCESS, FAILED, MANUAL_REVIEW
    original_description: str
    confirmed_attributes: Dict[str, str] = Field(default_factory=dict)
    enriched_description: str
    added_facts: List[AddedFact] = Field(default_factory=list)
    unsupported_facts_detected: List[str] = Field(default_factory=list)
    ready_for_reclassification: bool = False
    validation_reason: Optional[str] = None


class FactGroundingValidator:
    """
    Deterministic fact-grounding validation layer.
    Ensures that every added fact in the enriched description is explicitly
    traceable to the original description or customer-confirmed answers.
    """

    FORBIDDEN_INVENTED_PATTERNS = [
        # Unauthorized specific grades
        r"\b(?:ss\s*)?(?:304|316|316l|304l|410|202|grade\s*\d+)\b",
        # Unauthorized dimensional / schedule specs
        r"\b(?:sch(?:edule)?\s*\d+|1\/2\s*inch|2\s*inch|dn\d+|pn\d+)\b",
        # Unauthorized standards
        r"\b(?:astm\s*[a-z0-9]+|din\s*\d+|is\s*\d+|en\s*\d+)\b",
        # Unauthorized manufacturing claims if not in confirmed
        r"\b(?:cold\s*drawn|hot\s*rolled|galvanized|forged|annealed)\b",
    ]

    @classmethod
    def validate(
        cls,
        original_desc: str,
        confirmed_attrs: Dict[str, str],
        enriched_desc: str,
        added_facts: List[Dict[str, Any]]
    ) -> Tuple[bool, List[str], str]:
        """
        Validates fact-grounding deterministically.
        Returns (is_valid, unsupported_facts, reason).
        """
        orig_clean = str(original_desc or "").strip().lower()
        enrich_clean = str(enriched_desc or "").strip().lower()
        unsupported = []

        if not enrich_clean:
            return False, ["EMPTY_ENRICHED_DESCRIPTION"], "Enriched description is empty."

        # Rule 1: Contradiction Check between Original and Confirmed
        for attr, val in confirmed_attrs.items():
            val_lower = str(val).lower()
            if "plastic" in orig_clean and "steel" in val_lower:
                return False, [f"CONTRADICTION_{attr.upper()}"], f"Contradiction: Original specifies plastic but confirmed {attr} is {val}."
            if "steel" in orig_clean and "plastic" in val_lower:
                return False, [f"CONTRADICTION_{attr.upper()}"], f"Contradiction: Original specifies steel but confirmed {attr} is {val}."

        # Rule 2: Check for invented specifications not present in sources
        allowed_source_text = f"{orig_clean} " + " ".join([str(v).lower() for v in confirmed_attrs.values()])
        for pat in cls.FORBIDDEN_INVENTED_PATTERNS:
            match_enrich = re.findall(pat, enrich_clean)
            if match_enrich:
                for match in match_enrich:
                    if not re.search(re.escape(match), allowed_source_text):
                        unsupported.append(f"UNSUPPORTED_SPECIFICATION: '{match}'")

        # Rule 3: Check construction claims (e.g. seamless / welded)
        for constr in ["seamless", "welded", "erw", "extruded"]:
            if constr in enrich_clean and constr not in allowed_source_text:
                unsupported.append(f"UNSUPPORTED_CONSTRUCTION: '{constr}'")

        # Rule 4: Verify declared added facts against actual confirmed answers
        for fact in added_facts:
            attr = fact.get("attribute", "")
            val = str(fact.get("value", "")).lower()
            source = fact.get("source", "")
            if source == "CUSTOMER_CONFIRMED_ANSWER":
                expected_val = str(confirmed_attrs.get(attr, "")).lower()
                if not expected_val or (expected_val not in val and val not in expected_val):
                    unsupported.append(f"UNCONFIRMED_ATTRIBUTE: {attr}='{val}'")

        if unsupported:
            return False, unsupported, f"Fact-grounding validation failed: {'; '.join(unsupported)}"

        return True, [], "All facts strictly grounded in customer-confirmed sources."


class DeepSeekDescriptionEnricher:
    """
    Controlled AI-based product description enrichment service.
    Uses DeepSeek to generate clean phrasing and validates against fact-grounding rules.
    """

    _instance: Optional["DeepSeekDescriptionEnricher"] = None

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY", "")
        self.model_name = "deepseek-chat"

    def _extract_confirmed_attributes(
        self,
        clarification_answers: List[Dict[str, Any]]
    ) -> Tuple[Dict[str, str], List[AddedFact]]:
        """
        Filters customer answers to extract ONLY valid, non-unknown confirmed attributes.
        """
        confirmed: Dict[str, str] = {}
        added_facts: List[AddedFact] = []

        for ans in clarification_answers:
            if not isinstance(ans, dict):
                continue
            is_unknown = bool(ans.get("is_unknown", False))
            opt_id = str(ans.get("selected_option_id", "")).upper()
            val = ans.get("selected_value")
            attr = str(ans.get("attribute", "")).strip().lower()

            # Ignore unknown answers per contract
            if is_unknown or opt_id == "OPT_UNKNOWN" or str(val).lower() == "unknown":
                continue

            # Free text or clean option string
            free_text = ans.get("free_text")
            final_val = str(free_text).strip() if (free_text and str(free_text).strip()) else str(val or "").strip()
            # Clean underscores
            final_val = final_val.replace("_", " ").title()

            if attr and final_val:
                confirmed[attr] = final_val
                added_facts.append(AddedFact(
                    attribute=attr,
                    value=final_val,
                    source="CUSTOMER_CONFIRMED_ANSWER"
                ))

        return confirmed, added_facts

    def _generate_deterministic_enrichment(
        self,
        original_desc: str,
        confirmed_attrs: Dict[str, str]
    ) -> str:
        """
        Generates a grammatically coherent, strictly grounded enriched description
        without fabricating any external specifications.
        """
        orig_clean = str(original_desc or "").strip()
        if not confirmed_attrs:
            return orig_clean

        # Extract standard components if confirmed
        material = confirmed_attrs.get("material") or confirmed_attrs.get("textile_material")
        construction = confirmed_attrs.get("construction")
        use = confirmed_attrs.get("intended_use") or confirmed_attrs.get("application")
        sorting = confirmed_attrs.get("sorting_state")
        power = confirmed_attrs.get("power_rating")

        parts = []

        # Construction prefix (e.g. "Seamless")
        if construction and construction.lower() not in orig_clean.lower():
            parts.append(construction.capitalize())

        # Sorting state (e.g. "Sorted")
        if sorting and sorting.lower() not in orig_clean.lower():
            parts.append(sorting.capitalize())

        # Material (e.g. "Stainless steel" or "Cotton")
        if material and material.lower() not in orig_clean.lower():
            parts.append(material)

        # Base product name
        parts.append(orig_clean.lower())

        # Power rating suffix (e.g. "5 HP")
        if power and power.lower() not in orig_clean.lower():
            parts.append(f"with power output of {power}")

        # Intended use suffix
        if use and use.lower() not in orig_clean.lower():
            parts.append(f"intended for {use.lower()}")

        # Any other confirmed attributes not yet included
        handled_keys = {"material", "textile_material", "construction", "intended_use", "application", "sorting_state", "power_rating"}
        for k, v in confirmed_attrs.items():
            if k not in handled_keys and v.lower() not in orig_clean.lower():
                parts.append(f"({k.replace('_', ' ')}: {v})")

        enriched = " ".join(parts).strip()
        # Clean formatting
        enriched = re.sub(r"\s+", " ", enriched)
        return enriched[0].upper() + enriched[1:] + ("." if not enriched.endswith(".") else "")

    def _call_deepseek_api(
        self,
        original_desc: str,
        confirmed_attrs: Dict[str, str]
    ) -> Optional[Dict[str, Any]]:
        """Calls DeepSeek API with HSN_DESCRIPTION_ENRICHMENT prompt contract."""
        if not self.api_key:
            return None

        try:
            import urllib.request
            url = "https://api.deepseek.com/chat/completions"
            user_msg = {
                "original_description": original_desc,
                "confirmed_attributes": confirmed_attrs,
            }
            req_body = json.dumps({
                "model": self.model_name,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(user_msg)}
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.0,
                "max_tokens": 500
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
                return json.loads(content)
        except Exception as e:
            logger.warning(f"DeepSeek enrichment API call failed: {e}. Falling back to deterministic engine.")
            return None

    def enrich_description(
        self,
        original_description: str,
        clarification_answers: Optional[List[Dict[str, Any]]] = None,
        confirmed_attributes: Optional[Dict[str, str]] = None
    ) -> EnrichmentOutput:
        """
        Main entry point for controlled product description enrichment.
        Fulfills all requirements of Day 16:
        - Extracts strictly confirmed attributes.
        - Generates clear grammatical enrichment.
        - Executes deterministic Fact-Grounding validation.
        - Rejects unsupported specifications or contradictions.
        """
        orig_desc = str(original_description or "").strip()
        if not orig_desc:
            return EnrichmentOutput(
                schema_version=SCHEMA_VERSION,
                enrichment_status="FAILED",
                original_description="",
                confirmed_attributes={},
                enriched_description="",
                added_facts=[],
                unsupported_facts_detected=["EMPTY_INPUT"],
                ready_for_reclassification=False,
                validation_reason="Original product description cannot be empty."
            )

        # Step 1: Extract confirmed attributes and added facts
        if confirmed_attributes is not None:
            confirmed = dict(confirmed_attributes)
            added_facts = [
                AddedFact(attribute=k, value=v, source="CUSTOMER_CONFIRMED_ANSWER")
                for k, v in confirmed.items()
            ]
        else:
            confirmed, added_facts = self._extract_confirmed_attributes(clarification_answers or [])

        # If no clarification answers confirmed, preserve original description exactly
        if not confirmed:
            return EnrichmentOutput(
                schema_version=SCHEMA_VERSION,
                enrichment_status="SUCCESS",
                original_description=orig_desc,
                confirmed_attributes={},
                enriched_description=orig_desc,
                added_facts=[],
                unsupported_facts_detected=[],
                ready_for_reclassification=True,
                validation_reason="No customer answers to add. Original description preserved."
            )

        # Step 2: Generate candidate enriched description (API or Deterministic)
        candidate_enriched = ""
        api_res = self._call_deepseek_api(orig_desc, confirmed)
        if api_res and isinstance(api_res, dict) and api_res.get("enriched_description"):
            candidate_enriched = str(api_res["enriched_description"]).strip()

        if not candidate_enriched:
            candidate_enriched = self._generate_deterministic_enrichment(orig_desc, confirmed)

        # Step 3: Critical Fact-Grounding Validation
        is_valid, unsupported, reason = FactGroundingValidator.validate(
            original_desc=orig_desc,
            confirmed_attrs=confirmed,
            enriched_desc=candidate_enriched,
            added_facts=[f.model_dump() for f in added_facts]
        )

        if not is_valid:
            # Fact-grounding failed: Preserve original description, do not reclassify
            status = "MANUAL_REVIEW" if any("CONTRADICTION" in u for u in unsupported) else "FAILED"
            return EnrichmentOutput(
                schema_version=SCHEMA_VERSION,
                enrichment_status=status,
                original_description=orig_desc,
                confirmed_attributes=confirmed,
                enriched_description=orig_desc,  # Preserved original
                added_facts=[],
                unsupported_facts_detected=unsupported,
                ready_for_reclassification=False,
                validation_reason=reason
            )

        return EnrichmentOutput(
            schema_version=SCHEMA_VERSION,
            enrichment_status="SUCCESS",
            original_description=orig_desc,
            confirmed_attributes=confirmed,
            enriched_description=candidate_enriched,
            added_facts=added_facts,
            unsupported_facts_detected=[],
            ready_for_reclassification=True,
            validation_reason=reason
        )


def get_deepseek_description_enricher() -> DeepSeekDescriptionEnricher:
    """Returns singleton instance of DeepSeekDescriptionEnricher."""
    if DeepSeekDescriptionEnricher._instance is None:
        DeepSeekDescriptionEnricher._instance = DeepSeekDescriptionEnricher()
    return DeepSeekDescriptionEnricher._instance

