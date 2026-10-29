import logging
from pathlib import Path
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger("download_model")

BASE_DIR = Path(__file__).resolve().parent.parent
MODEL_DIR = BASE_DIR / "models" / "flan-t5-small"
MODEL_NAME = "google/flan-t5-small"

def download():
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    logger.info(f"Downloading generative model '{MODEL_NAME}' to {MODEL_DIR}...")
    
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    tokenizer.save_pretrained(MODEL_DIR)

    model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_NAME)
    model.save_pretrained(MODEL_DIR)

    logger.info("Generative model downloaded and stored locally. Ready for offline inference.")

if __name__ == "__main__":
    download()