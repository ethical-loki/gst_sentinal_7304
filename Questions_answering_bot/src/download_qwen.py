import sys
import logging
from pathlib import Path
from transformers import AutoTokenizer, AutoModelForCausalLM

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger("download_qwen")

BASE_DIR = Path(__file__).resolve().parent.parent
MODEL_DIR = BASE_DIR / "models" / "qwen2.5-0.5b-instruct"
MODEL_NAME = "Qwen/Qwen2.5-0.5B-Instruct"

def download():
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    logger.info(f"Downloading generative model '{MODEL_NAME}' to {MODEL_DIR}...")
    
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    tokenizer.save_pretrained(MODEL_DIR)
    logger.info("Tokenizer saved.")

    model = AutoModelForCausalLM.from_pretrained(MODEL_NAME)
    model.save_pretrained(MODEL_DIR)
    logger.info("Qwen2.5-0.5B-Instruct model downloaded and stored locally. Ready for offline inference.")

if __name__ == "__main__":
    download()

