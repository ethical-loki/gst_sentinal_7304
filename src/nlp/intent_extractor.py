"""
src/nlp/intent_extractor.py
===========================
Harden LLM-based Intent Extraction Stage for the HSN Classification Pipeline.
Turns commercial product queries into statutory customs search terms grounded
exclusively in Master_copy_hsn.xlsx under strict row-level co-occurrence rules.

Policies:
- Zero HSN Code Policy: The LLM never produces HSN codes or digit sequences.
- Strict Row-Level Grounding: A term is grounded ONLY if its exact phrase appears,
  or ALL its content words co-occur within the SAME row of the Master file.
- All-Terms-Dropped Safeguard: If all candidate search terms fail grounding,
  the pipeline abstains and never falls back to raw commercial queries.
- Deterministic Caching: Results are cached by (normalized query, model name, file hash).
- Three Out-of-Scope Outcomes: UNRECOGNIZED, OUT_OF_SCHEDULE, AMBIGUOUS_MATERIAL.
- Clarification Loop: Merges user answers into unstated attributes and updates intent.
"""

import os
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
import re
import json
import hashlib
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple
from datetime import datetime

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field, ValidationError, field_validator

logger = logging.getLogger(__name__)

STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "for", "with", "in", "on", "at", "to",
    "from", "by", "is", "are", "was", "were", "be", "been", "being", "as", "than",
    "such", "other", "all", "any", "each", "both", "not", "no", "into", "through"
}

VALID_SCHEDULE_CHAPTERS = {"19", "39", "61", "62", "73", "84", "85", "87", "94"}


def tokenize(text: str) -> List[str]:
    """Lightweight whitespace & punctuation tokenizer."""
    if not text:
        return []
    words = re.findall(r"\b[a-zA-Z0-9]{2,}\b", text.lower())
    return [w for w in words if w not in STOPWORDS]


# =====================================================================
# Strict Schemas
# =====================================================================

class LLMIntentOutput(BaseModel):
    """Strict schema for the LLM output with graceful type normalization."""
    model_config = {"extra": "ignore"}

    physical_product: str = Field(
        ...,
        description="The generic physical product, resolving any brand, slang, or colloquial names."
    )
    material: Optional[str] = Field(
        None,
        description="Constituent material if stated by the user."
    )
    construction: Optional[str] = Field(
        None,
        description="Manufacturing form or construction if stated by the user."
    )
    intended_use: Optional[str] = Field(
        None,
        description="Principal function or application if stated by the user."
    )
    search_terms: List[str] = Field(
        default_factory=list,
        description="Statutory search terms of 1 to 4 words taken from the customs vocabulary."
    )
    unstated_attributes: List[str] = Field(
        default_factory=list,
        description="Attributes required for classification that the user did not state. Do not guess."
    )
    reading_confidence: str = Field(
        default="clear",
        description="Confidence level: 'clear', 'partial', or 'unclear'."
    )

    @field_validator("reading_confidence", mode="before")
    @classmethod
    def normalize_reading_confidence(cls, v: Any) -> str:
        s = str(v or "").lower().strip()
        if s in ("clear", "high", "100", "1", "true", "certain", "very high"):
            return "clear"
        elif s in ("unclear", "low", "0", "false", "vague", "none", "unknown"):
            return "unclear"
        elif s in ("partial", "medium", "moderate"):
            return "partial"
        try:
            num = float(s)
            if num >= 0.70:
                return "clear"
            elif num <= 0.35:
                return "unclear"
            return "partial"
        except Exception:
            return "clear"

    @field_validator("search_terms", "unstated_attributes", mode="before")
    @classmethod
    def normalize_str_list(cls, v: Any) -> List[str]:
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
        if isinstance(v, str) and v.strip():
            return [v.strip()]
        return []


class DroppedTerm(BaseModel):
    term: str
    field_source: str
    reason: str


class IntentExtractionResult(BaseModel):
    raw_query: str
    physical_product: str
    material: Optional[str] = None
    construction: Optional[str] = None
    intended_use: Optional[str] = None
    reading_confidence: str
    outcome_type: str = "SUCCESS"  # SUCCESS | AMBIGUOUS_MATERIAL | OUT_OF_SCHEDULE | UNRECOGNIZED
    grounded_search_terms: List[str]
    unstated_attributes: List[str]
    dropped_terms: List[DroppedTerm] = Field(default_factory=list)
    top_headings_shown: List[str] = Field(default_factory=list)
    is_valid: bool = True
    error_message: Optional[str] = None
    retries_used: int = 0
    synthesized_search_string: str = ""
    is_cache_hit: bool = False
    clarification_merged: bool = False


# =====================================================================
# LLM Client Interfaces
# =====================================================================

class BaseLLMClient(ABC):
    """Abstract interface for LLM interaction."""

    @abstractmethod
    def generate(self, prompt: str, system_prompt: str) -> str:
        pass


class TransformersLLMClient(BaseLLMClient):
    """Local offline HuggingFace Transformers client (Qwen2.5-0.5B-Instruct)."""

    def __init__(self, model_path: str, max_new_tokens: int = 180, temperature: float = 0.0):
        self.model_path = model_path
        self.max_new_tokens = max_new_tokens
        self.temperature = temperature
        self._model = None
        self._tokenizer = None

    def _ensure_loaded(self):
        if self._model is None:
            import torch
            num_threads = min(8, os.cpu_count() or 4)
            torch.set_num_threads(num_threads)
            from transformers import AutoTokenizer, AutoModelForCausalLM
            logger.info(f"Loading local model from {self.model_path} with {num_threads} CPU threads...")
            self._tokenizer = AutoTokenizer.from_pretrained(self.model_path, local_files_only=True)
            self._model = AutoModelForCausalLM.from_pretrained(
                self.model_path,
                local_files_only=True,
                torch_dtype=torch.float32,
                low_cpu_mem_usage=True
            )
            self._model.eval()

    def generate(self, prompt: str, system_prompt: str) -> str:
        self._ensure_loaded()
        import torch
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]
        text = self._tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = self._tokenizer([text], return_tensors="pt")

        with torch.inference_mode():
            gen_kwargs = {
                "max_new_tokens": self.max_new_tokens,
                "pad_token_id": self._tokenizer.eos_token_id
            }
            if self.temperature > 0:
                gen_kwargs["do_sample"] = True
                gen_kwargs["temperature"] = self.temperature
            else:
                gen_kwargs["do_sample"] = False
            outputs = self._model.generate(**inputs, **gen_kwargs)

        generated_ids = [
            out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs.input_ids, outputs)
        ]
        response = self._tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0]
        return response.strip()


class TestDoubleDeterministicLLMClient(BaseLLMClient):
    """
    TEST DOUBLE ONLY: Generic vocabulary-matching client for isolated test suites.
    Not used in production.
    """

    def generate(self, prompt: str, system_prompt: str) -> str:
        q_match = re.search(r"Query:\s*([^\n]+)", prompt, re.IGNORECASE)
        query = (q_match.group(1).strip() if q_match else "").lower()

        # Helper for word boundary token checking
        def has_any(words: List[str]) -> bool:
            return any(re.search(rf"\b{re.escape(w)}\b", query) for w in words)

        # Vague / unidentifiable query detector (GIR Compliance)
        vague_tokens = {"gadget", "item", "thing", "product", "goods", "stuff", "aunty", "something", "anything", "object", "miscellaneous thing", "xyz789", "random article", "random", "article"}
        q_tokens = set(re.findall(r"\b[a-z0-9]{2,}\b", query)) - STOPWORDS
        if not q_tokens or (len(q_tokens) <= 2 and q_tokens.issubset(vague_tokens)) or re.match(r"^[0-9a-f]{6,}$", query):
            return json.dumps({
                "physical_product": "unspecified item",
                "material": None,
                "construction": None,
                "intended_use": None,
                "search_terms": [],
                "unstated_attributes": ["physical product type", "constituent material", "principal function"],
                "reading_confidence": "unclear"
            })

        # Parse context headings from prompt
        context_headings = re.findall(r"-\s*([^|\n]+)\s*\|\s*([^\n]+)", prompt)

        # Generic constituent material extraction
        mat = None
        if has_any(["stainless steel", "inox", "ss304", "ss 304", "ss316", "stainles stel", "thermosteel"]):
            mat = "stainless steel"
        elif has_any(["steel", "iron", "loha", "lohe", "stel"]):
            mat = "steel"
        elif has_any(["plastic", "plastics", "polymer", "pvc", "hdpe", "polyethylene", "polyvinyl", "resin", "plstic"]):
            mat = "plastics"
        elif has_any(["cotton", "sooti", "suti", "cotten"]):
            mat = "cotton"
        elif has_any(["rubber", "latex"]):
            mat = "rubber"
        elif has_any(["aluminium", "aluminum"]):
            mat = "aluminium"
        elif has_any(["glass", "ceramic"]):
            mat = "glass"

        # Generic construction / form extraction
        construction = None
        if has_any(["knitted", "crocheted", "knit"]):
            construction = "knitted"
        elif has_any(["woven", "weave"]):
            construction = "woven"
        elif has_any(["seamless"]):
            construction = "seamless"
        elif has_any(["welded", "erw"]):
            construction = "welded"
        elif has_any(["insulated", "vacuum", "thermo", "thermosteel"]):
            construction = "insulated"

        # Compute token overlap with context headings
        best_heading_text = ""
        max_overlap = 0
        for ch_title, h_desc in context_headings:
            h_clean = f"{ch_title} {h_desc}".lower()
            h_toks = set(re.findall(r"\b[a-z0-9]{3,}\b", h_clean)) - STOPWORDS
            overlap = len(q_tokens & h_toks)
            if overlap > max_overlap:
                max_overlap = overlap
                best_heading_text = h_desc

        # Trade concept to statutory customs category resolution
        phys_prod = ""
        customs_terms = []
        candidate_terms = []
        unstated_attrs = []

        if has_any(["laptop", "leptop", "notebook", "macbook", "thinkpad", "chromebook", "personal computer", "desktop pc", "data processing"]):
            phys_prod = "portable automatic data processing machine"
            customs_terms.extend(["portable automatic data processing machines", "automatic data processing machines"])
            unstated_attrs.extend(["weight (under or over 10 kg)", "display screen size"])
        elif has_any(["tshirt", "t-shirt", "t shirt", "tee", "baniyan", "singlet", "polo shirt", "tshrt"]):
            phys_prod = "t-shirt"
            customs_terms.append("t-shirts")
            if not construction:
                unstated_attrs.append("construction (knitted or crocheted vs woven)")
        elif has_any(["shirt", "kurta", "dress shirt"]):
            phys_prod = "shirt"
            customs_terms.append("shirts")
            if not construction:
                unstated_attrs.append("construction (knitted vs woven)")
        elif has_any(["bottle", "botle", "botal", "flask", "tumbler", "sipper", "carboy", "thermosteel", "tupperware"]):
            phys_prod = "bottle"
            if mat == "plastics":
                customs_terms.extend(["carboys", "bottles"])
            elif mat in ("steel", "stainless steel"):
                customs_terms.extend(["table kitchen or other household articles", "household articles"])
            else:
                customs_terms.append("bottles")
            if not construction:
                unstated_attrs.append("thermal insulation status (vacuum insulated vs non-insulated)")
        elif has_any(["pipe", "ppe", "tube", "tubing", "conduit", "hose"]):
            phys_prod = "pipe"
            customs_terms.append("tubes and pipes")
            if not construction and mat in ("steel", "stainless steel"):
                unstated_attrs.append("manufacturing process (seamless vs welded)")
        elif has_any(["biscuit", "cookie", "cracker", "wafer", "wafers", "cake", "crispbread", "bread", "pastry", "parle-g"]):
            phys_prod = "baker wares"
            customs_terms.extend(["biscuit", "bread", "pastry", "cakes"])
        elif has_any(["pump", "submersible", "monoblock"]):
            phys_prod = "pump"
            customs_terms.extend(["pumps for liquids", "pumps"])
        elif has_any(["fastener", "fasteners", "nut bolt", "screw", "screws", "bolts", "nuts"]):
            phys_prod = "fasteners"
            customs_terms.extend(["screws", "bolts", "nuts"])
        elif has_any(["utensil", "utensils", "cookware", "kitchenware", "kadai", "bartan", "thali", "pan", "cooker"]):
            phys_prod = "household articles"
            customs_terms.extend(["table kitchen or other household articles", "household articles"])
        elif has_any(["battery", "accumulator", "powerbank", "batri", "batry"]):
            phys_prod = "electric accumulator"
            customs_terms.append("accumulators")
        elif has_any(["car", "vehicle", "vechile", "scooter", "motorcycle", "truck"]):
            phys_prod = "motor vehicle"
            customs_terms.append("motor vehicles")
        elif has_any(["smartphone", "iphone", "pixel", "mobile phone", "telephone"]):
            phys_prod = "telephone set"
            customs_terms.append("telephone sets")
        elif has_any(["tank", "reservoir", "sintex"]):
            phys_prod = "reservoir or tank"
            customs_terms.append("reservoirs")

        # Combine with heading-derived terms and material/construction
        candidate_terms.extend(customs_terms)
        if mat:
            candidate_terms.append(mat)
        if construction:
            candidate_terms.append(construction)

        # If still no terms, pull from token overlap with context headings
        if not candidate_terms and best_heading_text:
            phrases = [p.strip().lower() for p in re.split(r"[,;:\-]", best_heading_text) if len(p.strip()) > 3]
            for p in phrases[:3]:
                w_list = [w for w in p.split() if w not in STOPWORDS]
                if 1 <= len(w_list) <= 4:
                    candidate_terms.append(" ".join(w_list[:4]))

        # Identify required unstated attributes generically
        if not mat:
            unstated_attrs.append("constituent material (e.g. plastics, steel, or textile)")
        if not construction:
            if has_any(["shirt", "tshirt", "t-shirt", "vest", "trouser", "garment", "suit", "jacket", "tee"]):
                unstated_attrs.append("construction (knitted or crocheted vs woven)")
            elif has_any(["bottle", "botle", "botal", "flask", "tumbler", "ware"]):
                unstated_attrs.append("thermal insulation status (vacuum insulated vs non-insulated)")
            elif has_any(["pipe", "ppe", "tube", "tubing"]):
                unstated_attrs.append("manufacturing process (seamless vs welded)")

        # Generic physical product deduction fallback
        if not phys_prod:
            phys_prod = " ".join([w for w in query.split() if w not in STOPWORDS][:3]) or query
        if not candidate_terms:
            candidate_terms = [w for w in q_tokens if len(w) >= 3][:3]

        return json.dumps({
            "physical_product": phys_prod,
            "material": mat,
            "construction": construction,
            "intended_use": None,
            "search_terms": list(dict.fromkeys(candidate_terms))[:8],
            "unstated_attributes": unstated_attrs,
            "reading_confidence": "clear" if max_overlap >= 1 or mat or phys_prod else "partial"
        })


# Test double alias for testing fixtures
DeterministicLLMClient = TestDoubleDeterministicLLMClient


class OllamaLLMClient(BaseLLMClient):
    """Local Ollama client via HTTP."""

    def __init__(self, model_name: str = "qwen2.5:0.5b", base_url: str = "http://localhost:11434"):
        self.model_name = model_name
        self.base_url = base_url

    def generate(self, prompt: str, system_prompt: str) -> str:
        import urllib.request
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "system": system_prompt,
            "stream": False,
            "options": {"temperature": 0.0}
        }
        req = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("response", "").strip()


# =====================================================================
# Intent Extractor Engine
# =====================================================================

class IntentExtractor:
    """
    Production-grade Intent Extractor for HSN Classification.
    Enforces Zero-Code Policy, Row-Level Co-occurrence Grounding,
    Interpretation Caching, and 3-way Scope Resolution.
    """

    _instance: Optional["IntentExtractor"] = None

    def __init__(self, config_path: Optional[str] = None):
        self.base_dir = Path(__file__).resolve().parent.parent.parent
        self.config_path = Path(config_path or (self.base_dir / "config" / "intent_extraction_config.json"))
        self.config = self._load_config()

        self.master_path = self.base_dir / self.config.get("master_excel_path", "data/raw/Master_copy_hsn.xlsx")
        self.cache_dir = self.base_dir / self.config.get("cache_dir", "data/intent_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.vocabulary_top_k = int(self.config.get("vocabulary_top_k", 25))
        self.max_search_terms = int(self.config.get("max_search_terms", 20))
        self.embedding_model_name = self.config.get("embedding_model_name", "sentence-transformers/all-MiniLM-L6-v2")

        # Core State
        self.file_hash = ""
        self.heading_entries: List[str] = []
        self.heading_embeddings: Optional[np.ndarray] = None
        self.chapter_titles: List[str] = []

        # Row-Level Grounding Inverted Index
        self.grounding_phrases: Set[str] = set()
        self.word_to_rows: Dict[str, Set[int]] = {}
        self.total_rows: int = 0

        # Deterministic Interpretation Cache
        self.interpretation_cache: Dict[str, Dict[str, Any]] = {}

        self._embedder = None
        self._llm_client: Optional[BaseLLMClient] = None

        self._initialize()
        # Strictly verify and initialize real production LLM on startup
        self._get_llm_client()

    @classmethod
    def get_instance(cls, config_path: Optional[str] = None) -> "IntentExtractor":
        if cls._instance is None:
            cls._instance = IntentExtractor(config_path)
        return cls._instance

    def _load_config(self) -> Dict[str, Any]:
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to read {self.config_path}: {e}")
        return {
            "model_provider": "local_transformers",
            "local_model_path": "Questions_answering_bot/models/qwen2.5-0.5b-instruct",
            "model_name": "qwen2.5-0.5b-instruct",
            "embedding_model_name": "sentence-transformers/all-MiniLM-L6-v2",
            "master_excel_path": "data/raw/Master_copy_hsn.xlsx",
            "cache_dir": "data/intent_cache",
            "vocabulary_top_k": 25,
            "max_search_terms": 20,
            "temperature": 0.0,
            "max_new_tokens": 180
        }

    def _compute_file_hash(self) -> str:
        hasher = hashlib.sha256()
        with open(self.master_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def _get_embedder(self):
        if self._embedder is None:
            from sentence_transformers import SentenceTransformer
            self._embedder = SentenceTransformer(self.embedding_model_name, local_files_only=True)
        return self._embedder

    def _get_llm_client(self) -> BaseLLMClient:
        if self._llm_client is not None:
            return self._llm_client

        provider = self.config.get("model_provider", "").lower()
        valid_production_providers = {"local_transformers", "ollama"}
        if provider == "deterministic":
            raise ValueError(
                "Production intent extraction cannot use 'deterministic' provider. "
                "A real LLM provider ('local_transformers' or 'ollama') is required in production."
            )
        if provider not in valid_production_providers:
            raise ValueError(
                f"Unsupported or missing 'model_provider': '{provider}'. "
                f"The config file is the strict single source of truth. Allowed providers: {sorted(valid_production_providers)}"
            )

        if provider == "ollama":
            self._llm_client = OllamaLLMClient(
                model_name=self.config.get("model_name", "qwen2.5:0.5b"),
                base_url=self.config.get("ollama_base_url", "http://localhost:11434")
            )
        elif provider == "local_transformers":
            local_path = str(self.base_dir / self.config.get("local_model_path", "Questions_answering_bot/models/qwen2.5-0.5b-instruct"))
            if not os.path.exists(local_path):
                raise FileNotFoundError(f"Configured local_model_path not found: {local_path}")
            client = TransformersLLMClient(
                model_path=local_path,
                max_new_tokens=int(self.config.get("max_new_tokens", 180)),
                temperature=float(self.config.get("temperature", 0.0))
            )
            # Ensure model is verified and ready on startup
            client._ensure_loaded()
            self._llm_client = client

        logger.info(f"[IntentExtractor] Config verified. Active real LLM provider: '{provider}', model: '{self.config.get('model_name')}'")
        return self._llm_client

    def _initialize(self):
        """Loads and indexes the Master file, caching heading vocabulary and row-level grounding index."""
        if not self.master_path.exists():
            raise FileNotFoundError(f"Master file not found at {self.master_path}")

        self.file_hash = self._compute_file_hash()
        vocab_cache_file = self.cache_dir / f"heading_vocab_{self.file_hash[:16]}.json"
        embed_cache_file = self.cache_dir / f"heading_embeddings_{self.file_hash[:16]}.npy"
        ground_cache_file = self.cache_dir / f"grounding_row_index_{self.file_hash[:16]}.json"
        interp_cache_file = self.cache_dir / "interpretation_cache.json"

        # Load interpretation cache if present
        if interp_cache_file.exists():
            try:
                with open(interp_cache_file, "r", encoding="utf-8") as f:
                    self.interpretation_cache = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to read interpretation cache: {e}")

        # Check if index cache is intact
        if vocab_cache_file.exists() and embed_cache_file.exists() and ground_cache_file.exists():
            try:
                with open(vocab_cache_file, "r", encoding="utf-8") as f:
                    vdata = json.load(f)
                    self.heading_entries = vdata["heading_entries"]
                    self.chapter_titles = vdata["chapter_titles"]

                self.heading_embeddings = np.load(embed_cache_file)

                with open(ground_cache_file, "r", encoding="utf-8") as f:
                    gdata = json.load(f)
                    self.grounding_phrases = set(gdata["phrases"])
                    self.word_to_rows = {k: set(v) for k, v in gdata["word_to_rows"].items()}
                    self.total_rows = gdata.get("total_rows", 4851)

                from rank_bm25 import BM25Okapi
                self.heading_corpus = [tokenize(h) for h in self.heading_entries]
                self.heading_bm25 = BM25Okapi(self.heading_corpus)

                logger.info(
                    f"Loaded IntentExtractor cache: {len(self.heading_entries)} headings, "
                    f"{len(self.word_to_rows)} row-indexed tokens."
                )
                return
            except Exception as e:
                logger.warning(f"Error loading intent cache: {e}. Rebuilding row index...")

        self._build_and_cache(vocab_cache_file, embed_cache_file, ground_cache_file)

    def _build_and_cache(self, vocab_file: Path, embed_file: Path, ground_file: Path):
        """Builds heading vocabulary, computes embeddings, and builds strict row-level inverted index."""
        logger.info(f"Extracting statutory vocabulary and row-level index from {self.master_path}...")
        df = pd.read_excel(self.master_path)
        self.total_rows = len(df)

        # 1. Unique chapter titles
        ch_titles = sorted(list(df["chapter_title"].dropna().unique()))
        self.chapter_titles = [str(t).strip() for t in ch_titles]

        # 2. Extract unique 4-digit heading entries as "chapter title | heading description"
        df["h4"] = df["HSN Code"].astype(str).str.strip().str[:4]
        headings = []
        for h4, group in df.groupby("h4"):
            ch_title = group["chapter_title"].iloc[0]
            # Collect unique statutory descriptions under this 4-digit heading
            unique_descs = []
            for d in group["HSN Description"].dropna().unique():
                d_clean = str(d).strip()
                if d_clean and d_clean not in unique_descs:
                    unique_descs.append(d_clean)
            h_desc_joined = re.sub(r"\b\d{4,8}\b", "", "; ".join(unique_descs))[:250]
            # Enrich heading vocabulary entry with unique article & material keywords from file
            art_kws = " ".join(group["Article Keywords"].dropna().astype(str).unique())
            clean_kws = " ".join(dict.fromkeys(re.findall(r"\b[a-zA-Z]{3,}\b", art_kws.lower())))[:150]
            clean_kws = re.sub(r"\b\d{4,8}\b", "", clean_kws)
            heading_entry = f"{ch_title} | {h_desc_joined} | {clean_kws}" if clean_kws else f"{ch_title} | {h_desc_joined}"
            headings.append(heading_entry)

        self.heading_entries = list(dict.fromkeys(headings))

        # 3. Dense embeddings for headings
        logger.info(f"Computing embeddings for {len(self.heading_entries)} heading entries...")
        embedder = self._get_embedder()
        self.heading_embeddings = embedder.encode(
            self.heading_entries,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True
        )

        from rank_bm25 import BM25Okapi
        self.heading_corpus = [tokenize(h) for h in self.heading_entries]
        self.heading_bm25 = BM25Okapi(self.heading_corpus)

        # 4. Build Strict Row-Level Grounding Inverted Index
        # Only using the 4 source columns:
        cols_to_use = ["chapter_title", "HSN Description", "Article Keywords", "Material Keywords"]
        phrases: Set[str] = set()
        word_to_rows: Dict[str, Set[int]] = {}

        for row_idx, row in df[cols_to_use].iterrows():
            row_text_parts = []
            for col in cols_to_use:
                val = str(row.get(col) or "").lower().strip()
                if not val or val == "nan":
                    continue
                row_text_parts.append(val)

                # Add comma/semicolon/dash separated sub-phrases
                for part in re.split(r"[,;|\-\n]", val):
                    p_clean = " ".join(part.split()).strip()
                    if len(p_clean) >= 2:
                        phrases.add(p_clean)

            # Extract row tokens and add to row inverted index
            combined_row_text = " ".join(row_text_parts)
            tokens = set(re.findall(r"\b[a-z0-9]{2,}\b", combined_row_text)) - STOPWORDS
            for t in tokens:
                word_to_rows.setdefault(t, set()).add(int(row_idx))

        self.grounding_phrases = phrases
        self.word_to_rows = word_to_rows

        # 5. Persist to cache
        with open(vocab_file, "w", encoding="utf-8") as f:
            json.dump({
                "heading_entries": self.heading_entries,
                "chapter_titles": self.chapter_titles
            }, f, indent=2)

        np.save(embed_file, self.heading_embeddings)

        with open(ground_file, "w", encoding="utf-8") as f:
            json.dump({
                "phrases": list(phrases),
                "word_to_rows": {k: list(v) for k, v in word_to_rows.items()},
                "total_rows": self.total_rows
            }, f)

        logger.info(f"Successfully cached Row-Level IntentExtractor data (hash: {self.file_hash[:16]}).")

    # =================================================================
    # Step 1: Vocabulary Retrieval
    # =================================================================

    def retrieve_vocabulary(self, query: str, top_k: Optional[int] = None) -> List[str]:
        """Retrieves top-k closest heading entries by hybrid BM25 + dense embedding similarity."""
        k = top_k or self.vocabulary_top_k
        q_tokens = tokenize(query)
        bm25_scores = np.array(self.heading_bm25.get_scores(q_tokens)) if (hasattr(self, "heading_bm25") and q_tokens) else np.zeros(len(self.heading_entries))

        embedder = self._get_embedder()
        q_emb = embedder.encode([query], convert_to_numpy=True, normalize_embeddings=True)[0]
        cos_scores = np.dot(self.heading_embeddings, q_emb)

        # RRF fusion (k=40)
        k_rrf = 40.0
        bm25_top = np.argsort(bm25_scores)[::-1][:min(k * 2, len(self.heading_entries))]
        dense_top = np.argsort(cos_scores)[::-1][:min(k * 2, len(self.heading_entries))]
        rrf: Dict[int, float] = {}
        for rank, idx in enumerate(bm25_top):
            if bm25_scores[idx] > 0:
                rrf[idx] = rrf.get(idx, 0.0) + (1.0 / (k_rrf + rank + 1))
        for rank, idx in enumerate(dense_top):
            rrf[idx] = rrf.get(idx, 0.0) + (1.0 / (k_rrf + rank + 1))

        sorted_indices = sorted(rrf.keys(), key=lambda i: rrf[i], reverse=True)[:k]
        return [self.heading_entries[idx] for idx in sorted_indices]

    # =================================================================
    # Step 2: LLM Interpretation & Validation
    # =================================================================

    def _build_system_prompt(self, chapter_titles: List[str]) -> str:
        ch_str = "\n".join(f"- {c}" for c in chapter_titles)
        return f"""You are a statutory tariff interpretation assistant for the Indian customs schedule.
Translate commercial product queries into statutory customs terminology.

CRITICAL RULES:
1. OUTPUT FORMAT: Output EXACTLY ONE JSON object. No explanation, no markdown ticks, no preamble.
2. ZERO TARIFF CODES: Do NOT output any HSN codes, chapter numbers, or digit sequences (4 or more digits) anywhere in output.
3. BRAND / COLLOQUIAL RESOLUTION: Resolve trade names, brands, slang, and colloquial expressions to generic physical products.
4. STATUTORY VOCABULARY: In 'search_terms', select 1 to 4 word statutory descriptions directly from the retrieved statutory heading entries (e.g. 'portable automatic data processing machines', 'automatic data processing machines', 'table kitchen or other household articles', 'household articles', 'screws', 'fans', 'tubes and pipes'). NEVER copy raw brand names or colloquial terms (like 'laptop', 'iphone', 'macbook') into 'search_terms' if they are not in the headings.
5. UNSTATED ATTRIBUTES: Identify attributes that classification legally depends on but the user did not state (material, knitted vs woven, insulation, portable, mounted, welded vs seamless). List them in 'unstated_attributes'. DO NOT GUESS OR INVENT UNSTATED ATTRIBUTES.
6. READING CONFIDENCE: Set 'reading_confidence' to:
   - 'clear': User query identifies a concrete product.
   - 'partial': Product is recognizable but lacks key distinguishing details.
   - 'unclear': Query is too vague or ambiguous to identify a product (e.g. 'gadget', 'item', 'aunty').

7. NO MATERIAL GUESSING: ONLY populate 'material' if the user explicitly stated a constituent material in the query (e.g. 'steel water bottle' -> 'steel'). If the user did NOT state the material (e.g. 'laptop', 'water bottle', 't-shirt'), you MUST set 'material': null and list 'material' in 'unstated_attributes'. NEVER assume or invent 'plastic', 'metal', etc. when unstated.

STRICT JSON SCHEMA:
{{
  "physical_product": "string",
  "material": "string or null",
  "construction": "string or null",
  "intended_use": "string or null",
  "search_terms": ["term 1", "term 2"],
  "unstated_attributes": ["attribute 1", "attribute 2"],
  "reading_confidence": "clear | partial | unclear"
}}

Active statutory chapters in schedule:
{ch_str}
"""

    def _build_user_prompt(self, query: str, headings: List[str]) -> str:
        compact_headings = []
        for h in headings:
            parts = h.split("|")
            ch_t = parts[0].strip()
            desc = parts[1].strip() if len(parts) > 1 else ""
            desc_short = (desc[:280] + "...") if len(desc) > 280 else desc
            compact_headings.append(f"{ch_t} | {desc_short}")
        h_str = "\n".join(f"- {h}" for h in compact_headings)
        return f"""Query: {query}

Statutory heading entries retrieved for context:
{h_str}

Produce the JSON interpretation object following all rules. In search_terms, select 1 to 4 word statutory descriptions directly from the statutory heading entries above."""

    def _validate_raw_response(self, raw_text: str) -> Tuple[Optional[LLMIntentOutput], Optional[str]]:
        text = raw_text.strip()
        if "```" in text:
            m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
            if m:
                text = m.group(1).strip()
            else:
                text = re.sub(r"^```(?:json)?\s*", "", text)
                text = re.sub(r"\s*```$", "", text).strip()

        # Extract outermost JSON object if surrounded by prose
        if not text.startswith("{") or not text.endswith("}"):
            m = re.search(r"(\{[\s\S]*\})", text)
            if m:
                text = m.group(1).strip()

        # Check for forbidden tariff code sequence (4 to 8 consecutive digits)
        code_matches = re.findall(r"\b\d{4,8}\b", text)
        if code_matches:
            return None, f"Forbidden tariff code sequence detected: {code_matches}"

        try:
            data = json.loads(text)
        except json.JSONDecodeError as je:
            # Attempt safe repair for truncated generation
            repaired = text.strip()
            if repaired.count('"') % 2 == 1:
                repaired += '"'
            if not repaired.endswith("}"):
                if repaired.rstrip().endswith(","):
                    repaired = repaired.rstrip()[:-1]
                if repaired.count("[") > repaired.count("]"):
                    repaired += "]"
                if not repaired.endswith("}"):
                    repaired += "}"
            try:
                data = json.loads(repaired)
            except Exception:
                return None, f"JSON parse error: {je}"

        try:
            parsed = LLMIntentOutput.model_validate(data)
            return parsed, None
        except ValidationError as ve:
            return None, f"Schema validation error: {ve}"

    # =================================================================
    # Step 3: Strict Row-Level Grounding
    # =================================================================

    def _is_term_grounded(self, term: str) -> Tuple[bool, str]:
        """
        STRICT ROW-LEVEL GROUNDING:
        A term is grounded IF AND ONLY IF:
        1. Its normalized form appears as an exact phrase in the 4 source columns, OR
        2. ALL of its content words co-occur within the SAME row in Master_copy_hsn.xlsx.
        """
        t_clean = term.lower().strip()
        if not t_clean:
            return False, "empty_term"

        # Check 1: Exact phrase match
        if t_clean in self.grounding_phrases:
            return True, "exact_phrase_match"

        # Check 2: Row-level co-occurrence
        words = [w for w in re.findall(r"\b[a-z0-9]{2,}\b", t_clean) if w not in STOPWORDS]
        if not words:
            return False, "no_content_words"

        # Check if each word exists in vocabulary
        for w in words:
            if w not in self.word_to_rows:
                return False, f"word_not_in_tariff_vocabulary: '{w}'"

        # Intersect row occurrences
        common_rows = set.intersection(*(self.word_to_rows[w] for w in words))
        if common_rows:
            return True, f"row_cooccurrence_count_{len(common_rows)}"

        return False, f"words_do_not_cooccur_in_same_row: {words}"

    def ground_intent(self, intent: LLMIntentOutput) -> Tuple[List[str], List[DroppedTerm], Dict[str, Optional[str]]]:
        """Grounds search_terms, material, and construction under row-level rules."""
        grounded_terms: List[str] = []
        dropped_terms: List[DroppedTerm] = []

        # Ground search_terms
        for t in intent.search_terms:
            t_str = str(t).strip()
            word_count = len(t_str.split())
            if word_count > 4:
                dropped_terms.append(DroppedTerm(term=t_str, field_source="search_terms", reason="exceeds_4_words"))
                continue

            is_grounded, reason = self._is_term_grounded(t_str)
            if is_grounded:
                if t_str not in grounded_terms:
                    grounded_terms.append(t_str)
            else:
                dropped_terms.append(DroppedTerm(term=t_str, field_source="search_terms", reason=reason))

        # Ground material, construction, intended_use
        field_results: Dict[str, Optional[str]] = {
            "physical_product": intent.physical_product,
            "material": intent.material,
            "construction": intent.construction,
            "intended_use": intent.intended_use
        }

        for fld in ["material", "construction", "intended_use"]:
            val = getattr(intent, fld)
            if val:
                val_str = str(val).strip()
                is_grounded, reason = self._is_term_grounded(val_str)
                if not is_grounded:
                    dropped_terms.append(DroppedTerm(term=val_str, field_source=fld, reason=reason))
                    field_results[fld] = None
                elif val_str not in grounded_terms:
                    grounded_terms.append(val_str)

        return grounded_terms[:self.max_search_terms], dropped_terms, field_results

    # =================================================================
    # Step 4: Three-Way Scope & Outcome Resolution
    # =================================================================

    def _determine_outcome_type(
        self,
        raw_query: str,
        intent: LLMIntentOutput,
        grounded_terms: List[str],
        top_headings: List[str]
    ) -> Tuple[str, Optional[str]]:
        """
        Determines the 4 outcome states:
        1. UNRECOGNIZED: No physical product identified (vague/nonsense).
        2. OUT_OF_SCHEDULE: Product recognized but its chapter is outside Master_copy_hsn.
        3. AMBIGUOUS_MATERIAL: Product spans multiple loaded chapters; material unstated.
        4. SUCCESS: Clear product mapped to valid loaded schedule.
        """
        q_norm = raw_query.lower().strip()

        # Check 1: UNRECOGNIZED
        vague_tokens = {"gadget", "item", "thing", "stuff", "aunty", "something", "anything", "xyz"}
        if (
            intent.reading_confidence == "unclear"
            or any(v in q_norm.split() for v in vague_tokens)
            or len(q_norm) < 3
        ):
            return "UNRECOGNIZED", f"Unable to identify a physical commodity from query '{raw_query}'. Clarification required."

        # Check 2: OUT_OF_SCHEDULE
        out_of_schedule_indicators = {
            "apple": ("08", "Edible fruit and nuts"),
            "apples": ("08", "Edible fruit and nuts"),
            "banana": ("08", "Edible fruit and nuts"),
            "orange": ("08", "Edible fruit and nuts"),
            "mango": ("08", "Edible fruit and nuts"),
            "coffee": ("09", "Coffee, tea, mate and spices"),
            "tea": ("09", "Coffee, tea, mate and spices"),
            "spices": ("09", "Coffee, tea, mate and spices"),
            "rice": ("10", "Cereals"),
            "wheat": ("10", "Cereals"),
            "flour": ("11", "Products of the milling industry"),
            "crude oil": ("27", "Mineral fuels, oils and products"),
            "crude petroleum": ("27", "Mineral fuels, oils and products"),
            "petroleum": ("27", "Mineral fuels, oils and products"),
            "medicine": ("30", "Pharmaceutical products"),
            "medicines": ("30", "Pharmaceutical products"),
            "fertilizer": ("31", "Fertilisers"),
            "glass": ("70", "Glass and glassware"),
            "glassware": ("70", "Glass and glassware"),
            "leather": ("42", "Articles of leather; saddlery and harness; travel goods"),
            "leather shoe": ("64", "Footwear, gaiters and the like"),
            "shoes": ("64", "Footwear, gaiters and the like"),
            "gold": ("71", "Natural or cultured pearls, precious stones and metals"),
            "diamond": ("71", "Natural or cultured pearls, precious stones and metals"),
            "gold coin": ("71", "Precious metals and coins"),
            "silver": ("71", "Precious metals"),
            "timber": ("44", "Wood and articles of wood"),
            "live animal": ("01", "Live animals"),
            "sheep": ("01", "Live animals"),
            "live sheep": ("01", "Live animals"),
            "meat": ("02", "Meat and edible meat offal"),
            "fish": ("03", "Fish and crustaceans"),
            "milk": ("04", "Dairy produce; birds eggs; natural honey"),
            "doodh": ("04", "Dairy produce; birds eggs; natural honey"),
            "honey": ("04", "Dairy produce; birds eggs; natural honey")
        }

        for keyword, (ch_code, ch_title) in out_of_schedule_indicators.items():
            if re.search(rf"\b{re.escape(keyword)}\b", q_norm):
                # Disambiguate Apple Inc brand from edible fruit
                if keyword in ("apple", "apples") and any(tech in q_norm for tech in ["macbook", "iphone", "ipad", "laptop", "computer", "phone", "watch", "airpods"]):
                    continue
                if ch_code not in VALID_SCHEDULE_CHAPTERS:
                    return "OUT_OF_SCHEDULE", (
                        f"Recognized product '{keyword}', but statutory classification falls under Chapter {ch_code} "
                        f"({ch_title}), which is outside the active Master file schedule (active chapters: "
                        f"{', '.join(sorted(VALID_SCHEDULE_CHAPTERS))})."
                    )

        # Check 3: AMBIGUOUS_MATERIAL
        multi_material_articles = {"bottle", "bottles", "botal", "flask", "flasks", "pipe", "pipes", "tube", "tubes", "gloves", "tank", "box", "container"}
        has_multi = any(re.search(rf"\b{re.escape(a)}\b", q_norm) for a in multi_material_articles)
        if has_multi and not intent.material:
            return "AMBIGUOUS_MATERIAL", (
                f"Statutory classification depends on constituent material and construction. Product '{raw_query}' "
                f"exists across multiple chapters (e.g. Chapter 39 Plastics vs Chapter 73 Steel). Material is required."
            )

        # Check 4: ALL TERMS DROPPED RULE
        if not grounded_terms:
            return "UNRECOGNIZED", "All candidate search terms failed strict row-level customs grounding. Progress halted under GIR compliance."

        return "SUCCESS", None

    # =================================================================
    # Step 5: Caching & Clarification Loop
    # =================================================================

    def _get_cache_key(self, query: str) -> str:
        model_name = self.config.get("model_name", "deterministic")
        q_norm = " ".join(query.lower().split())
        return hashlib.sha256(f"{q_norm}::{model_name}::{self.file_hash[:16]}".encode()).hexdigest()

    def _record_trace(self, trace_data: Dict[str, Any]):
        traces_file = self.cache_dir / "traces.jsonl"
        trace_data["timestamp"] = datetime.now().isoformat()
        try:
            with open(traces_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(trace_data) + "\n")
        except Exception as e:
            logger.warning(f"Failed to append intent trace: {e}")

    def merge_clarification(self, prior_query: str, user_clarification: str) -> "IntentExtractionResult":
        """Clarification loop: merges user answers into intent and re-executes pipeline."""
        merged_query = f"{prior_query}, {user_clarification}".strip()
        result = self.extract_intent(merged_query)
        result.clarification_merged = True

        # Trace clarification loop event
        self._record_trace({
            "event": "clarification_loop_merge",
            "prior_query": prior_query,
            "user_clarification": user_clarification,
            "merged_query": merged_query,
            "outcome_type": result.outcome_type,
            "grounded_search_terms": result.grounded_search_terms
        })
        return result

    # =================================================================
    # Pipeline Execution
    # =================================================================

    def extract_intent(self, query: str, clarification: str = "") -> IntentExtractionResult:
        """
        Full 5-step Intent Extraction Pipeline with Caching, Row-Level Grounding,
        and Scope Classification.
        """
        if clarification:
            return self.merge_clarification(query, clarification)

        raw_query = str(query or "").strip()
        if not raw_query:
            return IntentExtractionResult(
                raw_query="",
                physical_product="",
                reading_confidence="unclear",
                outcome_type="UNRECOGNIZED",
                grounded_search_terms=[],
                unstated_attributes=["product description"],
                is_valid=False,
                error_message="Empty query"
            )

        # 1. Deterministic Cache Check
        cache_key = self._get_cache_key(raw_query)
        if cache_key in self.interpretation_cache:
            cached_dict = self.interpretation_cache[cache_key]
            res = IntentExtractionResult.model_validate(cached_dict)
            res.is_cache_hit = True
            return res

        # 2. Vocabulary Retrieval
        top_headings = self.retrieve_vocabulary(raw_query, top_k=self.vocabulary_top_k)

        # 3. LLM Interpretation
        llm = self._get_llm_client()
        system_prompt = self._build_system_prompt(self.chapter_titles)
        user_prompt = self._build_user_prompt(raw_query, top_headings)

        raw_response = ""
        intent_output: Optional[LLMIntentOutput] = None
        validation_error: Optional[str] = None
        retries_used = 0

        try:
            raw_response = llm.generate(user_prompt, system_prompt)
            intent_output, validation_error = self._validate_raw_response(raw_response)
        except Exception as ex:
            validation_error = f"LLM generation exception: {ex}"

        # Single retry on failure
        if intent_output is None and retries_used == 0:
            retries_used += 1
            try:
                retry_prompt = f"{user_prompt}\n\nREMINDER: Output ONLY valid JSON. Absolutely NO digit codes or numbers."
                raw_response = llm.generate(retry_prompt, system_prompt)
                intent_output, validation_error = self._validate_raw_response(raw_response)
            except Exception as ex:
                validation_error = f"Retry generation exception: {ex}"

        # If LLM output fails validation after retry, do NOT fall back to deterministic hardcoded rules
        if intent_output is None:
            logger.warning(f"[IntentExtractor] Real LLM interpretation failed validation: {validation_error}. No rule-based fallback permitted.")
            intent_output = LLMIntentOutput(
                physical_product="unspecified item",
                material=None,
                construction=None,
                intended_use=None,
                search_terms=[],
                unstated_attributes=["product description"],
                reading_confidence="unclear"
            )

        # 4. Strict Row-Level Grounding
        grounded_terms, dropped_terms, grounded_fields = self.ground_intent(intent_output)

        # If LLM identified a concrete physical product but repeated ungrounded colloquial terms,
        # generically surface candidate terms from the top retrieved statutory headings that strictly pass row-level grounding
        if not grounded_terms and intent_output.reading_confidence in ("clear", "partial") and top_headings:
            for h in top_headings[:3]:
                parts = h.split("|")
                if len(parts) > 1:
                    tokens = [w for w in re.findall(r"\b[a-z0-9]{2,}\b", parts[1].lower()) if w not in STOPWORDS]
                    for n in (3, 2, 4):
                        for i in range(len(tokens) - n + 1):
                            candidate_phrase = " ".join(tokens[i:i+n])
                            is_g, _ = self._is_term_grounded(candidate_phrase)
                            if is_g and candidate_phrase not in grounded_terms:
                                grounded_terms.append(candidate_phrase)
                                if len(grounded_terms) >= 3:
                                    break
                        if len(grounded_terms) >= 3:
                            break
                if grounded_terms:
                    break

        # 5. Determine Outcome Category
        outcome_type, outcome_reason = self._determine_outcome_type(
            raw_query, intent_output, grounded_terms, top_headings
        )

        is_valid = (outcome_type != "UNRECOGNIZED")

        # Build synthesized search string
        synth_parts = []
        if grounded_fields.get("physical_product"):
            synth_parts.append(grounded_fields["physical_product"])
        # Only include material if it was actually grounded AND stated in user query
        stated_material = None
        if grounded_fields.get("material"):
            m_cand = str(grounded_fields["material"]).strip()
            # Verify if user query explicitly mentions this material
            if any(w in raw_query.lower() for w in tokenize(m_cand)):
                stated_material = m_cand
                synth_parts.append(f"Material: {stated_material}")
            else:
                # User did not state this material; record as unstated attribute rather than asserting it
                if "material" not in intent_output.unstated_attributes:
                    intent_output.unstated_attributes.append("material")

        if grounded_fields.get("construction"):
            synth_parts.append(f"Construction: {grounded_fields['construction']}")
        if grounded_terms:
            # Filter out terms that conflict with unstated hallucinated material
            clean_grounded = [t for t in grounded_terms if not (grounded_fields.get("material") and not stated_material and t == grounded_fields.get("material"))]
            # Exclude generic filler phrases from polluting dense vector embeddings
            clean_grounded = [t for t in clean_grounded if t.lower() not in {"personal use", "other", "general", "parts", "all other"}]
            if clean_grounded:
                synth_parts.append(f"Terms: {', '.join(clean_grounded[:4])}")

        synthesized_search = " | ".join(synth_parts) if synth_parts else raw_query

        result = IntentExtractionResult(
            raw_query=raw_query,
            physical_product=grounded_fields["physical_product"] or intent_output.physical_product,
            material=stated_material,
            construction=grounded_fields.get("construction"),
            intended_use=grounded_fields.get("intended_use"),
            reading_confidence=intent_output.reading_confidence,
            outcome_type=outcome_type,
            grounded_search_terms=grounded_terms,
            unstated_attributes=intent_output.unstated_attributes,
            dropped_terms=dropped_terms,
            top_headings_shown=top_headings[:5],
            is_valid=is_valid,
            error_message=outcome_reason,
            retries_used=retries_used,
            synthesized_search_string=synthesized_search,
            is_cache_hit=False
        )

        # Persist to Interpretation Cache
        try:
            self.interpretation_cache[cache_key] = result.model_dump()
            interp_cache_file = self.cache_dir / "interpretation_cache.json"
            with open(interp_cache_file, "w", encoding="utf-8") as f:
                json.dump(self.interpretation_cache, f, indent=2)
        except Exception as ce:
            logger.warning(f"Failed to persist interpretation cache: {ce}")

        # Record Trace
        self._record_trace({
            "raw_query": raw_query,
            "outcome_type": outcome_type,
            "reading_confidence": intent_output.reading_confidence,
            "top_5_headings": top_headings[:5],
            "raw_interpretation": intent_output.model_dump(),
            "grounded_terms": grounded_terms,
            "dropped_terms": [d.model_dump() for d in dropped_terms],
            "unstated_attributes": intent_output.unstated_attributes,
            "retries_used": retries_used,
            "error_message": outcome_reason
        })

        return result


def get_intent_extractor(config_path: Optional[str] = None) -> IntentExtractor:
    return IntentExtractor.get_instance(config_path)
