"""
config.py — Configuration parameters for GST Sentinel Question Answering bot.
"""

from pathlib import Path
import os

# Base Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DOCS_DIR = BASE_DIR / "docs"
MODELS_DIR = BASE_DIR / "models"

# Domain-specific Context Files
DOMAIN_CONTEXT_PATHS = {
    "e_invoice": DATA_DIR / "e_invoice_context.txt",
    "eway_bill": DATA_DIR / "eway_bill_context.txt",
    "ims": DATA_DIR / "ims_context.txt",
}

# Default monolithic context fallback
def resolve_context_path() -> Path:
    candidates = [
        DATA_DIR / "e_invoice_context.txt",
        DATA_DIR / "context.txt",
        BASE_DIR / "context.txt",
    ]
    for p in candidates:
        if p.exists():
            return p
    return DATA_DIR / "context.txt"

CONTEXT_PATH = resolve_context_path()
CONTENT_PATH = CONTEXT_PATH
INDEX_DB_PATH = DATA_DIR / "index.db"

# Model configuration — Local Qwen2.5 Instruct LLM
LOCAL_QWEN_MODEL = MODELS_DIR / "qwen2.5-0.5b-instruct"
LOCAL_SMALL_MODEL = LOCAL_QWEN_MODEL if LOCAL_QWEN_MODEL.exists() else (MODELS_DIR / "flan-t5-small")
DEFAULT_MODEL_NAME = os.getenv("QA_MODEL", "Qwen/Qwen2.5-0.5B-Instruct")
MODEL_PATH = LOCAL_QWEN_MODEL if LOCAL_QWEN_MODEL.exists() else Path(DEFAULT_MODEL_NAME)

# Retrieval / Chunking Parameters
CHUNK_SIZE = 250
CHUNK_OVERLAP = 60
TOP_K = 3
SCORE_THRESHOLD = 0.04

# Generation parameters for Qwen / Causal LM
MAX_NEW_TOKENS = 250
MIN_LENGTH = 3
NUM_BEAMS = 1
DO_SAMPLE = False
TEMPERATURE = 0.1
REPETITION_PENALTY = 1.1

# Strict Fallback response
FALLBACK_RESPONSE = "Information not found in the selected domain context."
