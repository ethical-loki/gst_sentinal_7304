"""
src/chapter_predictor/llm_rerank.py
===================================
Stage D: Local LLM Reranking & GIR Statutory Disambiguation.

Features:
- Queries local Ollama server at http://localhost:11434 with model 'qwen2.5:7b-instruct'
  (fallback to 'qwen2.5:3b-instruct' / 'qwen2.5:0.5b-instruct' / 'llama3.2').
- Enforces strict JSON Schema constrained decoding.
- Strictly confines choices to the candidate chapters retrieved from Stage B & C.
- Enforces WCO GIR statutory rules (finished article vs material, state & negation handling).
- Gracefully returns None if Ollama is unreachable, allowing Stage E RRF fusion to take over.
- Optional Gemini fallback when CHAPTER_PREDICTOR_USE_GEMINI=true.
"""

import json
import logging
import os
import re
import time
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
PREFERRED_OLLAMA_MODELS = [
    os.environ.get("OLLAMA_CHAPTER_MODEL", "qwen2.5:7b-instruct"),
    "qwen2.5:3b-instruct",
    "qwen2.5:7b",
    "qwen2.5:3b",
    "qwen2.5:0.5b-instruct",
    "qwen2.5:1.5b",
    "llama3.2:3b",
    "llama3.2:1b"
]

# JSON schema for constrained Ollama decoding
OLLAMA_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "chapter": {
            "type": "string",
            "description": "The selected 2-digit HSN chapter code strictly from the candidates list (e.g. '09', '85', '61')"
        },
        "confidence": {
            "type": "number",
            "description": "Confidence score between 0.0 and 1.0"
        },
        "reason": {
            "type": "string",
            "description": "Statutory justification (max 40 words) citing relevant tariff text or Chapter Notes"
        },
        "negation_handled": {
            "type": "boolean",
            "description": "Whether statutory state or negation (roasted, unmounted, knitted, etc.) was evaluated"
        }
    },
    "required": ["chapter", "confidence", "reason", "negation_handled"]
}


class LLMRerankResult(BaseModel):
    chapter: str
    confidence: float
    reason: str
    negation_handled: bool
    model_used: str


class LocalLLMReranker:
    """
    Reranks candidate chapters using local Ollama LLM with JSON schema enforcement.
    """
    def __init__(self, ollama_url: str = OLLAMA_BASE_URL):
        self.ollama_url = ollama_url
        self._active_model: Optional[str] = None
        self._is_ollama_available: Optional[bool] = None
        self._cached_health: Optional[Tuple[bool, List[str]]] = None
        self._cached_health_time: float = 0.0

    def check_ollama_health(self) -> Tuple[bool, List[str]]:
        """Checks if local Ollama server is reachable and lists installed models (cached for 15s)."""
        now = time.time()
        if self._cached_health is not None and (now - self._cached_health_time) < 15.0:
            return self._cached_health

        try:
            url = f"{self.ollama_url}/api/tags"
            req = urllib.request.Request(url, headers={"User-Agent": "GSTSentinel/1.0"})
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                models = [m.get("name", "") for m in data.get("models", [])]
                self._is_ollama_available = True
                self._cached_health = (True, models)
                self._cached_health_time = now
                return True, models
        except Exception:
            self._is_ollama_available = False
            self._cached_health = (False, [])
            self._cached_health_time = now
            return False, []

    def _select_ollama_model(self, available_models: List[str]) -> Optional[str]:
        """Chooses the best available installed model."""
        avail_lower = [m.lower() for m in available_models]
        for pref in PREFERRED_OLLAMA_MODELS:
            pref_low = pref.lower()
            for idx, m_low in enumerate(avail_lower):
                if pref_low in m_low or m_low.startswith(pref_low.split(":")[0]):
                    return available_models[idx]
        return available_models[0] if available_models else None

    def rerank(
        self,
        query: str,
        candidates: List[Dict[str, Any]]
    ) -> Optional[LLMRerankResult]:
        """
        Executes Stage D LLM Reranking:
        - Constructs GIR-grounded prompt with candidate chapters & evidence tariff lines
        - Invokes Ollama with JSON schema constraint
        - Validates that the returned chapter is strictly from candidate list
        """
        if not candidates:
            return None

        # Check optional Gemini override
        if os.environ.get("CHAPTER_PREDICTOR_USE_GEMINI", "").lower() == "true":
            gemini_res = self._try_gemini_rerank(query, candidates)
            if gemini_res:
                return gemini_res

        # Check Ollama availability
        is_up, avail_models = self.check_ollama_health()
        if not is_up or not avail_models:
            return None

        chosen_model = self._select_ollama_model(avail_models)
        if not chosen_model:
            return None

        valid_candidate_codes = [str(c["chapter"]).zfill(2) for c in candidates]

        # Build candidate presentation
        candidate_blocks = []
        for c in candidates[:10]:
            ch = str(c["chapter"]).zfill(2)
            title = c.get("chapter_title", "")
            ev_lines = c.get("evidence_lines", [])
            lines_summary = "; ".join(
                f"{l['hsn_code']}: {l['description'][:75]}"
                for l in ev_lines[:3]
            ) or "General Chapter classification"
            candidate_blocks.append(f"- Chapter {ch} ({title}):\n  Evidence: {lines_summary}")

        candidates_text = "\n".join(candidate_blocks)

        prompt = f"""You are an elite statutory Customs Tariff Classification Officer operating under the Harmonized System (HSN / ITC-HS).

PRODUCT DESCRIPTION: "{query}"

CANDIDATE CHAPTERS (Choose ONLY from this list):
{candidates_text}

STATUTORY CLASSIFICATION RULES:
1. Apply the General Rules for the Interpretation (GIR) of the Harmonized System.
2. Essential Character & State: State words like "roasted vs unroasted", "cooked vs raw", "frozen vs fresh", "knitted vs woven", "mounted vs unmounted", and "raw vs manufactured" are legally DECISIVE for chapter selection.
   - Example: Roasted coffee beans belong to Chapter 09 (0901), not raw/plantations or other chapters.
   - Example: Microprocessors & integrated circuits belong to Chapter 85 (8542).
3. Finished Article vs Material: If the product is a finished article or garment, classify under the chapter for the finished article, NOT the chapter of the constituent material (e.g. Cotton shirt -> Chapter 61/62, not Chapter 52).
4. Strictly choose ONE 2-digit chapter from the provided candidate list: {valid_candidate_codes}. NEVER invent an unlisted chapter.

Output strictly valid JSON matching the schema."""

        payload = {
            "model": chosen_model,
            "prompt": prompt,
            "stream": False,
            "format": OLLAMA_JSON_SCHEMA,
            "options": {
                "temperature": 0.0,
                "num_predict": 150
            }
        }

        try:
            req_data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                f"{self.ollama_url}/api/generate",
                data=req_data,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=8.0) as resp:
                resp_json = json.loads(resp.read().decode("utf-8"))
                raw_response = resp_json.get("response", "{}")
                parsed = json.loads(raw_response)

                pred_ch = str(parsed.get("chapter", "")).strip().zfill(2)
                # Strict guardrail: must be in candidate list
                if pred_ch not in valid_candidate_codes:
                    logger.warning(f"Ollama returned chapter {pred_ch} not in candidates {valid_candidate_codes}")
                    return None

                conf = float(parsed.get("confidence", 0.90))
                reason = str(parsed.get("reason", "Classified under GIR 1.")).strip()
                negation_handled = bool(parsed.get("negation_handled", True))

                return LLMRerankResult(
                    chapter=pred_ch,
                    confidence=min(1.0, max(0.0, conf)),
                    reason=reason,
                    negation_handled=negation_handled,
                    model_used=f"ollama/{chosen_model}"
                )
        except Exception as e:
            logger.warning(f"Ollama rerank failed: {e}")
            return None

    def _try_gemini_rerank(
        self,
        query: str,
        candidates: List[Dict[str, Any]]
    ) -> Optional[LLMRerankResult]:
        """Optional remote Gemini fallback if configured."""
        api_key = os.environ.get("GEMINI_API_KEY", "") or os.environ.get("GOOGLE_API_KEY", "")
        if not api_key:
            return None

        valid_candidate_codes = [str(c["chapter"]).zfill(2) for c in candidates]
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
            prompt_text = f"""Classify product '{query}' into ONE of these HSN Chapters: {valid_candidate_codes}.
Return JSON strictly: {{"chapter": "XX", "confidence": 0.95, "reason": "short explanation", "negation_handled": true}}"""
            payload = {
                "contents": [{"parts": [{"text": prompt_text}]}],
                "generationConfig": {"temperature": 0.0, "responseMimeType": "application/json"}
            }
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                text_out = data["candidates"][0]["content"]["parts"][0]["text"]
                parsed = json.loads(text_out)
                pred_ch = str(parsed.get("chapter", "")).strip().zfill(2)
                if pred_ch in valid_candidate_codes:
                    return LLMRerankResult(
                        chapter=pred_ch,
                        confidence=float(parsed.get("confidence", 0.95)),
                        reason=str(parsed.get("reason", "")),
                        negation_handled=bool(parsed.get("negation_handled", True)),
                        model_used="gemini-2.0-flash"
                    )
        except Exception as e:
            logger.warning(f"Gemini fallback failed: {e}")
        return None


# Module singleton
_reranker_instance: Optional[LocalLLMReranker] = None

def get_llm_reranker() -> LocalLLMReranker:
    global _reranker_instance
    if _reranker_instance is None:
        _reranker_instance = LocalLLMReranker()
    return _reranker_instance

