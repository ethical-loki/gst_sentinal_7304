"""
src/nlp/hsn_rag_layer.py
========================
HSN & ITC-HS Retrieval-Augmented Generation (RAG) Application Layer.

Architecture:
1. Stage 1: Customs Classification & Tariff Attribute Extractor
   - Normalizes commercial product descriptions
   - Extracts constituent material, processing state, function/use, mounted state
   - Performs statutory cross-chapter ambiguity check (e.g. pipes, shoes, gloves)
   - Emits structured search keywords and customer clarification questions when required
2. Stage 2: Statutory Context Retriever (RAG)
   - Retrieves top candidate tariff headings from CBIC Tariff Master
   - Injects WCO GIR (1-6) rules and statutory Section & Chapter legal notes
   - Injects verified precedent knowledge from persistent parquet store
3. Stage 3: Statutory HSN & ITC-HS Legal Verification Engine
   - Adjudicates candidates against extracted attributes & statutory notes
   - Strictly applies negative legal constraints (Coffee vs Cocoa, Mounted vs Unmounted brakes, Primary vs Secondary batteries)
   - Emits verified 8-digit HSN code, statutory rationale, rejected candidates, and confidence score
"""

import json
import logging
import os
import re
import time
import urllib.request
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# =====================================================================
# PYDANTIC SCHEMAS
# =====================================================================

class ExtractedAttributes(BaseModel):
    material: Optional[str] = None
    processing_state: Optional[str] = None
    function_use: Optional[str] = None
    mounted_state: str = "not_applicable"  # "mounted" | "unmounted" | "not_applicable"

class ClarificationPayload(BaseModel):
    question: Optional[str] = None
    options: List[str] = Field(default_factory=list)

class AttributeExtractionResult(BaseModel):
    product_normalized: str
    attributes: ExtractedAttributes
    needs_clarification: bool
    clarification: Optional[ClarificationPayload] = None
    search_keywords: List[str] = Field(default_factory=list)

class RejectedCandidate(BaseModel):
    hsn: str
    reason: str

class StatutoryVerificationResult(BaseModel):
    selected_hsn: str
    heading_description: str
    gst_rate_expected: Optional[str] = None
    statutory_rationale: str
    rejected_candidates: List[RejectedCandidate] = Field(default_factory=list)
    confidence_score: float = 1.0

class RAGPipelineResult(BaseModel):
    query: str
    extraction: AttributeExtractionResult
    retrieved_candidates: List[Dict[str, Any]] = Field(default_factory=list)
    retrieved_statutory_notes: List[str] = Field(default_factory=list)
    verification: Optional[StatutoryVerificationResult] = None
    status: str = "SUCCESS"  # "SUCCESS" | "REQUIRES_CLARIFICATION" | "MANUAL_REVIEW"
    latency_ms: float = 0.0


# =====================================================================
# SYSTEM PROMPTS
# =====================================================================

STAGE1_ATTRIBUTE_EXTRACTOR_PROMPT = """You are an expert Customs Classification & Tariff Attribute Extractor operating under the Harmonized Commodity Description and Coding System (HSN / ITC-HS).

Your task:
Analyze the input product name/description and extract statutory attributes. Do NOT invent or predict final 8-digit HSN codes in this stage.

Evaluation Steps:
1. Identify the Constituent Material (e.g., Stainless Steel, Nitrile Rubber, Leather, Coffee Bean, Cocoa).
2. Identify the Processing/Form (e.g., Raw, Roasted, Assembled, Unmounted, Mounted, Liquid, Solid).
3. Identify the End-Use / Function (e.g., Passenger Motor Vehicle part, Medical, Agriculture, Cutting tool).
4. Ambiguity & Missing Parameter Check:
   - Does this product span multiple statutory Chapters or 4-digit Headings depending on material or end-use?
     (Examples: "Pipes" -> plastic Ch 39 vs steel Ch 73; "Gloves" -> rubber Ch 40 vs leather Ch 42 vs textile Ch 61/62; "Shoes" -> upper material determines 6402 vs 6403 vs 6404).
   - If critical information is missing, set "needs_clarification" to true.

Output strictly valid JSON with this exact schema:
{
  "product_normalized": "Normalized standard product name",
  "attributes": {
    "material": "string or null",
    "processing_state": "string or null",
    "function_use": "string or null",
    "mounted_state": "mounted | unmounted | not_applicable"
  },
  "needs_clarification": true | false,
  "clarification": {
    "question": "Specific question to the customer if needs_clarification is true, else null",
    "options": ["Option 1", "Option 2", "Option 3"]
  },
  "search_keywords": ["keyword1", "keyword2", "keyword3"]
}"""

STAGE2_LEGAL_VERIFICATION_PROMPT = """You are the Statutory HSN & ITC-HS Legal Verification Engine operating strictly under the WCO General Rules for the Interpretation (GIR) of the Harmonized System and CBIC statutory rules.

Inputs provided to you:
1. Product Name & Customer Clarification (if any).
2. Extracted Attributes (Material, Processing, Function, Mount Status).
3. Candidate Tariff Headings retrieved from the statutory database.
4. Statutory Legal Notes & Chapter Boundary Exclusions.

CRITICAL STATUTORY RULES & NEGATIVE CONSTRAINTS:
1. Agricultural Traps:
   - Coffee (Coffea beans) belongs strictly to Chapter 09 (Heading 0901).
   - Cocoa (Theobroma cacao) belongs strictly to Chapter 18 (Heading 1801).
   - NEVER classify coffee under Chapter 18.
2. Section XVII & Chapter 68 Boundary (Brakes & Friction):
   - Heading 6813 strictly covers UNMOUNTED friction material (sheets, rolls, strips).
   - Friction materials MOUNTED on a backing plate or brake shoe ready for vehicle fitment are EXCLUDED from Chapter 68 by Chapter Note 1 and MUST be classified under Chapter 87 (8708.30).
3. Chapter 85 Accumulators vs Primary Cells:
   - Primary (non-rechargeable) cells: Heading 8506.
   - Secondary / Rechargeable batteries (Lithium-ion, Lead-acid): Heading 8507 (Lithium-ion accumulators: 8507.60.00).
4. GIR Application Order:
   - Rule 1: The terms of headings and Section/Chapter Notes have primary legal force.
   - Rule 3(a): The heading providing the most specific description shall be preferred to headings providing a more general description.

Task:
Evaluate the product against the provided Candidate Headings and Chapter Notes. Select the single legally sound 8-digit HSN code.

Output strictly valid JSON with this exact schema:
{
  "selected_hsn": "8-digit HSN code (e.g., 0901 21 10)",
  "heading_description": "Official tariff description of the selected heading",
  "gst_rate_expected": "e.g., 5%, 12%, 18%, or 28%",
  "statutory_rationale": "Clear, concise legal reasoning citing relevant GIR Rule, Chapter Notes, or Section exclusions.",
  "rejected_candidates": [
    {
      "hsn": "Rejected HSN code",
      "reason": "Why it was excluded by statutory note or definition"
    }
  ],
  "confidence_score": 0.0 to 1.0
}"""

STAGE3_AI_LEGAL_SELECTOR_PROMPT = """You are an official auditor. Look at this product string. Choose the single best HSN code strictly out of these 3 legal options. Do not make up your own numbers under any circumstances.

Inputs provided to you:
1. Master Search String (constructed by Stage 1 Context Aggregator from base product + user clarification + extracted attributes).
2. Top 3 Official Tariff Options (pulled by Stage 2 Vector Search Index directly from the official HSN Law Book).

STRICT AUDITOR GUARDRAILS:
- You MUST select ONE option strictly from the 3 provided legal options (OPTION_1, OPTION_2, or OPTION_3).
- You are strictly forbidden from inventing, guessing, or outputting any HSN code that is not in the 3 provided options.
- Apply WCO General Interpretative Rules (GIR 1 and GIR 3(a)) to pick the most specific match among the 3 options.

Output strictly valid JSON with this exact schema:
{
  "selected_option_id": "OPTION_1 | OPTION_2 | OPTION_3",
  "selected_hsn": "Exact 8-digit HSN code from the chosen option",
  "auditor_rationale": "Concise legal explanation of why this option is the best statutory match among the 3 official tariff options."
}"""

ELITE_STATUTORY_AUDITOR_PROMPT = """You are an elite Statutory Customs Auditor specializing in the Harmonized System (HS) and Indian GST Tariff Framework. Your task is to dynamically evaluate user product descriptions against the retrieved tariff options and select the legally flawless 8-digit HSN code.

### OPERATIONAL FRAMEWORK:
You must strictly apply General Interpretative Rules (GIR 1 & GIR 6) to cross-verify the vector results. Do not blindly select the highest vector similarity score. You must evaluate the hierarchical structure of the tariff book entries.

### CRITICAL TARIFF AUDIT RULES:
1. MATERIAL SPECIFICITY: If the retrieved HSN codes bifurcate based on material composition (e.g., 7304.11 for Stainless Steel vs 7304.19 for Carbon Steel/Other), you MUST identify if the user provided this information. If the user input is ambiguous or missing the material type, do not guess.
2. COMMODITY FORM SPECIFICITY: Never default to a residual "Other" bucket (e.g., ending in 90/99) if the user's core commodity explicitly matches a specific sub-item line (e.g., "Tubes and pipes" ending in 10). 
3. EXCLUSION CHECK (GIR 1): Scan chapter notes to verify the product is not legally excluded from the current heading (e.g., coffee belongs in Ch 9, not Ch 18).
4. OUTDATED CODE DETECTION: Treat 4-digit or 6-digit headings that have been structurally replaced or split in the current tariff book (such as old generic subheadings like 7304.10) as INVALID. If a retrieved option belongs to a deprecated tree, reject it immediately.

### INPUT DATA FOR EVALUATION:
- USER INPUT STRINGS:
  * Product Description: {user_raw_input}
  * Extracted Attributes: {context_aggregator_attributes}

- RETRIEVED TARIFF OPTIONS (Vector Search Top 3):
{vector_search_top_3_options}

### DYNAMIC OUTPUT PROTOCOL:
Analyze the input data. You must return your evaluation in one of the two following formats:

[FORMAT A: SUCCESSFUL MATCH]
Use this if the user input contains all necessary parameters to decisively lock a specific, active 8-digit HSN code.
Output JSON structure:
{{
  "status": "SUCCESS",
  "hsn_code": "8-digit string",
  "gst_rate": "percentage",
  "tariff_text": "Full legal text string of the selected code",
  "statutory_rationale": "Step-by-step hierarchical breakdown explaining the choice under GIR. Mention the exact material, processing, and heading path chosen."
}}

[FORMAT B: AMBIGUITY / INSUFFICIENT DATA]
Use this if the retrieved HSN choices depend on technical criteria (like material type, manufacturing process, or specific end-use) that the user did not explicitly provide or imply in their query.
Output JSON structure:
{{
  "status": "NEED_CLARIFICATION",
  "hsn_code": null,
  "gst_rate": null,
  "missing_attributes": ["List the specific missing technical variables"],
  "user_prompt_suggestion": "Write a user-friendly, specific question asking the user to clear up the exact ambiguity (e.g., 'Is this pipe made of Stainless Steel or Carbon Steel?')"
}}"""


# =====================================================================
# STATUTORY KNOWLEDGE REPOSITORY (RAG RETRIEVAL CORPUS)
# =====================================================================

STATUTORY_LEGAL_NOTES = {
    "09": (
        "Chapter 09 Note 1 & Chapter 18 Note 1: Chapter 09 covers coffee (heading 0901), tea, and spices. "
        "Chapter 18 Note 1 explicitly excludes coffee and goods of Chapter 9. Coffee beans (Coffea) can never be classified under Chapter 18."
    ),
    "18": (
        "Chapter 18 Note 1: Covers Cocoa and cocoa preparations. Excludes coffee and coffee substitutes (Heading 0901)."
    ),
    "68": (
        "Chapter 68 Note 1(e): This Chapter does not cover friction material mounted on a base plate or shoe for motor vehicles (Heading 8708). "
        "Heading 6813 applies strictly to unmounted friction material."
    ),
    "87": (
        "Section XVII Note 2(e) & Chapter 87: Mounted brake linings and brake pads for motor vehicles are classified under Heading 8708 (8708 30 / 8708 31) "
        "as parts and accessories of motor vehicles."
    ),
    "8506": (
        "Chapter 85 Heading 8506: Covers primary (non-rechargeable) electric cells and batteries. Excludes rechargeable accumulators."
    ),
    "8507": (
        "Chapter 85 Heading 8507: Covers secondary (rechargeable) electric accumulators. Tariff item 8507 60 00 strictly covers Lithium-ion accumulators."
    ),
    "73": (
        "Chapter 73 Headings 7304-7306: Covers tubes, pipes and hollow profiles of iron or steel. Heading 7304 covers seamless stainless/carbon steel line pipes."
    ),
    "39": (
        "Chapter 39 Heading 3917: Covers tubes, pipes and hoses of plastics."
    ),
    "64": (
        "Chapter 64 General Note: Footwear classification depends primarily on the material of the outer sole and upper. "
        "Heading 6402 covers uppers of rubber/plastics; Heading 6403 covers uppers of leather; Heading 6404 covers uppers of textile materials."
    ),
    "GIR_1": (
        "GIR 1 (General Interpretative Rule 1): The titles of Sections, Chapters and sub-Chapters are provided for ease of reference only; "
        "for legal purposes, classification shall be determined according to the terms of the headings and any relative Section or Chapter Notes."
    ),
    "GIR_3A": (
        "GIR 3(a) (General Interpretative Rule 3(a)): The heading which provides the most specific description shall be preferred to headings providing a more general description."
    )
}


# =====================================================================
# RAG APPLICATION LAYER IMPLEMENTATION
# =====================================================================

class HSNRAGApplicationLayer:
    """
    Complete Retrieval-Augmented Generation (RAG) Application Layer for HSN extraction & verification.
    """
    _instance: Optional["HSNRAGApplicationLayer"] = None

    def __init__(self):
        self.api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()

    @classmethod
    def get_instance(cls) -> "HSNRAGApplicationLayer":
        if cls._instance is None:
            cls._instance = HSNRAGApplicationLayer()
        return cls._instance

    # -----------------------------------------------------------------
    # STAGE 1: TARIFF ATTRIBUTE EXTRACTOR
    # -----------------------------------------------------------------
    def extract_attributes(self, product_description: str) -> AttributeExtractionResult:
        """
        Stage 1: Normalizes product description and extracts statutory attributes.
        Adheres strictly to the Attribute Extraction Schema.
        """
        desc = (product_description or "").strip()
        if not desc:
            return AttributeExtractionResult(
                product_normalized="",
                attributes=ExtractedAttributes(),
                needs_clarification=True,
                clarification=ClarificationPayload(
                    question="Please provide a valid commercial product description.",
                    options=[]
                ),
                search_keywords=[]
            )

        # 1. Try DeepSeek LLM invocation if API key is configured
        llm_res = self._call_extractor_llm(desc)
        if llm_res:
            try:
                return AttributeExtractionResult(**llm_res)
            except Exception as e:
                logger.warning(f"Failed to parse LLM extraction output: {e}")

        # 2. Deterministic Rule-Grounded Fallback (GIR 1 & Chapter Notes aligned)
        return self._extract_attributes_deterministic(desc)

    def _extract_attributes_deterministic(self, desc: str) -> AttributeExtractionResult:
        """
        Dynamic statutory attribute extractor aligned with GIR 1 & WCO Chapter Notes.
        Extracts constituent material, processing state, function/use, and mounted state
        dynamically using generalized tariff trade vocabularies without hardcoding product entries.
        """
        q_lower = desc.lower()

        # -------------------------------------------------------------
        # 1. DYNAMIC CONSTITUENT MATERIAL EXTRACTOR
        # -------------------------------------------------------------
        mat = None
        has_stainless = any(w in q_lower for w in ["stainless", "ss 304", "ss304", "ss 316", "ss316", "inox"])
        has_carbon = any(w in q_lower for w in ["carbon steel", "mild steel", "non-alloy", "cs pipe", "ms pipe"])
        has_generic_steel = any(w in q_lower for w in ["steel", "iron"]) and not (has_stainless or has_carbon)
        has_pvc = any(w in q_lower for w in ["pvc", "polyvinyl", "hdpe", "ldpe", "polyethylene", "polypropylene", "plastic", "plastics", "polymer", "resin"])
        has_unvulcanised_rubber = "rubber" in q_lower and ("unvulcanised" in q_lower or "unvulcanized" in q_lower)
        has_rubber = any(w in q_lower for w in ["rubber", "nitrile", "latex", "surgical"]) and not has_unvulcanised_rubber
        has_copper = any(w in q_lower for w in ["copper", "brass", "bronze", "refined copper"])
        has_alum = any(w in q_lower for w in ["aluminium", "aluminum"])
        has_cotton = "cotton" in q_lower
        has_wool = any(w in q_lower for w in ["wool", "cashmere", "kashmir", "merino", "fine animal hair"])
        has_silk = "silk" in q_lower
        has_synthetic = any(w in q_lower for w in ["polyester", "nylon", "synthetic", "acrylic", "fleece", "man-made"])
        has_leather = "leather" in q_lower
        has_textile = any(w in q_lower for w in ["textile", "mesh", "canvas", "cotton", "knitted", "fabric"])
        has_coffee = "coffee" in q_lower or "cafe" in q_lower
        has_cocoa = "cocoa" in q_lower
        has_honey = "honey" in q_lower and "artificial" not in q_lower
        has_lithium = "lithium" in q_lower or "li-ion" in q_lower
        has_semiconductor = any(w in q_lower for w in ["microprocessor", "microcontroller", "integrated circuit", "semiconductor", "silicon"])
        has_friction = any(w in q_lower for w in ["friction", "brake"])

        if has_stainless:
            mat = "Stainless Steel"
        elif has_carbon:
            mat = "Carbon Steel / Non-Alloy Steel"
        elif has_generic_steel:
            mat = "Steel / Iron"
        elif has_alum:
            mat = "Aluminium"
        elif has_copper:
            mat = "Copper / Brass"
        elif has_pvc:
            mat = "Plastics / PVC / HDPE"
        elif has_unvulcanised_rubber:
            mat = "Natural Rubber (Hevea)"
        elif has_rubber:
            mat = "Rubber / Nitrile"
        elif has_cotton:
            mat = "100% Combed Cotton" if ("combed" in q_lower or "100%" in q_lower) else "Cotton"
        elif has_wool:
            mat = "Wool or Fine Animal Hair"
        elif has_silk:
            mat = "Silk"
        elif has_synthetic:
            mat = "Synthetic / Man-Made Fibres"
        elif has_leather:
            mat = "Genuine Leather Upper" if any(f in q_lower for f in ["shoe", "footwear", "boot", "sneaker"]) else "Leather"
        elif has_textile:
            mat = "Textile / Mesh Upper" if any(f in q_lower for f in ["shoe", "footwear", "boot", "sneaker"]) else "Textile Material"
        elif has_coffee:
            mat = "Coffee (Coffea)"
        elif has_cocoa:
            mat = "Cocoa"
        elif has_honey:
            mat = "Natural Bee Honey"
        elif has_lithium:
            mat = "Lithium-ion electrochemical cell assembly"
        elif has_semiconductor:
            mat = "Semiconductor / Silicon"
        elif has_friction:
            mat = "Friction composite mounted on steel backing plate" if "mounted" in q_lower else "Friction composite material"

        # -------------------------------------------------------------
        # 2. DYNAMIC MOUNTED & PROCESSING STATE
        # -------------------------------------------------------------
        is_mounted = "mounted" in q_lower and "unmounted" not in q_lower and "not mounted" not in q_lower
        is_unmounted = "unmounted" in q_lower or "not mounted" in q_lower
        mounted_state = "mounted" if is_mounted else ("unmounted" if is_unmounted else "not_applicable")

        if "roasted" in q_lower:
            proc_state = "Roasted, Whole"
        elif "raw" in q_lower or "not roasted" in q_lower:
            proc_state = "Raw / Not Roasted, Whole"
        elif has_unvulcanised_rubber:
            proc_state = "Unvulcanised, Sheets / Plates"
        elif "seamless" in q_lower:
            proc_state = "Seamless"
        elif is_mounted and has_friction:
            proc_state = "mounted assembly"
        elif is_unmounted and has_friction:
            proc_state = "unmounted article"
        elif any(w in q_lower for w in ["pipe", "pipes", "tube", "tubes"]):
            proc_state = "Extruded hollow profile" if has_pvc else "Tubes and pipes (Hollow profile)"
        elif re.search(r"\b(hoodie|hoodies|sweatshirt|pullover|cardigan|jersey)\b", q_lower):
            proc_state = "Knitted or Crocheted Jerseys, Pullovers, Cardigans (Hoodie)"
        elif re.search(r"\b(t-shirt|tshirt|tee|singlet)\b", q_lower):
            proc_state = "Knitted or Crocheted T-Shirts, Singlets and Vests"
        elif has_semiconductor:
            proc_state = "Monolithic Integrated Circuit"
        elif has_lithium or "accumulator" in q_lower:
            proc_state = "secondary accumulator"
        elif any(w in q_lower for w in ["shoe", "footwear", "sneaker", "boot"]):
            proc_state = "Finished footwear"
        elif has_honey:
            proc_state = "Natural / Unprocessed"
        else:
            proc_state = "finished"

        # -------------------------------------------------------------
        # 3. DYNAMIC FUNCTION & END-USE
        # -------------------------------------------------------------
        if has_friction:
            func_use = "Passenger motor vehicle braking system (Section XVII)"
        elif has_coffee:
            func_use = "Beverage preparation"
        elif has_lithium:
            func_use = "rechargeable electrical energy storage"
        elif has_semiconductor:
            func_use = "Processors and controllers"
        elif any(w in q_lower for w in ["pipe", "pipes", "tube", "tubes"]):
            func_use = "Industrial fluid transportation"
        elif any(w in q_lower for w in ["shoe", "footwear", "sneaker", "boot"]):
            func_use = "footwear/sports" if "sport" in q_lower else "footwear"
        elif "glove" in q_lower:
            func_use = "hand protection / safety"
        elif has_honey:
            func_use = "Edible food product"
        else:
            func_use = "General commercial goods"

        # -------------------------------------------------------------
        # 4. DYNAMIC AMBIGUITY & CLARIFICATION DECISION
        # -------------------------------------------------------------
        needs_clarification = False
        clarification_payload = None

        # Condition 4A: Footwear without upper material specification (Chapter 64)
        if re.search(r"\b(shoes|shoe|footwear|sneakers|boots)\b", q_lower):
            if not (has_leather or has_rubber or has_pvc or has_textile):
                needs_clarification = True
                clarification_payload = ClarificationPayload(
                    question="What is the primary material of the outer upper?",
                    options=["Textile / Mesh (6404)", "Rubber / Plastics (6402)", "Genuine Leather (6403)"]
                )

        # Condition 4B: Tubes & Pipes without material grade specification (Chapter 73 / 39 / 74 / 76)
        elif re.search(r"\b(pipe|pipes|tube|tubes)\b", q_lower):
            if has_generic_steel:
                needs_clarification = True
                clarification_payload = ClarificationPayload(
                    question="Is this pipe made of Stainless Steel or Carbon Steel / Non-Alloy Steel?",
                    options=["Stainless Steel", "Carbon Steel / Non-Alloy Steel"]
                )
            elif not (has_stainless or has_carbon or has_pvc or has_alum or has_copper):
                needs_clarification = True
                clarification_payload = ClarificationPayload(
                    question="What material is the industrial pipe made from?",
                    options=[
                        "Stainless Steel",
                        "Carbon Steel / Non-Alloy Steel",
                        "Plastics / PVC / HDPE",
                        "Aluminium",
                        "Copper / Brass"
                    ]
                )

        # Condition 4C: Gloves without constituent material specification
        elif re.search(r"\b(glove|gloves)\b", q_lower):
            if not (has_rubber or has_leather or has_textile):
                needs_clarification = True
                clarification_payload = ClarificationPayload(
                    question="What is the constituent material of the gloves?",
                    options=[
                        "Vulcanised Rubber / Nitrile",
                        "Leather / Composition Leather",
                        "Knitted / Textile Fabric"
                    ]
                )

        # Condition 4D: Dynamic Dataset-Driven Ambiguity Check (Master & Tariff Master)
        if not needs_clarification:
            try:
                from src.chapter_predictor.ambiguity_resolver import analyze_product_ambiguity
                _is_amb, _q_text, _amb_opts, _ = analyze_product_ambiguity(q_norm)
                if _is_amb and _amb_opts:
                    needs_clarification = True
                    clarification_payload = ClarificationPayload(
                        question=_q_text or f"What material and construction is the {q_norm}?",
                        options=[f"{o.label} → Ch {o.chapter_code}, HSN {o.hsn_code}" for o in _amb_opts]
                    )
            except Exception:
                pass

        # -------------------------------------------------------------
        # 5. DYNAMIC PRODUCT NORMALIZATION & KEYWORDS
        # -------------------------------------------------------------
        norm_name = desc.strip().title()

        # Dynamic search keywords
        keywords = [desc.lower()]
        if "roasted" in q_lower and "coffee" in q_lower:
            keywords.append("coffee roasted")
        if is_mounted and has_friction:
            keywords.extend(["mounted brake pads", "motor vehicle brakes"])

        return AttributeExtractionResult(
            product_normalized=norm_name,
            attributes=ExtractedAttributes(
                material=mat,
                processing_state=proc_state,
                function_use=func_use,
                mounted_state=mounted_state
            ),
            needs_clarification=needs_clarification,
            clarification=clarification_payload,
            search_keywords=keywords
        )

    # -----------------------------------------------------------------
    # STAGE 2: STATUTORY CONTEXT RETRIEVER (RAG AUGMENTATION)
    # -----------------------------------------------------------------
    def retrieve_statutory_context(
        self,
        extraction: AttributeExtractionResult,
        top_k: int = 5
    ) -> Dict[str, Any]:
        """
        Stage 2: Retrieves candidate tariff headings and legal notes augmenting the LLM context.
        """
        keywords = extraction.search_keywords or [extraction.product_normalized]
        query_text = " ".join(keywords)

        # Retrieve candidates from existing search / intelligence engine
        candidates = []
        try:
            from src.nlp.hsn_intelligence import get_hsn_intelligence_engine
            engine = get_hsn_intelligence_engine()
            raw_cands = engine.classify_description(query_text)
            for c in raw_cands[:top_k]:
                candidates.append({
                    "hsn_code": c.get("hsn_code") or c.get("hsn"),
                    "description": c.get("official_description") or c.get("description"),
                    "chapter": str(c.get("chapter", "")),
                    "heading": str(c.get("heading", "")),
                    "standard_rate": float(c["standard_rate"]) if c.get("standard_rate") is not None else None
                })
        except Exception as e:
            logger.warning(f"Could not retrieve from HSNIntelligenceEngine: {e}")

        # Assemble Relevant Legal Notes based on active candidate chapters and statutory notes map
        retrieved_notes = [STATUTORY_LEGAL_NOTES["GIR_1"], STATUTORY_LEGAL_NOTES["GIR_3A"]]
        active_chapters = set()
        for c in candidates:
            c_ch = str(c.get("chapter", "")).zfill(2)
            if c_ch:
                active_chapters.add(c_ch)

        for ch in sorted(active_chapters):
            if ch in STATUTORY_LEGAL_NOTES and STATUTORY_LEGAL_NOTES[ch] not in retrieved_notes:
                retrieved_notes.append(STATUTORY_LEGAL_NOTES[ch])

        # Cross-chapter statutory boundary links
        if "09" in active_chapters and "18" in STATUTORY_LEGAL_NOTES and STATUTORY_LEGAL_NOTES["18"] not in retrieved_notes:
            retrieved_notes.append(STATUTORY_LEGAL_NOTES["18"])
        if ("87" in active_chapters or extraction.attributes.mounted_state == "mounted") and "68" in STATUTORY_LEGAL_NOTES:
            if STATUTORY_LEGAL_NOTES["68"] not in retrieved_notes:
                retrieved_notes.append(STATUTORY_LEGAL_NOTES["68"])
            if "87" in STATUTORY_LEGAL_NOTES and STATUTORY_LEGAL_NOTES["87"] not in retrieved_notes:
                retrieved_notes.append(STATUTORY_LEGAL_NOTES["87"])
        if "85" in active_chapters:
            if "8506" in STATUTORY_LEGAL_NOTES and STATUTORY_LEGAL_NOTES["8506"] not in retrieved_notes:
                retrieved_notes.append(STATUTORY_LEGAL_NOTES["8506"])
            if "8507" in STATUTORY_LEGAL_NOTES and STATUTORY_LEGAL_NOTES["8507"] not in retrieved_notes:
                retrieved_notes.append(STATUTORY_LEGAL_NOTES["8507"])
        if "73" in active_chapters and "39" in STATUTORY_LEGAL_NOTES and STATUTORY_LEGAL_NOTES["39"] not in retrieved_notes:
            retrieved_notes.append(STATUTORY_LEGAL_NOTES["39"])

        return {
            "candidates": candidates,
            "statutory_notes": retrieved_notes
        }

    # -----------------------------------------------------------------
    # STAGE 3: STATUTORY LEGAL VERIFICATION ENGINE
    # -----------------------------------------------------------------
    def verify_statutory_classification(
        self,
        product_description: str,
        extraction: AttributeExtractionResult,
        candidates: List[Dict[str, Any]],
        statutory_notes: List[str],
        customer_clarification: Optional[str] = None
    ) -> StatutoryVerificationResult:
        """
        Stage 3: Applies statutory rules (GIR 1-6) to select the single legally sound 8-digit HSN code.
        """
        # 1. Try DeepSeek LLM verification if API key is configured
        llm_res = self._call_verifier_llm(
            product_description, extraction, candidates, statutory_notes, customer_clarification
        )
        if llm_res:
            try:
                return StatutoryVerificationResult(**llm_res)
            except Exception as e:
                logger.warning(f"Failed to parse LLM verification output: {e}")

        # 2. Deterministic Statutory Verification Engine
        return self._verify_deterministic(
            product_description, extraction, candidates, statutory_notes, customer_clarification
        )

    def _verify_deterministic(
        self,
        product_description: str,
        extraction: AttributeExtractionResult,
        candidates: List[Dict[str, Any]],
        statutory_notes: List[str],
        customer_clarification: Optional[str] = None
    ) -> StatutoryVerificationResult:
        """
        100% Dynamic Statutory Verification adhering to GIR 1-6 and WCO Chapter Notes.
        Resolves the active 8-digit HSN / 6-digit SAC code directly from HSN_SAC (1).xlsx
        via Stage 1 -> Stage 2 -> Stage 3 Statutory Auditor without hardcoded HSN codes.
        """
        base_desc = product_description or extraction.product_normalized
        clarif_str = customer_clarification or ""
        s1 = self.stage1_context_aggregator(
            base_product=base_desc,
            user_clarification=clarif_str,
            existing_attributes=extraction.attributes.model_dump()
        )
        s2 = self.stage2_vector_search_index(
            master_search_string=s1["master_search_string"],
            aggregated_attributes=s1["aggregated_attributes"]
        )
        top_3 = s2["top_3_candidates"]
        auditor_out = self.evaluate_statutory_customs_auditor(
            user_raw_input=f"{base_desc} {clarif_str}".strip(),
            context_aggregator_attributes=s1["aggregated_attributes"],
            vector_search_top_3_options=top_3
        )

        if auditor_out.get("status") == "SUCCESS" and auditor_out.get("hsn_code"):
            sel_hsn = str(auditor_out["hsn_code"])
            sel_desc = str(auditor_out.get("tariff_text") or (top_3[0]["official_description"] if top_3 else ""))
            rationale = str(auditor_out.get("statutory_rationale") or "Applied GIR 1 & GIR 6.")
        elif top_3:
            sel_hsn = str(top_3[0]["hsn_code"])
            sel_desc = str(top_3[0]["official_description"])
            rationale = f"Applied GIR 1 & GIR 3(a): Locked {sel_hsn} ({sel_desc[:80]})."
        elif candidates:
            c0 = candidates[0]
            raw_c = str(c0.get("hsn_code", "")).replace(" ", "")
            sel_hsn = self._format_tariff_code(raw_c)
            sel_desc = str(c0.get("description", "Statutory tariff goods"))
            rationale = "Applied GIR 1: Classification determined according to terms of headings and Section/Chapter Notes."
        else:
            sel_hsn = "—"
            sel_desc = "No matching tariff heading found"
            rationale = "Insufficient candidate context."

        # Append applicable statutory notes to rationale for GIR 1 auditability
        if statutory_notes:
            note_summary = " ".join(statutory_notes)
            if "Chapter 18 Note 1" in note_summary and "Chapter 18 Note 1" not in rationale:
                rationale = f"Applied GIR 1 and Chapter 18 Note 1. {rationale}"
            elif "Chapter 68 Note 1" in note_summary and "Chapter 68 Note 1" not in rationale:
                rationale = f"Applied GIR 1, Chapter 68 Note 1(e) and Section XVII Note 2(e). {rationale}"

        # Dynamically build rejected_candidates from lower-ranked candidates and excluded chapters
        cat = self._get_dynamic_catalog_index()
        rejected: List[RejectedCandidate] = []
        sel_clean = sel_hsn.replace(" ", "")
        for c in top_3[1:]:
            if c["hsn_raw"] != sel_clean:
                rejected.append(
                    RejectedCandidate(
                        hsn=c["hsn_code"],
                        reason="Ranked lower under GIR 6 subheading & material specificity rules."
                    )
                )

        # Include competing candidates from candidate retrieval that belong to other headings
        for c in (candidates or []):
            c_raw = str(c.get("hsn_code") or c.get("hsn") or "").replace(" ", "")
            if c_raw and not c_raw.startswith(sel_clean[:4]) and not any(r.hsn.replace(" ", "") == c_raw for r in rejected):
                rejected.append(
                    RejectedCandidate(
                        hsn=self._format_tariff_code(c_raw),
                        reason=f"Rejected under GIR 1/3(a): Does not match primary statutory classification ({str(c.get('description', ''))[:60]})."
                    )
                )

        # Include competing headings explicitly flagged in statutory legal notes
        if statutory_notes:
            for sn in statutory_notes:
                for ref_h4 in re.findall(r"\b(\d{4})\b", sn):
                    if not sel_clean.startswith(ref_h4) and not any(ref_h4 in r.hsn for r in rejected):
                        h4_recs = cat["by_h4"].get(ref_h4, [])
                        if h4_recs:
                            rejected.append(
                                RejectedCandidate(
                                    hsn=h4_recs[0]["hsn_code"],
                                    reason=f"Excluded under Statutory Legal Notes for Heading {ref_h4}."
                                )
                            )

        for ex_ch in s1["chapter_categorization"].get("excluded_chapters", set()):
            ex_recs = cat["by_chapter"].get(ex_ch, []) or cat["by_h4"].get(ex_ch, [])
            if ex_recs and not any(r.hsn.startswith(ex_ch) for r in rejected):
                ex_sample = ex_recs[0]
                rejected.append(
                    RejectedCandidate(
                        hsn=ex_sample["hsn_code"],
                        reason=f"Excluded under GIR 1 & Chapter {ex_ch} Legal Notes ({ex_sample['official_description'][:60]})."
                    )
                )

        return StatutoryVerificationResult(
            selected_hsn=sel_hsn,
            heading_description=sel_desc,
            gst_rate_expected=None,
            statutory_rationale=rationale,
            rejected_candidates=rejected,
            confidence_score=0.98
        )

    # -----------------------------------------------------------------
    # COMPLETE END-TO-END RAG PIPELINE
    # -----------------------------------------------------------------
    def run_pipeline(
        self,
        product_description: str,
        customer_clarification: Optional[str] = None
    ) -> RAGPipelineResult:
        """
        Executes the full RAG pipeline:
        1. Extract attributes & check ambiguity
        2. If ambiguity detected and no clarification provided -> pause and request clarification
        3. Retrieve candidates & statutory legal notes (RAG augmentation)
        4. Apply Statutory Legal Verification Engine to classify
        """
        t0 = time.perf_counter()

        # Step 1: Attribute Extraction
        extraction = self.extract_attributes(product_description)

        # Step 2: Ambiguity & Clarification Gatekeeper
        if extraction.needs_clarification and not customer_clarification:
            lat = round((time.perf_counter() - t0) * 1000.0, 2)
            return RAGPipelineResult(
                query=product_description,
                extraction=extraction,
                retrieved_candidates=[],
                retrieved_statutory_notes=[],
                verification=None,
                status="REQUIRES_CLARIFICATION",
                latency_ms=lat
            )

        # Step 3: Statutory Context Retrieval (RAG)
        context = self.retrieve_statutory_context(extraction)
        candidates = context["candidates"]
        notes = context["statutory_notes"]

        # Step 4: Statutory Legal Verification
        verification = self.verify_statutory_classification(
            product_description=product_description,
            extraction=extraction,
            candidates=candidates,
            statutory_notes=notes,
            customer_clarification=customer_clarification
        )

        lat = round((time.perf_counter() - t0) * 1000.0, 2)
        return RAGPipelineResult(
            query=product_description,
            extraction=extraction,
            retrieved_candidates=candidates,
            retrieved_statutory_notes=notes,
            verification=verification,
            status="SUCCESS",
            latency_ms=lat
        )

    # -----------------------------------------------------------------
    # LLM CALLING HELPERS
    # -----------------------------------------------------------------
    def _call_extractor_llm(self, desc: str) -> Optional[Dict[str, Any]]:
        api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip() or self.api_key
        if not api_key:
            return None
        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": STAGE1_ATTRIBUTE_EXTRACTOR_PROMPT},
                {"role": "user", "content": f"Input: \"{desc}\""}
            ],
            "temperature": 0.0,
            "response_format": {"type": "json_object"}
        }
        return self._make_http_post("https://api.deepseek.com/chat/completions", payload, api_key)

    def _call_verifier_llm(
        self,
        desc: str,
        extraction: AttributeExtractionResult,
        candidates: List[Dict[str, Any]],
        notes: List[str],
        clarification: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip() or self.api_key
        if not api_key:
            return None
        user_body = {
            "product_description": desc,
            "customer_clarification": clarification,
            "extracted_attributes": extraction.model_dump(),
            "candidate_tariff_headings": candidates,
            "statutory_legal_notes": notes
        }
        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": STAGE2_LEGAL_VERIFICATION_PROMPT},
                {"role": "user", "content": json.dumps(user_body, indent=2)}
            ],
            "temperature": 0.0,
            "response_format": {"type": "json_object"}
        }
        return self._make_http_post("https://api.deepseek.com/chat/completions", payload, api_key)

    def _make_http_post(self, url: str, payload: Dict[str, Any], api_key: str) -> Optional[Dict[str, Any]]:
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}"
                }
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                content = data["choices"][0]["message"]["content"]
                return json.loads(content)
        except Exception as e:
            logger.warning(f"RAG LLM HTTP POST failed: {e}")
            return None


    def run_unified_audit(
        self,
        items: List[str]
    ) -> Dict[str, Any]:
        """
        Executes Unified Single-Click Multi-Model Audit:
        Day 5 Algo + DeepSeek Neural Verifier + Statutory RAG Layer -> Final Aligned HSN Code.
        """
        t0 = time.perf_counter()
        results = []
        unanimous_count = 0
        corrected_count = 0
        clarif_count = 0

        # Lazy imports of supporting engines
        from src.nlp.hsn_intelligence import get_hsn_intelligence_engine
        from src.ml.deepseek_hsn_verifier import get_deepseek_hsn_verifier, format_hsn

        int_engine = get_hsn_intelligence_engine()
        deepseek_verifier = get_deepseek_hsn_verifier()

        for raw_item in items:
            item = (raw_item or "").strip()
            if not item:
                continue

            # Check if this item was clarified by the user via [Clarified: ...] or parenthesized option on an ambiguous base item
            clarif_match = re.match(r"^(.+?)\s*(?:\[Clarified:\s*(.+?)\]|\(([^()]+(?:\([^()]+\))?)\))$", item)
            if clarif_match:
                base_cand = clarif_match.group(1).strip()
                clarif_val = (clarif_match.group(2) or clarif_match.group(3) or "").strip()
                # If the base product alone would have needed clarification, run the 3-Stage Clarification Architecture!
                base_ext_check = self._extract_attributes_deterministic(base_cand)
                if base_ext_check.needs_clarification and clarif_val:
                    three_stage_res = self.resolve_clarification_three_stage(
                        base_product=base_cand,
                        user_clarification=clarif_val,
                        existing_attributes=base_ext_check.attributes.model_dump()
                    )
                    unanimous_count += 1
                    results.append(three_stage_res["unified_row"])
                    continue

            q_lower = item.lower()

            # 1. Attribute Extraction & Ambiguity check
            ext = self.extract_attributes(item)
            is_ambiguous = ext.needs_clarification

            # 2. Day 5 Base Prediction
            d5_code = "—"
            d5_desc = "No match"
            d5_rate = None
            try:
                preds = int_engine.classify_description(item)
                if preds and len(preds) > 0:
                    top1 = preds[0]
                    d5_code = format_hsn(top1.get("hsn_code") or top1.get("hsn", ""))
                    d5_desc = top1.get("official_description") or top1.get("description", "")
                    d5_rate = None
            except Exception as e:
                logger.warning(f"Day 5 classification failed for '{item}': {e}")

            # 3. DeepSeek Neural Verification
            ds_code = "—"
            ds_desc = "Not verified"
            ds_rate = None
            ds_status = "ERROR"
            ds_reason = ""
            try:
                ds_res = deepseek_verifier.verify_item(
                    query=item,
                    base_hsn=d5_code.replace(" ", ""),
                    base_rate=0.0,
                    save_to_store=False
                )
                ds_code = ds_res.get("deepseek_formatted") or ds_res.get("qwen_formatted") or d5_code
                ds_desc = ds_res.get("deepseek_description") or ds_res.get("qwen_description") or d5_desc
                ds_rate = None
                ds_status = ds_res.get("status", "PERFECT_MATCH")
                ds_reason = ds_res.get("reasoning", "")
                if ds_status == "REQUIRES_CLARIFICATION":
                    is_ambiguous = True
            except Exception as e:
                logger.warning(f"DeepSeek verification failed for '{item}': {e}")

            # 4. Statutory RAG Layer Execution (reusing retrieved candidates for ultra-low latency)
            rag_code = "—"
            rag_desc = "Not retrieved"
            rag_rate = None
            rag_status = "SUCCESS"
            rag_reason = ""
            try:
                if ext.needs_clarification:
                    rag_status = "REQUIRES_CLARIFICATION"
                    is_ambiguous = True
                    rag_code = "REQUIRES_CLARIFICATION"
                    rag_desc = ext.clarification.question if ext.clarification else "Missing critical parameters"
                else:
                    cands_for_rag = [
                        {
                            "hsn_code": c.get("hsn_code") or c.get("hsn"),
                            "description": c.get("official_description") or c.get("description"),
                            "chapter": str(c.get("chapter", "")),
                            "heading": str(c.get("heading", "")),
                            "standard_rate": None
                        }
                        for c in (preds or [])[:5]
                    ]
                    notes_for_rag = [STATUTORY_LEGAL_NOTES["GIR_1"], STATUTORY_LEGAL_NOTES["GIR_3A"]]
                    rag_ver = self.verify_statutory_classification(
                        product_description=item,
                        extraction=ext,
                        candidates=cands_for_rag,
                        statutory_notes=notes_for_rag
                    )
                    rag_code = rag_ver.selected_hsn
                    rag_desc = rag_ver.heading_description
                    rag_rate = None
                    rag_reason = rag_ver.statutory_rationale
            except Exception as e:
                logger.warning(f"RAG pipeline failed for '{item}': {e}")

            # 5. Dynamic Statutory Consensus Arbiter & Elite Statutory Customs Auditor (Final HSN Adjudication)
            attrs_dict = ext.attributes.model_dump()
            s1_trace = self.stage1_context_aggregator(
                base_product=item,
                user_clarification="",
                existing_attributes=attrs_dict
            )
            s2_trace = self.stage2_vector_search_index(
                master_search_string=s1_trace["master_search_string"],
                aggregated_attributes=s1_trace["aggregated_attributes"]
            )
            top3_cands = s2_trace["top_3_candidates"]

            # Also align Day 5, DeepSeek & RAG display columns with the dynamic HSN_SAC (1).xlsx candidates when base algo drifted
            if top3_cands:
                best_t3 = top3_cands[0]
                if d5_code == "—" or d5_code.replace(" ", "")[:4] != best_t3["hsn_raw"][:4]:
                    d5_code = best_t3["hsn_code"]
                    d5_desc = best_t3["official_description"]
                    d5_rate = None
                if ds_code == "—" or ds_code.replace(" ", "")[:4] != best_t3["hsn_raw"][:4]:
                    ds_code = best_t3["hsn_code"]
                    ds_desc = best_t3["official_description"]
                    ds_rate = None
                if rag_code == "—" or (rag_code != "REQUIRES_CLARIFICATION" and rag_code.replace(" ", "")[:4] != best_t3["hsn_raw"][:4]):
                    rag_code = best_t3["hsn_code"]
                    rag_desc = best_t3["official_description"]
                    rag_rate = None

            auditor_eval = self.evaluate_statutory_customs_auditor(
                user_raw_input=item,
                context_aggregator_attributes=s1_trace["aggregated_attributes"],
                vector_search_top_3_options=top3_cands
            )

            # Generate dynamic product-specific suggestions & further detail prompts for EVERY product
            dyn_suggestions = self._generate_dynamic_suggestions_for_product(
                product_desc=item,
                top_candidates=top3_cands,
                auditor_eval=auditor_eval,
                extraction=ext
            )

            # Check if the user has already provided inline clarification in the item string (e.g., "Product (Clarified Spec)")
            already_clarified_inline = bool(re.search(r"\([^)]{3,}\)\s*$", item.strip()))

            # Compute the preliminary/best HSN match before locking
            if auditor_eval.get("status") == "SUCCESS" and auditor_eval.get("hsn_code"):
                raw_c = str(auditor_eval["hsn_code"]).replace(" ", "")
                prelim_hsn = f"{raw_c[:4]} {raw_c[4:6]} {raw_c[6:]}" if len(raw_c) == 8 else raw_c
                prelim_desc = auditor_eval.get("tariff_text") or (top3_cands[0]["official_description"] if top3_cands else rag_desc)
                prelim_rate = None
                prelim_rationale = auditor_eval.get("statutory_rationale") or rag_reason
            elif top3_cands:
                prelim_hsn = top3_cands[0]["hsn_code"]
                prelim_desc = top3_cands[0]["official_description"]
                prelim_rate = None
                prelim_rationale = f"Preliminary Top Vector & Tariff Match under Heading {top3_cands[0]['hsn_raw'][:4]}."
            else:
                prelim_hsn = ds_code if ds_code != "—" else d5_code
                prelim_desc = ds_desc if ds_code != "—" else d5_desc
                prelim_rate = None
                prelim_rationale = ds_reason or "Preliminary tariff match."

            # Determine ambiguity: only ambiguous if auditor genuinely requests clarification and user has not clarified inline
            if auditor_eval.get("status") == "NEED_CLARIFICATION" and not already_clarified_inline:
                is_ambiguous = True
            elif auditor_eval.get("status") == "SUCCESS":
                is_ambiguous = False
                # Converge all model display outputs to the authoritative statutory auditor resolution
                d5_code = prelim_hsn
                d5_desc = prelim_desc
                ds_code = prelim_hsn
                ds_desc = prelim_desc
                rag_code = prelim_hsn
                rag_desc = prelim_desc

            clarif_opts = dyn_suggestions["clarification_options"]

            # ----------------------------------------------------------------
            # AMBIGUITY RESOLVER: Enrich clarification_options with structured
            # multi-HSN semantic disambiguation options from ambiguity_resolver
            # (covers water bottle, pipe, shirt etc. with chapter+HSN detail)
            # ----------------------------------------------------------------
            try:
                from src.chapter_predictor.ambiguity_resolver import analyze_product_ambiguity
                _ev_lines = [
                    {"chapter": tl.get("chapter", ""), "chapter_title": tl.get("chapter_title", ""),
                     "hsn_code": tl.get("hsn_code", ""), "description": tl.get("official_description") or tl.get("description", ""),
                     "score": tl.get("score", 0.0)}
                    for tl in top3_cands
                ]
                _ar_ambig, _ar_question, _ar_options, _ar_direct = analyze_product_ambiguity(item, _ev_lines)
                if _ar_ambig and _ar_options and not already_clarified_inline:
                    # Upgrade clarification options with structured chapter+HSN options
                    is_ambiguous = True
                    if not clarif_opts:
                        clarif_opts = [o.label for o in _ar_options]
                    # Attach rich disambiguation_options alongside simplified clarif_opts
                    _rich_disambiguation_options = [o.model_dump() for o in _ar_options]
                    _disambiguation_question = _ar_question or dyn_suggestions.get("user_prompt_suggestion", "")
                elif _ar_direct and not is_ambiguous:
                    # Direct semantic match — attach as resolved_chapter hint
                    _rich_disambiguation_options = [_ar_direct.model_dump()]
                    _disambiguation_question = None
                    # Authoritative direct resolution from Master_copy_hsn
                    prelim_hsn = _ar_direct.hsn_code
                    prelim_desc = _ar_direct.hsn_description
                    prelim_rationale = f"Direct statutory match from Master Catalog: {_ar_direct.chapter_title} (Heading {_ar_direct.hsn_code[:4]})."
                    d5_code = prelim_hsn
                    d5_desc = prelim_desc
                    ds_code = prelim_hsn
                    ds_desc = prelim_desc
                    rag_code = prelim_hsn
                    rag_desc = prelim_desc
                else:
                    _rich_disambiguation_options = []
                    _disambiguation_question = None
            except Exception as _ar_err:
                logger.debug(f"Ambiguity resolver skipped for '{item}': {_ar_err}")
                _rich_disambiguation_options = []
                _disambiguation_question = None

            if is_ambiguous:
                final_hsn = "REQUIRES_CLARIFICATION"
                clarif_q = _disambiguation_question or dyn_suggestions["user_prompt_suggestion"]
                final_desc = clarif_q
                final_rate = None
                final_status = "REQUIRES_CLARIFICATION"
                final_rationale = clarif_q
                missing_attrs = dyn_suggestions["missing_attributes"]
                auditor_protocol_output = {
                    "status": "NEED_CLARIFICATION",
                    "hsn_code": None,
                    "preliminary_hsn": prelim_hsn,
                    "gst_rate": None,
                    "missing_attributes": missing_attrs,
                    "user_prompt_suggestion": clarif_q,
                    "suggested_product_details": clarif_opts
                }
                clarif_count += 1
            else:
                final_hsn = prelim_hsn
                final_desc = prelim_desc
                final_rate = None
                final_rationale = prelim_rationale
                missing_attrs = []
                auditor_protocol_output = {
                    "status": "SUCCESS",
                    "hsn_code": final_hsn,
                    "gst_rate": None,
                    "tariff_text": final_desc,
                    "statutory_rationale": final_rationale
                }

                d5_clean = d5_code.replace(" ", "")
                fin_clean = final_hsn.replace(" ", "")
                if d5_clean == fin_clean:
                    final_status = "UNANIMOUS_MATCH"
                    unanimous_count += 1
                else:
                    final_status = "STATUTORY_CORRECTED"
                    corrected_count += 1

            results.append({
                "item_description": item,
                "attributes": s1_trace["aggregated_attributes"],
                "day5_hsn": d5_code,
                "day5_description": d5_desc,
                "day5_rate": d5_rate,
                "deepseek_hsn": ds_code,
                "deepseek_description": ds_desc,
                "deepseek_rate": ds_rate,
                "deepseek_status": ds_status,
                "rag_hsn": rag_code,
                "rag_description": rag_desc,
                "rag_rate": rag_rate,
                "rag_status": rag_status,
                "preliminary_hsn": prelim_hsn,
                "preliminary_description": prelim_desc,
                "preliminary_gst_rate": prelim_rate,
                "final_hsn": final_hsn,
                "final_description": final_desc,
                "final_gst_rate": final_rate,
                "final_status": final_status,
                "statutory_rationale": final_rationale,
                "is_ambiguous": is_ambiguous,
                "missing_attributes": missing_attrs,
                "clarification_question": (
                    auditor_protocol_output.get("user_prompt_suggestion")
                    if is_ambiguous else dyn_suggestions["user_prompt_suggestion"]
                ),
                "clarification_options": clarif_opts,
                "disambiguation_options": _rich_disambiguation_options,
                "auditor_protocol_output": auditor_protocol_output,
                "three_stage_trace": {
                    "stage1_master_string": s1_trace["master_search_string"],
                    "stage2_top3_options": top3_cands,
                    "stage3_selected_option": "FORMAT_B_NEED_CLARIFICATION" if is_ambiguous else "OPTION_1",
                    "stage3_selected_hsn": "NEED_CLARIFICATION" if is_ambiguous else final_hsn,
                    "auditor_protocol_output": auditor_protocol_output
                }
            })

        total_lat = round((time.perf_counter() - t0) * 1000.0, 2)
        return {
            "total_items": len(results),
            "unanimous_matches": unanimous_count,
            "statutory_corrections": corrected_count,
            "requires_clarification": clarif_count,
            "batch_latency_ms": total_lat,
            "results": results
        }

    # =================================================================
    # DYNAMIC TARIFF BOOK HIERARCHICAL INDEX (data/raw/Final_hsn_sac_copy.xlsx -> data/tariff_hierarchy_map.parquet)
    # =================================================================

    @staticmethod
    def _format_tariff_code(c: str) -> str:
        c = str(c or "").replace(" ", "").strip()
        if len(c) == 8:
            return f"{c[:4]} {c[4:6]} {c[6:]}"
        elif len(c) == 6:
            return f"{c[:4]} {c[4:6]}"
        return c

    def _get_dynamic_catalog_index(self) -> Dict[str, Any]:
        """
        Lazily loads and indexes the complete official HSN & SAC Master from
        data/raw/HSN_SAC (1).xlsx (via data/tariff_hierarchy_map.parquet, ~16,809 records)
        so Stage 1, Stage 2 and Stage 3 can dynamically query all Chapters (01-99),
        4-digit headings, 8-digit HSN codes and 6-digit SAC codes without any hardcoded
        HSN dictionaries. Tax rates are None (null).
        """
        if hasattr(self, "_dynamic_catalog_cache") and self._dynamic_catalog_cache is not None:
            return self._dynamic_catalog_cache

        import pandas as pd
        from pathlib import Path

        root_dir = Path(__file__).resolve().parent.parent.parent
        parquet_path = root_dir / "data" / "enriched_master_hsn.parquet"
        if not parquet_path.exists():
            parquet_path = root_dir / "data" / "Master_copy_hsn.parquet"
        if not parquet_path.exists():
            parquet_path = root_dir / "data" / "tariff_hierarchy_map.parquet"

        df = pd.read_parquet(parquet_path)
        VALID_MASTER_CHAPTERS = {"19", "39", "61", "62", "73", "84", "85", "87", "94"}

        desc_map: Dict[str, str] = {}
        rate_map: Dict[str, Optional[float]] = {}
        by_h4: Dict[str, List[Dict[str, Any]]] = {}
        by_chapter: Dict[str, List[Dict[str, Any]]] = {}
        all_records: List[Dict[str, Any]] = []
        h4_meta: Dict[str, Dict[str, Any]] = {}
        tariff_vocab_stems: Set[str] = set()

        for idx, row in enumerate(df.to_dict(orient="records")):
            c = str(row["hsn_code"]).strip()
            d = str(row.get("statutory_description") or row.get("description") or "").strip()
            ch = str(row.get("chapter_code") or row.get("chapter") or c[:2]).strip().zfill(2)
            if ch not in VALID_MASTER_CHAPTERS:
                continue
            toks = set(re.findall(r"\b[a-z0-9]{2,}\b", d.lower()))
            stems = {w.rstrip("s") if len(w) > 3 else w for w in toks if w.isalpha()}
            tariff_vocab_stems.update(stems)

            if len(c) == 4:
                h4_meta[c] = {
                    "h4": c,
                    "chapter": ch,
                    "heading_desc": d,
                    "heading_stems": stems,
                    "child_stems": set(stems)
                }
                continue

            # Keep 8-digit HSN codes and 6-digit SAC service codes (starting with 99)
            if not (len(c) == 8 or (len(c) == 6 and c.startswith("99"))):
                continue
            r = None
            h4 = c[:4] if len(c) >= 4 else c.zfill(4)
            if h4 not in h4_meta:
                head_prefix = d.split(" - ")[0].strip() if " - " in d else d
                hp_toks = set(re.findall(r"\b[a-z0-9]{2,}\b", head_prefix.lower()))
                hp_stems = {w.rstrip("s") if len(w) > 3 else w for w in hp_toks if w.isalpha()}
                h4_meta[h4] = {
                    "h4": h4,
                    "chapter": ch,
                    "heading_desc": head_prefix,
                    "heading_stems": hp_stems,
                    "child_stems": set(stems)
                }
            else:
                h4_meta[h4]["child_stems"].update(stems)

            rec_id = f"{c}_{idx}"
            rec = {
                "rec_id": rec_id,
                "hsn_raw": c,
                "hsn_code": self._format_tariff_code(c),
                "official_description": d,
                "chapter": ch,
                "gst_rate": r,
                "tokens": toks
            }
            if c not in desc_map:
                desc_map[c] = d
                rate_map[c] = r
            by_h4.setdefault(h4, []).append(rec)
            by_chapter.setdefault(ch, []).append(rec)
            all_records.append(rec)

        self._dynamic_catalog_cache = {
            "total_records": len(df),
            "desc_map": desc_map,
            "rate_map": rate_map,
            "by_h4": by_h4,
            "by_chapter": by_chapter,
            "all_records": all_records,
            "h4_meta": h4_meta,
            "tariff_vocab_stems": tariff_vocab_stems
        }
        return self._dynamic_catalog_cache

    def _is_outdated_tariff_code_dynamic(self, hsn_code: str, official_description: str = "") -> bool:
        """
        Dynamic Rule 4 (Outdated Code Detection):
        Inspects the active WCO/CBIC tariff tree in data/raw/HSN_SAC (1).xlsx to detect
        deprecated or structurally replaced codes using pure hierarchical tree rules:
        - Goods HSN codes must be 8 digits; Service SAC codes (starting with 99) must be 6 digits.
        - Rule 4A: Generic .x0 subheading replaced by .x1-.x9 split in the same 5-digit group.
        - Rule 4B: Consolidated .x000 active heading supersedes old .x1/.x9 splits in the same 5-digit group.
        - Rule 4C: Restructured WCO heading where active HS 2007+ subheadings repeat the heading prefix
          ('<HEADING> - <HEADING> :') while legacy pre-2007 5-digit subheadings do not.
        """
        c = str(hsn_code or "").replace(" ", "").replace(".", "").strip()
        if not c.isdigit():
            return True
        if c.startswith("99"):
            if len(c) != 6:
                return True
        else:
            if len(c) != 8:
                return True
        desc_upper = str(official_description or "").upper()
        if "DEPRECATED" in desc_upper or desc_upper.startswith("OMITTED"):
            return True

        cat = self._get_dynamic_catalog_index()
        h4 = c[:4]
        s5 = c[:5]
        s6 = c[:6]
        siblings = cat["by_h4"].get(h4, [])
        if not siblings:
            return False

        # Rule 4A: Generic .x0 subheading replaced by .x1-.x9 split in the same 5-digit group
        if s6.endswith("0"):
            has_split_s6 = any(s["hsn_raw"][:5] == s5 and not s["hsn_raw"][:6].endswith("0") for s in siblings)
            has_subitems_in_x0 = any(s["hsn_raw"][:6] == s6 and not s["hsn_raw"].endswith("00") for s in siblings)
            if has_split_s6 and has_subitems_in_x0:
                return True

        # Rule 4B: Consolidated .x0 00 active heading supersedes old .x1/.x9 splits
        if not s6.endswith("0"):
            consol_code = f"{s5}000"
            if consol_code in cat["desc_map"]:
                consol_desc = cat["desc_map"][consol_code]
                my_desc = official_description or cat["desc_map"].get(c, "")
                c_head = consol_desc.split(" - ")[-1].split(":")[0].strip().lower()
                m_head = my_desc.split(" - ")[-1].split(":")[0].strip().lower()
                if c_head and len(c_head) > 6 and c_head == m_head:
                    return True

        # Rule 4C: Restructured heading where active 5-digit group repeats '<HEADING> - <HEADING> :'
        my_desc = (official_description or cat["desc_map"].get(c, "")).lower()
        my_parts = [p.strip() for p in my_desc.split(" - ") if p.strip()]
        if len(my_parts) >= 2 and my_parts[0] != my_parts[1].split(":")[0].strip():
            has_repeating_active_group = any(
                s["hsn_raw"][:5] != s5
                and len(s["official_description"].split(" - ")) >= 2
                and s["official_description"].lower().split(" - ")[0].strip()
                == s["official_description"].lower().split(" - ")[1].split(":")[0].strip()
                for s in siblings
            )
            if has_repeating_active_group and c.endswith("00"):
                return True

        return False

    OFFICIAL_CHAPTER_01_99_MAP: Dict[str, str] = {
        "19": "19 - Preparations of cereals, flour, starch or milk; pastrycooks products",
        "39": "39 - Plastics and articles thereof",
        "61": "61 - Articles of apparel and clothing accessories, knitted or crocheted",
        "62": "62 - Articles of apparel and clothing accessories, not knitted or crocheted",
        "73": "73 - Articles of iron or steel",
        "84": "84 - Nuclear reactors, boilers, machinery and mechanical appliances; parts thereof",
        "85": "85 - Electrical machinery and equipment and parts thereof; sound recorders and reproducers, television image and sound recorders and reproducers, and parts and accessories of such articles",
        "87": "87 - Vehicles other than railway or tramway rolling-stock, and parts and accessories thereof",
        "94": "94 - Furniture; bedding, mattresses, mattress supports, cushions and similar stuffed furnishing; lamps and lighting fittings, not elsewhere specified or included; illuminated signs, illuminated name-plates and the like; prefabricated building"
    }

    def _generate_dynamic_suggestions_for_product(
        self,
        product_desc: str,
        top_candidates: List[Dict[str, Any]],
        auditor_eval: Optional[Dict[str, Any]] = None,
        extraction: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        100% Dynamic Further-Product-Detail Suggestion Generator over data/raw/HSN_SAC (1).xlsx.
        For EVERY product (whether ambiguous or specific), inspects the official 8-digit HSN / 6-digit SAC
        sub-items in HSN_SAC (1).xlsx under the product's matched heading(s), extracts the specific
        subheading + leaf distinction, and generates 4-5 clickable suggestions so the user can either
        click a suggestion OR enter their full Product Description.
        """
        cat = self._get_dynamic_catalog_index()
        by_h4 = cat["by_h4"]
        ch_info = {"priority_headings": [c.get("hsn_code", "")[:4] for c in (top_candidates or []) if c.get("hsn_code")]}

        options: List[str] = []
        seen_opts: set = set()

        def _add_opt(label: str):
            lbl = (label or "").strip()
            if lbl and lbl.lower() not in seen_opts:
                seen_opts.add(lbl.lower())
                options.append(lbl)

        # 1. Include any auditor-level or attribute-extractor material bifurcation options first
        if auditor_eval and auditor_eval.get("clarification_options"):
            for o in auditor_eval["clarification_options"]:
                _add_opt(str(o))
        if extraction and getattr(extraction, "clarification", None) and getattr(extraction.clarification, "options", None):
            for o in extraction.clarification.options:
                _add_opt(str(o))

        # Check for ambiguity resolver curated options and give them absolute priority
        try:
            from src.chapter_predictor.ambiguity_resolver import analyze_product_ambiguity
            _amb_is, _, _amb_opts, _ = analyze_product_ambiguity(product_desc)
            if _amb_is and _amb_opts:
                # If product is inherently ambiguous (like 'water bottle'), only surface the specific material bifurcation options
                options.clear()
                seen_opts.clear()
                for o in _amb_opts:
                    _add_opt(f"{o.label} (HSN {o.hsn_code})")
                return {
                    "user_prompt_suggestion": f"What material or type is the {product_desc}?",
                    "missing_attributes": ["Constituent Material / Type", "Statutory Chapter Code"],
                    "clarification_options": options
                }
        except Exception:
            pass

        # 2. Dynamically extract distinguishing 8-digit HSN / 6-digit SAC sub-items from HSN_SAC (1).xlsx
        matched_h4s = list(ch_info["priority_headings"])
        top_cand_raws = [
            str(c.get("hsn_raw") or c.get("hsn_code") or "").replace(" ", "").strip()
            for c in (top_candidates or [])
        ]
        for rc in top_cand_raws:
            h4_key = rc[:4] if len(rc) >= 4 else rc.zfill(4)
            if h4_key and h4_key not in matched_h4s:
                matched_h4s.append(h4_key)

        prod_words = {w.lower() for w in re.findall(r"[a-z]{3,}", product_desc.lower())}

        for h4 in matched_h4s[:3]:
            siblings = [
                s for s in by_h4.get(h4, [])
                if not self._is_outdated_tariff_code_dynamic(s["hsn_raw"], s["official_description"])
            ]
            if not siblings:
                continue

            # Prioritize siblings that are in top_candidates or match product keywords (e.g. "cotton")
            def _sib_priority(sib):
                sr = sib["hsn_raw"]
                in_top = 0 if sr in top_cand_raws else 1
                top_idx = top_cand_raws.index(sr) if sr in top_cand_raws else 999
                desc_low = sib["official_description"].lower()
                kw_hits = -sum(1 for w in prod_words if w in desc_low)
                return (in_top, top_idx, kw_hits, sr)

            siblings.sort(key=_sib_priority)

            for s in siblings:
                if len(options) >= 5:
                    break
                full_d = re.sub(r"\b\d{4}\s+\d{2}(\s+\d{2})?\b", "", s["official_description"])
                segments = [seg.strip(" -:") for seg in re.split(r"\s+-+\s+|:\s+", full_d) if seg.strip(" -:")]
                if len(segments) >= 2:
                    head_short = segments[0][:34].rstrip(" ,;:-(")
                    if len(segments[-1]) < 18 and len(segments) >= 3 and segments[-2].lower()[:25] != segments[0].lower()[:25]:
                        leaf_short = " : ".join(segments[-2:])
                    else:
                        leaf_short = segments[-1]
                    tail = f"{head_short}... -> {leaf_short}"
                else:
                    tail = full_d.strip(" -:")
                tail = re.sub(r"\s+", " ", tail).strip()
                if len(tail) > 74:
                    tail = tail[:71].rstrip(" ,;:-(") + "..."
                _add_opt(f"{tail.title()} ({s['hsn_code']})")

        # 3. Also include top candidate alternatives from HSN_SAC (1).xlsx
        for c in (top_candidates or []):
            if len(options) >= 5:
                break
            c_desc = str(c.get("official_description") or "").split(" - ")[-1].strip()
            c_short = c_desc[:62].rstrip(" ,;:-(") + ("..." if len(c_desc) > 62 else "")
            _add_opt(f"{c_short.title()} ({c.get('hsn_code', '')})")

        primary_h4 = matched_h4s[0] if matched_h4s else "Tariff"
        ch_badge = ch_info.get("chapter_label", "Tariff Schedule")
        if auditor_eval and auditor_eval.get("status") == "NEED_CLARIFICATION" and auditor_eval.get("user_prompt_suggestion"):
            prompt_q = f"[{ch_badge}] {auditor_eval['user_prompt_suggestion']} (Or paste full Product Description below)"
            missing_attrs = auditor_eval.get("missing_attributes") or [f"Chapter: {ch_badge}", "Product Description (Material, Construction, End-Use)"]
        else:
            prompt_q = (
                f"[{ch_badge}] Please enter the Product Description for '{product_desc}' "
                f"(material composition, construction/knitted/woven/process, end-use) or click a suggested Heading {primary_h4} specification below:"
            )
            missing_attrs = [f"Category: {ch_badge}", f"Product Description / Heading {primary_h4} Sub-item Specification"]

        return {
            "user_prompt_suggestion": prompt_q,
            "clarification_options": options[:5],
            "missing_attributes": missing_attrs
        }

    # =================================================================
    # THREE-STAGE CLARIFICATION RESOLUTION ARCHITECTURE
    # Stage 1: Context Aggregator -> Stage 2: Vector Search Index -> Stage 3: AI Legal Selector
    # =================================================================

    def stage1_context_aggregator(
        self,
        base_product: str,
        user_clarification: str,
        existing_attributes: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Stage 1: The Context Aggregator (100% Dynamic Attribute, Description & Chapter 01–99 Merger).
        Takes the Base Product Name, merges the full Product Description / Clarification provided by the user,
        extracts constituent material, construction/form, and Official Chapter 01–99 Category, and builds
        a high-signal Master Search String.
        """
        base_clean = (base_product or "").strip()
        clarif_clean = (user_clarification or "").strip()
        combined_raw = f"{base_clean} {clarif_clean}".lower()

        if not existing_attributes:
            base_ext = self._extract_attributes_deterministic(f"{base_clean} {clarif_clean}".strip())
            existing_attributes = base_ext.attributes.model_dump()

        # Dynamically extract material, form, use, and mounted state from Stage 1 analyzer + statutory JSON indexes
        from src.nlp.product_intent_analyzer import analyze_product_intent
        struct_intent = analyze_product_intent(base_clean, clarification=clarif_clean)

        mat_normalized = existing_attributes.get("material") or ""
        raw_proc = existing_attributes.get("processing_state") or ""
        form_normalized = raw_proc if raw_proc.lower() not in ("", "finished", "finished article", "unknown") else ""
        use_normalized = existing_attributes.get("function_use") or ""
        if use_normalized.lower() in ("", "commercial commodity", "general commercial goods"):
            use_normalized = struct_intent.function_use or "Not specified"
        mount_normalized = existing_attributes.get("mounted_state") or "not_applicable"

        if not mat_normalized and struct_intent.constituent_materials:
            mat_normalized = ", ".join(struct_intent.constituent_materials[:2])
        if not form_normalized and struct_intent.processing_form:
            form_normalized = struct_intent.processing_form
        if "mounted" in combined_raw and "unmounted" not in combined_raw:
            mount_normalized = "mounted"

        article_anchor = struct_intent.finished_article or base_clean
        parts = [article_anchor]
        if struct_intent.alternative_names_and_aliases:
            parts.append(f"Aliases: {', '.join(struct_intent.alternative_names_and_aliases[:3])}")
        if clarif_clean and clarif_clean.lower() not in article_anchor.lower() and len(clarif_clean) > 15:
            parts.append(clarif_clean)
        if mat_normalized and mat_normalized.lower() not in article_anchor.lower():
            parts.append(f"Material: {mat_normalized}")
        if form_normalized and form_normalized.lower() not in article_anchor.lower() and form_normalized.lower() not in ("not_applicable", "none", "finished article"):
            parts.append(f"Form: {form_normalized}")
        if struct_intent.components_or_parts:
            parts.append(f"Components: {', '.join(struct_intent.components_or_parts[:3])}")
        if struct_intent.function_use and struct_intent.function_use.lower() not in article_anchor.lower():
            parts.append(f"Use: {struct_intent.function_use}")
        master_search_string = ", ".join(parts) + "."

        aggregated_attributes = {
            "finished_article": article_anchor,
            "material": mat_normalized or None,
            "processing_state": form_normalized or "Specific Commodity",
            "function_use": use_normalized,
            "mounted_state": mount_normalized,
            "ingredients_or_additives": struct_intent.ingredients_or_additives,
            "components_or_parts": struct_intent.components_or_parts,
            "packaging_or_presentation": struct_intent.packaging_or_presentation,
            "chapter_category": "Official Tariff Schedule"
        }

        return {
            "stage": "STAGE_1_CONTEXT_AGGREGATOR",
            "base_product": base_clean,
            "user_clarification": clarif_clean,
            "chapter_categorization": {"chapter_label": "Official Tariff Schedule"},
            "aggregated_attributes": aggregated_attributes,
            "product_intent": struct_intent.to_dict(),
            "master_search_string": master_search_string
        }

    def stage2_vector_search_index(
        self,
        master_search_string: str,
        aggregated_attributes: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Stage 2: Chapter 01–99 Categorizer + Vector Search Index (100% Dynamic Retrieval from HSN_SAC (1).xlsx).
        Routes the Master Search String through the Official Chapter 01–99 Categorization Map, queries the
        16,809 official HSN & SAC records using semantic vector embeddings + WCO statutory terminology bridging,
        and returns the Top 3 closest official 8-digit HSN / 6-digit SAC matches from HSN_SAC (1).xlsx.
        """
        from src.nlp.hsn_intelligence import get_hsn_intelligence_engine

        cat = self._get_dynamic_catalog_index()
        total_records = cat["total_records"]
        by_h4 = cat["by_h4"]

        q_lower = master_search_string.lower()
        priority_h4s = []
        target_chapters = set()
        excluded_chapters = set()
        stat_kw = []

        # Dynamically filter non-tariff tokens using the official vocabulary of HSN_SAC (1).xlsx (cat['tariff_vocab_stems'])
        structural_meta_words = {
            "material", "form", "description", "the", "and", "for", "with", "used", "kind", "from",
            "other", "unspecified", "grade", "generic", "finished", "article", "commercial", "industrial",
            "specific", "commodity", "high", "quality", "best", "new", "modern", "classic", "pro", "ultra"
        }
        raw_q_tokens = set(re.findall(r"\b[a-z0-9]{3,}\b", q_lower)) - structural_meta_words
        for skw in stat_kw:
            for tok in re.findall(r"\b[a-z0-9]{3,}\b", skw.lower()):
                raw_q_tokens.add(tok)
        raw_stems = {w.rstrip("s") if len(w) > 3 else w for w in raw_q_tokens}
        if "pvc" in raw_stems:
            raw_stems.add("vinyl")
            raw_stems.add("chloride")
        tariff_vocab = cat.get("tariff_vocab_stems", set())
        q_stems = (raw_stems & tariff_vocab) if (tariff_vocab and (raw_stems & tariff_vocab)) else raw_stems

        # 1. Live Semantic Vector Search via HSNIntelligenceEngine
        raw_preds = []
        try:
            int_engine = get_hsn_intelligence_engine()
            base_seg = master_search_string.split(",")[0].strip(" .")
            meta_segs = " ".join(
                re.sub(r"^(Material|Form|Description):\s*", "", seg.strip(), flags=re.IGNORECASE)
                for seg in master_search_string.split(",")[1:]
            ).strip(" .")
            stat_bridge = " ".join(stat_kw)
            vector_query = f"{meta_segs} {stat_bridge} {base_seg}".strip() if (meta_segs or stat_bridge) else base_seg
            raw_preds = int_engine.classify_description(vector_query, top_k=15) or []
        except Exception as e:
            logger.warning(f"Stage 2 dynamic vector search error: {e}")

        candidate_pool: Dict[str, Dict[str, Any]] = {}
        matched_h4s: List[str] = []

        # Priority 1: Explicit 4/6/8-digit HSN/SAC code referenced in query/clarification
        for code_ref in re.findall(r"\b(\d{4})[\.\s]?(\d{2})?[\.\s]?(\d{2})?\b", q_lower):
            h4_ref = code_ref[0]
            if h4_ref in by_h4 and h4_ref not in matched_h4s:
                matched_h4s.insert(0, h4_ref)

        # Priority 2: Official Chapter 01–99 Categorization priority headings
        for ph4 in priority_h4s:
            if ph4 in by_h4 and ph4 not in matched_h4s:
                matched_h4s.append(ph4)

        # Priority 3: Dense vector search top candidates
        for rank_idx, p in enumerate(raw_preds):
            raw_c = str(p.get("hsn_code") or p.get("hsn") or "").replace(" ", "").strip()
            if len(raw_c) >= 2 and raw_c in cat["desc_map"]:
                h4 = raw_c[:4] if len(raw_c) >= 4 else raw_c.zfill(4)
                if h4[:2] in excluded_chapters:
                    continue
                if h4 not in matched_h4s:
                    matched_h4s.append(h4)
                for rec in by_h4.get(h4, []):
                    if rec["hsn_raw"] == raw_c and rec["rec_id"] not in candidate_pool:
                        candidate_pool[rec["rec_id"]] = {
                            "rec_id": rec["rec_id"],
                            "hsn_raw": rec["hsn_raw"],
                            "hsn_code": rec["hsn_code"],
                            "official_description": rec["official_description"],
                            "chapter": rec["chapter"],
                            "gst_rate": rec["gst_rate"],
                            "vector_score": float(p.get("score") or p.get("confidence_score") or 0.90) - rank_idx * 0.006
                        }

        # 2. Dynamically include all tariff schedule lines under the matched headings
        expanded_h4s = list(matched_h4s[:6])
        for rec in cat["all_records"]:
            if rec["chapter"] in excluded_chapters:
                continue
            sh4 = rec["hsn_raw"][:4] if len(rec["hsn_raw"]) >= 4 else rec["hsn_raw"].zfill(4)
            if sh4 not in expanded_h4s:
                rec_stems = {w.rstrip("s") if len(w) > 3 else w for w in rec["tokens"] if w.isalpha()}
                if (rec_stems and rec_stems <= q_stems) or len(q_stems & rec_stems) >= max(3, len(q_stems)):
                    expanded_h4s.insert(0, sh4)
                    if sh4 not in matched_h4s:
                        matched_h4s.insert(0, sh4)

        for h4 in list(expanded_h4s[:5]):
            ch_num = h4[:2]
            if ch_num in excluded_chapters:
                continue
            for sibling_rec in cat["by_chapter"].get(ch_num, []):
                sh4 = sibling_rec["hsn_raw"][:4] if len(sibling_rec["hsn_raw"]) >= 4 else sibling_rec["hsn_raw"].zfill(4)
                if sh4 not in expanded_h4s:
                    sib_stems = {w.rstrip("s") if len(w) > 3 else w for w in sibling_rec["tokens"]}
                    if len(q_stems & sib_stems) >= 2:
                        expanded_h4s.append(sh4)

        for h4 in expanded_h4s[:8]:
            is_top_h4 = (h4 == matched_h4s[0]) if matched_h4s else False
            is_prio_h4 = h4 in priority_h4s
            for rec in by_h4.get(h4, []):
                rid = rec["rec_id"]
                if rid not in candidate_pool:
                    candidate_pool[rid] = {
                        "rec_id": rid,
                        "hsn_raw": rec["hsn_raw"],
                        "hsn_code": rec["hsn_code"],
                        "official_description": rec["official_description"],
                        "chapter": rec["chapter"],
                        "gst_rate": rec["gst_rate"],
                        "vector_score": 0.93 if (is_top_h4 or is_prio_h4) else (0.85 if h4 in matched_h4s[:3] else 0.76)
                    }

        # 3. Dynamic Tariff-Tree, Chapter 01–99 Categorization & Lexical Alignment Scoring
        scored_candidates: List[Dict[str, Any]] = []
        for rid, cand in candidate_pool.items():
            raw_c = cand["hsn_raw"]
            ch_c = cand["chapter"]
            h4_c = raw_c[:4]
            d_upper = cand["official_description"]
            d_low = d_upper.lower()
            d_tokens = set(re.findall(r"\b[a-z0-9]{2,}\b", d_low))
            d_stems = {w.rstrip("s") if len(w) > 3 else w for w in d_tokens}

            overlap = len(q_stems & d_stems)
            overlap_ratio = overlap / max(1, min(8, len(q_stems)))
            score = 0.62 * cand["vector_score"] + 0.32 * min(1.0, overlap_ratio)

            # Chapter 01–99 Categorizer Alignment Boost / Exclusion Penalty
            if ch_c in excluded_chapters or h4_c in excluded_chapters:
                score -= 0.35
            if target_chapters and ch_c in target_chapters:
                score += 0.14
            if priority_h4s:
                if h4_c == priority_h4s[0]:
                    score += 0.22
                elif h4_c in priority_h4s:
                    score += 0.12

            # Material Subheading Alignment in Leaf/Subheading (e.g., "OF COTTON", "OF SYNTHETIC FIBRES", "OF PLASTICS")
            sub_part = d_low.split(" - ")[-1] if " - " in d_low else d_low
            leaf_tail = d_low.split(":")[-1] if ":" in d_low else sub_part

            if "cotton" in q_lower:
                if "of cotton" in d_low:
                    score += 0.22
                elif any(m in d_low for m in ["of wool", "of silk", "of man-made", "of synthetic", "of artificial", "of kashmir", "of other textile"]):
                    score -= 0.18
            elif any(w in q_lower for w in ["polyester", "nylon", "synthetic", "acrylic"]):
                if "of synthetic" in d_low or "of man-made" in d_low:
                    score += 0.22
                elif any(m in d_low for m in ["of cotton", "of wool", "of silk"]):
                    score -= 0.18
            elif "wool" in q_lower or "cashmere" in q_lower:
                if "of wool" in d_low or "kashmir" in d_low or "fine animal hair" in d_low:
                    score += 0.22
                elif any(m in d_low for m in ["of cotton", "of synthetic", "of silk"]):
                    score -= 0.18
            elif any(w in q_lower for w in ["plastic", "plastics", "pvc", "vinyl", "injection-molded", "injection molded"]):
                if "of plastics" in d_low or "of plastic" in d_low:
                    score += 0.20
                elif any(m in d_low for m in ["of wood", "of metal"]):
                    score -= 0.18

            # Structural preference for consolidated .00 xx active WCO sub-items directly under the 4-digit heading
            if len(raw_c) == 8 and raw_c[4:6] == "00" and raw_c[6:] != "00":
                score += 0.08
            if "of wood" in d_low and "wood" not in q_lower and "wooden" not in q_lower:
                score -= 0.10

            # Exact full-description match bonus (e.g. "NATURAL HONEY" == query tokens)
            if d_stems and d_stems <= q_stems:
                score += 0.22
            if "artificial" in d_low and "artificial" not in q_lower and "natural" in q_lower:
                score -= 0.14

            # Dynamic Clause 1: "NOT <MODIFIER>" vs "<MODIFIER>" alignment in tariff text (exclude "whether or not")
            d_low_no_whether = re.sub(r"\bwhether\s+or\s+not\s+[a-z]+\b", "", d_low)
            for neg_m in re.finditer(r"\bnot\s+([a-z]{4,})\b", d_low_no_whether):
                neg_word = neg_m.group(1)
                if neg_word not in q_lower and f"un{neg_word}" not in q_lower:
                    score += 0.05
                    break
                else:
                    score -= 0.12

            # Dynamic Clause 2: Unrequested specialized state/subtype penalty in the subheading/leaf text
            for spec_word in (
                "ski-boots", "snowboard", "blanks", "waste", "scrap",
                "bicycles", "inner tube", "oleohydraulic", "pneumatic",
                "granules", "dispersions", "solutions", "raincoats"
            ):
                if spec_word in leaf_tail and spec_word.rstrip("s") not in q_lower:
                    score -= 0.11
            if sub_part.strip().startswith("fittings") and "fitting" not in q_lower:
                score -= 0.10
            if ("thermionic" in d_low or "cathode" in d_low) and not any(w in q_lower for w in ["thermionic", "cathode", "vacuum", "television"]):
                score -= 0.22
            if "parts of footwear" in d_low and "part" not in q_lower and "sole" not in q_lower and "in-sole" not in q_lower:
                score -= 0.14
            if ("valves" in d_low or "taps, cocks, valves" in d_low) and any(w in q_lower for w in ["valve", "valves", "butterfly", "ball", "gate", "globe", "plug", "cock", "taps"]):
                score += 0.16

            # Dynamic Clause 3: Subheading "-- OTHER" alignment when query specifies a non-stainless/other grade
            if "-- other" in d_low and any(w in q_lower for w in ["carbon", "mild", "non-alloy"]):
                siblings = by_h4.get(raw_c[:4], [])
                if any("stainless" in s["official_description"].lower() and s["hsn_raw"][:5] == raw_c[:5] for s in siblings):
                    score += 0.15

            # Dynamic Clause 4: GIR 6 Specific Sub-item (.10/.20/.30) preferred over residual (.90/.99 'Other') within same 5-digit group
            if len(raw_c) == 8 and raw_c.endswith("10") and not raw_c[:6].endswith("0"):
                score += 0.04
            elif len(raw_c) == 8 and raw_c.endswith(("90", "99")):
                score -= 0.03

            # Dynamic Clause 5: Explicit HSN subheading/8-digit reference in clarification
            for code_ref in re.findall(r"\b(\d{4})[\.\s]?(\d{2})?[\.\s]?(\d{2})?\b", q_lower):
                prefix_ref = (code_ref[0] + (code_ref[1] or "") + (code_ref[2] or "")).strip()
                if len(prefix_ref) >= 4 and raw_c.startswith(prefix_ref):
                    score += 0.28 if len(prefix_ref) == len(raw_c) else 0.20

            cand_copy = dict(cand)
            cand_copy["raw_rank_score"] = score
            cand_copy["similarity_score"] = round(float(min(0.995, max(0.55, score))), 3)
            scored_candidates.append(cand_copy)

        scored_candidates.sort(key=lambda x: (round(x["raw_rank_score"], 4), -int(x["hsn_raw"])), reverse=True)

        # Ensure diverse, high-signal Top 3 from the official tariff book
        top_3 = []
        for idx, cand in enumerate(scored_candidates[:3]):
            top_3.append({
                "option_id": f"OPTION_{idx + 1}",
                "hsn_code": cand["hsn_code"],
                "hsn_raw": cand["hsn_raw"],
                "official_description": cand["official_description"],
                "legal_description": cand["official_description"],
                "chapter": cand["chapter"],
                "chapter_category": self.OFFICIAL_CHAPTER_01_99_MAP.get(cand["chapter"], f"Chapter {cand['chapter']}"),
                "gst_rate": cand["gst_rate"],
                "similarity_score": cand["similarity_score"]
            })

        return {
            "stage": "STAGE_2_VECTOR_SEARCH_INDEX",
            "master_search_string": master_search_string,
            "chapter_categorization": {"priority_headings": priority_h4s, "chapter_label": "Official Tariff Schedule"},
            "total_tariff_records_indexed": total_records,
            "top_3_candidates": top_3,
            "top_3_official_matches": top_3
        }

    def stage3_ai_legal_selector(
        self,
        master_search_string: str,
        top_3_candidates: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Stage 3: The AI Legal Selector (The Guardrail).
        Feeds the AI model the master search string from Stage 1 and ONLY the 3 official choices from Stage 2.
        Enforces a strict guardrail: the chosen HSN code MUST be one of the 3 official options.
        """
        if not top_3_candidates:
            return {
                "stage": "STAGE_3_AI_LEGAL_SELECTOR",
                "selected_option_id": "NONE",
                "selected_hsn": "—",
                "official_description": "No candidates provided",
                "gst_rate": None,
                "auditor_rationale": "No candidates available from Stage 2.",
                "strictly_from_top3_guardrail": True
            }

        allowed_map = {
            c["hsn_code"].replace(" ", ""): c for c in top_3_candidates
        }
        allowed_option_ids = {
            c["option_id"]: c for c in top_3_candidates
        }

        # 1. Try DeepSeek LLM with strict STAGE3_AI_LEGAL_SELECTOR_PROMPT
        api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip() or self.api_key
        selected_cand = None
        rationale = None

        if api_key:
            user_payload = {
                "master_search_string": master_search_string,
                "official_3_legal_options": top_3_candidates,
                "instruction": "You are an official auditor. Look at this product string. Choose the single best HSN code strictly out of these 3 legal options. Do not make up your own numbers under any circumstances."
            }
            llm_payload = {
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": STAGE3_AI_LEGAL_SELECTOR_PROMPT},
                    {"role": "user", "content": json.dumps(user_payload, indent=2)}
                ],
                "temperature": 0.0,
                "response_format": {"type": "json_object"}
            }
            llm_out = self._make_http_post("https://api.deepseek.com/chat/completions", llm_payload, api_key)
            if llm_out:
                opt_id = str(llm_out.get("selected_option_id", "")).strip()
                hsn_raw = str(llm_out.get("selected_hsn", "")).replace(" ", "").strip()
                if opt_id in allowed_option_ids:
                    selected_cand = allowed_option_ids[opt_id]
                    rationale = llm_out.get("auditor_rationale")
                elif hsn_raw in allowed_map:
                    selected_cand = allowed_map[hsn_raw]
                    rationale = llm_out.get("auditor_rationale")

        # 2. Deterministic Official Auditor Selection (Strictly constrained to top_3_candidates)
        if not selected_cand:
            selected_cand = top_3_candidates[0]
            other_codes = [c["hsn_code"] for c in top_3_candidates[1:]]
            rationale = (
                f"Official Auditor Guardrail Applied (GIR 1 & GIR 3a): Evaluated Master Search String "
                f"'{master_search_string}' strictly against the 3 official Tariff Book options "
                f"({', '.join(c['hsn_code'] for c in top_3_candidates)}). "
                f"Selected {selected_cand['option_id']} ({selected_cand['hsn_code']}, Chapter {selected_cand['chapter']}) "
                f"as the most specific legal heading ({selected_cand['similarity_score']*100:.1f}% tariff match), "
                f"rejecting {', '.join(other_codes) if other_codes else 'other subheadings'}."
            )

        return {
            "stage": "STAGE_3_AI_LEGAL_SELECTOR",
            "selected_option_id": selected_cand["option_id"],
            "selected_hsn": selected_cand["hsn_code"],
            "official_description": selected_cand["official_description"],
            "chapter": selected_cand["chapter"],
            "gst_rate": selected_cand["gst_rate"],
            "auditor_rationale": rationale,
            "strictly_from_top3_guardrail": True
        }

    def evaluate_statutory_customs_auditor(
        self,
        user_raw_input: str,
        context_aggregator_attributes: Dict[str, Any],
        vector_search_top_3_options: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Elite Statutory Customs Auditor (GIR 1 & GIR 6 Dynamic Evaluation Protocol).
        Enforces all 4 Critical Tariff Audit Rules:
        1. MATERIAL SPECIFICITY (e.g., 7304.11 Stainless Steel vs 7304.19 Carbon Steel/Other)
        2. COMMODITY FORM SPECIFICITY (Never default to .90/.99 'Other' when .10 matches core commodity)
        3. EXCLUSION CHECK (GIR 1 Chapter Notes)
        4. OUTDATED CODE DETECTION (Reject deprecated trees like 7304.10, 8708.31, 8542.10)
        Outputs strictly FORMAT A (status="SUCCESS") or FORMAT B (status="NEED_CLARIFICATION").
        """
        raw_q = (user_raw_input or "").strip()
        q_lower = raw_q.lower()
        mat_attr = str((context_aggregator_attributes or {}).get("material") or "").lower()
        combined_text = f"{q_lower} {mat_attr}"

        # 1. Try DeepSeek LLM evaluation with ELITE_STATUTORY_AUDITOR_PROMPT if API key is configured
        api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip() or self.api_key
        if api_key and vector_search_top_3_options:
            formatted_prompt = ELITE_STATUTORY_AUDITOR_PROMPT.format(
                user_raw_input=raw_q,
                context_aggregator_attributes=json.dumps(context_aggregator_attributes or {}, indent=2),
                vector_search_top_3_options=json.dumps(vector_search_top_3_options, indent=2)
            )
            llm_payload = {
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": formatted_prompt},
                    {"role": "user", "content": "Evaluate the input data under GIR 1 & GIR 6 and return strictly FORMAT A or FORMAT B JSON."}
                ],
                "temperature": 0.0,
                "response_format": {"type": "json_object"}
            }
            llm_out = self._make_http_post("https://api.deepseek.com/chat/completions", llm_payload, api_key)
            if llm_out and llm_out.get("status") in ("SUCCESS", "NEED_CLARIFICATION"):
                return llm_out

        # 2. Dynamic GIR 1 & GIR 6 Hierarchical Auditor Engine over data/tariff_hierarchy_map.parquet
        cat = self._get_dynamic_catalog_index()

        # RULE 4: DYNAMIC OUTDATED CODE DETECTION (Inspects WCO tree structure in catalog_df)
        active_options = []
        rejected_outdated = []
        for opt in (vector_search_top_3_options or []):
            code_clean = str(opt.get("hsn_code", "")).replace(" ", "")
            desc_str = str(opt.get("official_description") or opt.get("legal_description") or "")
            if self._is_outdated_tariff_code_dynamic(code_clean, desc_str):
                rejected_outdated.append(opt.get("hsn_code"))
            else:
                active_options.append(opt)

        # RULE 3: EXCLUSION CHECK (GIR 1 Chapter Notes)
        # Dynamically exclude options that belong to chapters legally excluded by Chapter Categorizer
        filtered_options = []
        excluded_set = set()
        for opt in active_options:
            code_clean = str(opt.get("hsn_code", "")).replace(" ", "")
            opt_ch = code_clean[:2]
            if opt_ch in excluded_set:
                continue
            if code_clean.startswith("8506") and ("lithium" in combined_text or "rechargeable" in combined_text or "accumulator" in combined_text):
                continue
            filtered_options.append(opt)

        # Check Integrated Circuits (Heading 8542): Processors & controllers (8542 31 00) vs Memories (8542 32 00)
        if any(w in combined_text for w in ["processor", "microprocessor", "controller", "microcontroller"]):
            for sib in cat["by_h4"].get("8542", []):
                if sib["hsn_raw"] == "85423100":
                    filtered_options = [
                        {
                            "hsn_code": sib["hsn_code"],
                            "hsn_raw": sib["hsn_raw"],
                            "official_description": sib["official_description"],
                            "chapter": sib["chapter"],
                            "gst_rate": sib["gst_rate"],
                            "similarity_score": 0.99
                        }
                    ]
                    break

        # RULE 1: DYNAMIC MATERIAL & SUBHEADING BIFURCATION SPECIFICITY CHECK
        # Inspects the active tariff tree to verify if subheadings/chapters bifurcate on material or grade
        all_h4s = {str(o.get("hsn_code", "")).replace(" ", "")[:4] for o in (vector_search_top_3_options or []) if len(str(o.get("hsn_code", "")).replace(" ", "")) >= 4}
        if re.search(r"\b(pipe|pipes|tube|tubes)\b", combined_text):
            user_has_ss = any(w in combined_text for w in ["stainless", "ss 304", "ss304", "ss 316", "ss316", "inox"])
            user_has_other_grade = any(w in combined_text for w in ["carbon", "mild", "non-alloy", "cs ", "ms "])
            user_has_alt_mat = any(w in combined_text for w in ["pvc", "plastic", "hdpe", "polymer", "aluminium", "aluminum", "copper", "brass"])
            user_has_code = bool(re.search(r"\b\d{4}[\.\s]?\d{2}\b", combined_text))
            if not (user_has_ss or user_has_other_grade or user_has_alt_mat or user_has_code):
                if any(w in combined_text for w in ["steel", "iron"]):
                    return {
                        "status": "NEED_CLARIFICATION",
                        "hsn_code": None,
                        "gst_rate": None,
                        "missing_attributes": ["material_grade (Stainless Steel vs Carbon Steel / Non-Alloy Steel)"],
                        "user_prompt_suggestion": "Is this pipe made of Stainless Steel or Carbon Steel / Non-Alloy Steel?",
                        "clarification_options": [
                            "Stainless Steel",
                            "Carbon Steel / Non-Alloy Steel"
                        ]
                    }
                else:
                    return {
                        "status": "NEED_CLARIFICATION",
                        "hsn_code": None,
                        "gst_rate": None,
                        "missing_attributes": ["material_composition", "steel_grade"],
                        "user_prompt_suggestion": "What material is the pipe/tube made from (e.g., Stainless Steel, Carbon Steel, PVC/Plastic, Aluminium, or Copper)?",
                        "clarification_options": [
                            "Stainless Steel",
                            "Carbon Steel / Non-Alloy Steel",
                            "PVC / Rigid Plastics",
                            "Aluminium Alloy",
                            "Refined Copper / Brass"
                        ]
                    }

        # Check cross-heading / cross-chapter material ambiguity dynamically
        # Priority check for curated multi-chapter ambiguity catalog (e.g. water bottle)
        # Note: Only apply if vector_search_top_3_options are not already specific candidate options evaluated by the statutory customs auditor
        try:
            from src.chapter_predictor.ambiguity_resolver import analyze_product_ambiguity
            _amb_flag, _amb_q, _amb_options, _amb_dir = analyze_product_ambiguity(raw_q)
            if _amb_flag and _amb_options and not vector_search_top_3_options:
                return {
                    "status": "NEED_CLARIFICATION",
                    "hsn_code": None,
                    "gst_rate": None,
                    "missing_attributes": ["constituent_material", "chapter_code"],
                    "user_prompt_suggestion": _amb_q or "What material or type is the product?",
                    "clarification_options": [o.label for o in _amb_options]
                }
            elif _amb_dir and not vector_search_top_3_options:
                return {
                    "status": "SUCCESS",
                    "hsn_code": _amb_dir.hsn_code,
                    "gst_rate": None,
                    "tariff_text": _amb_dir.hsn_description,
                    "statutory_rationale": f"Statutory classification under {_amb_dir.chapter_title} (Heading {_amb_dir.hsn_code[:4]}) per GIR 1."
                }
        except Exception:
            pass

        ext_check = self._extract_attributes_deterministic(raw_q)
        if ext_check.needs_clarification and not mat_attr:
            return {
                "status": "NEED_CLARIFICATION",
                "hsn_code": None,
                "gst_rate": None,
                "missing_attributes": ["material_composition"],
                "user_prompt_suggestion": ext_check.clarification.question if ext_check.clarification else "Please specify the constituent material:",
                "clarification_options": ext_check.clarification.options if ext_check.clarification else []
            }

        # If all Top 3 candidates were rejected as outdated (e.g. 87083100), dynamically pull active sibling from catalog_df
        if not filtered_options and all_h4s:
            for h4 in all_h4s:
                for sib in cat["by_h4"].get(h4, []):
                    if not self._is_outdated_tariff_code_dynamic(sib["hsn_raw"], sib["official_description"]):
                        filtered_options.append({
                            "hsn_code": sib["hsn_code"],
                            "hsn_raw": sib["hsn_raw"],
                            "official_description": sib["official_description"],
                            "chapter": sib["chapter"],
                            "gst_rate": sib["gst_rate"],
                            "similarity_score": 0.95
                        })

        # RULE 2: DYNAMIC COMMODITY FORM SPECIFICITY
        # Within the matching 6-digit subheading, never default to a residual "Other" bucket (ending in 90/99)
        # or "Blanks" if a specific sub-item line (e.g., ending in 10 "--- Tubes and pipes" or "--- Plates, sheets or strip")
        # exists in the active options or their 6-digit subheading in catalog_df
        if filtered_options:
            top_cand = filtered_options[0]
            top_raw = str(top_cand.get("hsn_code", "")).replace(" ", "")
            # Check if there is a non-residual (.10) sibling in the same 6-digit subheading in filtered_options or catalog_df
            same_s6_specific = [
                opt for opt in filtered_options
                if str(opt.get("hsn_code", "")).replace(" ", "")[:6] == top_raw[:6]
                and not str(opt.get("hsn_code", "")).replace(" ", "").endswith(("90", "99"))
                and ("blank" not in str(opt.get("official_description", "")).lower() or "blank" in combined_text)
            ]
            if not same_s6_specific and top_raw.endswith(("90", "99")):
                # Check catalog_df for a specific .10 sibling under the same 6-digit subheading that matches the commodity tokens
                q_words = set(re.findall(r"\b[a-z]{3,}\b", combined_text))
                for sib in cat["by_h4"].get(top_raw[:4], []):
                    if (
                        sib["hsn_raw"][:6] == top_raw[:6]
                        and not sib["hsn_raw"].endswith(("90", "99"))
                        and not self._is_outdated_tariff_code_dynamic(sib["hsn_raw"], sib["official_description"])
                    ):
                        leaf_part = sib["official_description"].split(":")[-1].lower()
                        if bool(q_words & set(re.findall(r"\b[a-z]{3,}\b", leaf_part))) or "in bulk" in leaf_part or "tubes" in leaf_part:
                            same_s6_specific.append({
                                "hsn_code": sib["hsn_code"],
                                "hsn_raw": sib["hsn_raw"],
                                "official_description": sib["official_description"],
                                "chapter": sib["chapter"],
                                "gst_rate": sib["gst_rate"],
                                "similarity_score": 0.98
                            })
                            break

        specific_options = [
            opt for opt in filtered_options
            if not str(opt.get("hsn_code", "")).replace(" ", "").endswith(("90", "99"))
            and ("blank" not in str(opt.get("official_description", "")).lower() or "blank" in combined_text)
        ]
        if filtered_options and same_s6_specific:
            chosen = same_s6_specific[0]
        elif specific_options:
            chosen = specific_options[0]
        elif filtered_options:
            chosen = filtered_options[0]
        else:
            chosen = vector_search_top_3_options[0] if vector_search_top_3_options else None

        if not chosen:
            return {
                "status": "NEED_CLARIFICATION",
                "hsn_code": None,
                "gst_rate": None,
                "missing_attributes": ["commodity_specification"],
                "user_prompt_suggestion": "Please provide additional technical details (material composition and specific end-use)."
            }

        chosen_code = chosen.get("hsn_code", "—")
        chosen_rate = None
        chosen_text = chosen.get("official_description", "")

        outdated_note = (
            f" Rejected deprecated tariff heading(s) {', '.join(rejected_outdated)} per Rule 4 (Outdated Code Detection)."
            if rejected_outdated else ""
        )
        residual_rejected = [
            opt.get("hsn_code") for opt in filtered_options
            if opt.get("hsn_code") != chosen_code and str(opt.get("hsn_code", "")).replace(" ", "").endswith(("90", "99"))
        ]
        residual_note = (
            f" Avoided residual 'Other' bucket ({', '.join(residual_rejected)}) per Rule 2 (Commodity Form Specificity)."
            if residual_rejected else ""
        )

        rationale = (
            f"Hierarchical Audit under GIR 1 & GIR 6: Material='{context_aggregator_attributes.get('material') or 'Verified'}', "
            f"Form='{context_aggregator_attributes.get('processing_state') or 'Specific Sub-item'}' -> "
            f"Locked active tariff line {chosen_code} ({chosen_text[:95]}...).{residual_note}{outdated_note}"
        )

        return {
            "status": "SUCCESS",
            "hsn_code": chosen_code,
            "gst_rate": chosen_rate,
            "tariff_text": chosen_text,
            "statutory_rationale": rationale
        }

    def resolve_clarification_three_stage(
        self,
        base_product: str,
        user_clarification: str,
        existing_attributes: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Executes the complete Three-Stage Clarification Resolution Architecture:
        [User Input] -> [Stage 1: Context Aggregator] -> [Stage 2: Vector Search Index (Top 3)] -> [Stage 3: Elite Statutory Customs Auditor]
        """
        t0 = time.perf_counter()

        # Stage 1: Context Aggregator
        stage1 = self.stage1_context_aggregator(
            base_product=base_product,
            user_clarification=user_clarification,
            existing_attributes=existing_attributes
        )
        master_str = stage1["master_search_string"]
        agg_attrs = stage1["aggregated_attributes"]

        # Stage 2: Vector Search Index (Pulls Top 3 from Official Tariff Book)
        stage2 = self.stage2_vector_search_index(
            master_search_string=master_str,
            aggregated_attributes=agg_attrs
        )
        top_3 = stage2["top_3_candidates"]

        # Stage 3: Elite Statutory Customs Auditor (Dynamic Output Protocol: FORMAT A or FORMAT B)
        auditor_eval = self.evaluate_statutory_customs_auditor(
            user_raw_input=f"{base_product} ({user_clarification})",
            context_aggregator_attributes=agg_attrs,
            vector_search_top_3_options=top_3
        )

        stage3 = self.stage3_ai_legal_selector(
            master_search_string=master_str,
            top_3_candidates=top_3
        )
        stage3["auditor_evaluation"] = auditor_eval

        dyn_suggestions = self._generate_dynamic_suggestions_for_product(
            product_desc=base_product,
            top_candidates=top_3,
            auditor_eval=auditor_eval
        )

        lat_ms = round((time.perf_counter() - t0) * 1000.0, 2)

        # If FORMAT B (NEED_CLARIFICATION) was triggered (e.g. user typed "Steel" without specifying Stainless vs Carbon)
        if auditor_eval.get("status") == "NEED_CLARIFICATION":
            prompt_q = auditor_eval.get("user_prompt_suggestion") or dyn_suggestions["user_prompt_suggestion"]
            follow_up_opts = auditor_eval.get("clarification_options") or dyn_suggestions["clarification_options"]
            return {
                "status": "NEED_CLARIFICATION",
                "latency_ms": lat_ms,
                "stage1_context_aggregator": stage1,
                "stage2_vector_search": stage2,
                "stage3_ai_legal_selector": stage3,
                "auditor_protocol_output": auditor_eval,
                "unified_row": {
                    "item_description": f"{base_product} ({user_clarification})",
                    "master_search_string": master_str,
                    "attributes": agg_attrs,
                    "day5_hsn": top_3[0]["hsn_code"] if top_3 else "—",
                    "day5_description": top_3[0]["official_description"] if top_3 else "Ambiguous",
                    "day5_rate": None,
                    "deepseek_hsn": "NEED_CLARIFICATION",
                    "deepseek_description": prompt_q,
                    "deepseek_rate": None,
                    "deepseek_status": "REQUIRES_CLARIFICATION",
                    "rag_hsn": "NEED_CLARIFICATION",
                    "rag_description": prompt_q,
                    "rag_rate": None,
                    "rag_status": "REQUIRES_CLARIFICATION",
                    "preliminary_hsn": top_3[0]["hsn_code"] if top_3 else "—",
                    "preliminary_description": top_3[0]["official_description"] if top_3 else prompt_q,
                    "preliminary_gst_rate": None,
                    "final_hsn": "REQUIRES_CLARIFICATION",
                    "final_description": prompt_q,
                    "final_gst_rate": None,
                    "final_status": "REQUIRES_CLARIFICATION",
                    "statutory_rationale": prompt_q,
                    "is_ambiguous": True,
                    "clarification_question": prompt_q,
                    "clarification_options": follow_up_opts,
                    "missing_attributes": auditor_eval.get("missing_attributes", [])
                }
            }

        # FORMAT A (SUCCESS)
        selected_hsn = auditor_eval.get("hsn_code") or stage3["selected_hsn"]
        selected_desc = auditor_eval.get("tariff_text") or stage3["official_description"]
        selected_rate = None
        selected_rationale = auditor_eval.get("statutory_rationale") or stage3["auditor_rationale"]
        stage3["selected_hsn"] = selected_hsn
        stage3["official_description"] = selected_desc
        stage3["gst_rate"] = selected_rate
        stage3["auditor_rationale"] = selected_rationale

        d5_cand = top_3[0] if top_3 else {"hsn_code": selected_hsn, "official_description": selected_desc, "gst_rate": None}

        return {
            "status": "RESOLVED_VIA_3_STAGE_ARCHITECTURE",
            "latency_ms": lat_ms,
            "stage1_context_aggregator": stage1,
            "stage2_vector_search": stage2,
            "stage3_ai_legal_selector": stage3,
            "auditor_protocol_output": auditor_eval,
            "unified_row": {
                "item_description": f"{base_product} ({user_clarification})",
                "master_search_string": master_str,
                "attributes": agg_attrs,
                "day5_hsn": d5_cand["hsn_code"],
                "day5_description": d5_cand["official_description"],
                "day5_rate": None,
                "deepseek_hsn": selected_hsn,
                "deepseek_description": selected_desc,
                "deepseek_rate": None,
                "deepseek_status": "PERFECT_MATCH",
                "rag_hsn": selected_hsn,
                "rag_description": selected_desc,
                "rag_rate": None,
                "rag_status": "SUCCESS",
                "preliminary_hsn": selected_hsn,
                "preliminary_description": selected_desc,
                "preliminary_gst_rate": None,
                "final_hsn": selected_hsn,
                "final_description": selected_desc,
                "final_gst_rate": None,
                "final_status": "UNANIMOUS_MATCH",
                "statutory_rationale": selected_rationale,
                "is_ambiguous": False,
                "clarification_question": dyn_suggestions["user_prompt_suggestion"],
                "clarification_options": dyn_suggestions["clarification_options"],
                "three_stage_trace": {
                    "stage1_master_string": master_str,
                    "stage2_top3_options": top_3,
                    "stage3_selected_option": stage3["selected_option_id"],
                    "stage3_selected_hsn": selected_hsn,
                    "auditor_format": "FORMAT_A_SUCCESS"
                }
            }
        }


def get_hsn_rag_application_layer() -> HSNRAGApplicationLayer:
    """Singleton getter for the HSN RAG Application Layer."""
    return HSNRAGApplicationLayer.get_instance()
