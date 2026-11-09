"""
scripts/build_eval_dataset.py
==============================
Builds stratified evaluation datasets for Step 1 Chapter Prediction:
- Plain queries
- Branded queries (with noise brands)
- Noisy queries (with marketing hype and quantities)
Splits into:
  - data/eval/dev_set.csv (70% for development and tuning)
  - data/eval/holdout_set.csv (30% strictly held out)
"""

import csv
import json
import random
from pathlib import Path
from typing import List, Dict

ROOT_DIR = Path(__file__).resolve().parent.parent
EVAL_DIR = ROOT_DIR / "data" / "eval"
SEED_CSV = ROOT_DIR / "tests" / "fixtures" / "chapter_eval.csv"
NOISE_FILE = ROOT_DIR / "data" / "noise_words.json"
VOCAB_FILE = ROOT_DIR / "data" / "article_form_vocabulary.json"

random.seed(42)


def generate_evaluation_dataset():
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    
    # 1. Load Noise Words
    with open(NOISE_FILE, "r", encoding="utf-8") as f:
        noise_data = json.load(f)
    brands = noise_data.get("brand_names", ["Marvel", "Nike", "Disney", "Sony", "Philips"])
    adjectives = noise_data.get("marketing_adjectives", ["Premium", "Deluxe", "Classic", "Genuine", "Export Quality"])
    pack_fillers = noise_data.get("trade_pack_fillers", ["Combo Pack", "Retail Pack", "Value Pack"])

    # 2. Load Seed Fixtures
    records: List[Dict[str, str]] = []
    if SEED_CSV.exists():
        with open(SEED_CSV, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                p_name = row["product_name"].strip()
                ch = row["expected_chapter"].strip().zfill(2)
                cat = row.get("category", "General Goods").strip()
                if p_name and ch:
                    # Plain version
                    records.append({
                        "product_name": p_name,
                        "expected_chapter": ch,
                        "variant": "plain",
                        "category": cat
                    })
                    # Branded version
                    brand = random.choice(brands).title()
                    records.append({
                        "product_name": f"{brand} {p_name}",
                        "expected_chapter": ch,
                        "variant": "branded",
                        "category": cat
                    })
                    # Noisy version
                    adj = random.choice(adjectives).title()
                    filler = random.choice(pack_fillers).title()
                    qty = random.choice(["500g", "1 kg", "2 pcs", "10 units", "pack of 2"])
                    records.append({
                        "product_name": f"{brand} {adj} {p_name} in {filler} ({qty})",
                        "expected_chapter": ch,
                        "variant": "noisy",
                        "category": cat
                    })

    # Shuffle deterministically
    random.shuffle(records)
    total = len(records)
    dev_split = int(0.70 * total)

    dev_records = records[:dev_split]
    holdout_records = records[dev_split:]

    dev_file = EVAL_DIR / "dev_set.csv"
    holdout_file = EVAL_DIR / "holdout_set.csv"

    fieldnames = ["product_name", "expected_chapter", "variant", "category"]
    
    with open(dev_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(dev_records)

    with open(holdout_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(holdout_records)

    print(f"[SUCCESS] Built stratified eval dataset in {EVAL_DIR}:")
    print(f"  - Total Generated Records: {total}")
    print(f"  - Dev Set: {len(dev_records)} items -> {dev_file}")
    print(f"  - Holdout Set: {len(holdout_records)} items -> {holdout_file}")


if __name__ == "__main__":
    generate_evaluation_dataset()

