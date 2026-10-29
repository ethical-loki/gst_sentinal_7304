from pathlib import Path

# Base Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DOCS_DIR = BASE_DIR / "docs"
MODELS_DIR = BASE_DIR / "models"

# File Paths
CONTENT_PATH = DATA_DIR / "content.txt"
INDEX_DB_PATH = DATA_DIR / "index.db"
MODEL_PATH = MODELS_DIR / "longformer-squad2"

# Retrieval / Indexing Parameters (word counts)
# Small chunks keep each passage focused on one topic and keep Longformer
# inference fast on CPU (~400 tokens per chunk instead of ~4096).
CHUNK_SIZE = 250
CHUNK_OVERLAP = 50
TOP_K = 3

# Inference Threshold
# If the top reader probability is below this value, reply "not found"
SCORE_THRESHOLD = 0.05