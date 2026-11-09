"""
scripts/record_phase0_baseline.py
=================================
Phase 0: Record baseline for the five specified test items:
1. Stainless Steel Blind Flange
2. Steel Ingot
3. Stainless Steel Sheet
4. Steel Pipe Fitting
5. Steel Bolt
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.chapter_predictor.predictor import ChapterPredictor
from src.chapter_predictor.normalize import extract_query_facts

def record_baseline():
    items = [
        "Stainless Steel Blind Flange",
        "Steel Ingot",
        "Stainless Steel Sheet",
        "Steel Pipe Fitting",
        "Steel Bolt"
    ]
    predictor = ChapterPredictor.get_instance()
    print("=" * 70)
    print("PHASE 0: BASELINE FIVE TEST ITEMS")
    print("=" * 70)
    for item in items:
        facts = extract_query_facts(item)
        res = predictor.predict(item)
        print(f"Item: {item}")
        print(f"  Head Noun / Article:   {facts.get('article')}")
        print(f"  Constituent Material:  {facts.get('material')}")
        print(f"  State / Form Stage:    {facts.get('form_stage', facts.get('form'))}")
        print(f"  Candidate Chapters:    {facts.get('vocabulary_candidate_chapters')}")
        print(f"  Predicted Chapter:     {res.chapter} - {res.chapter_title}")
        print(f"  Status:                {res.status}")
        print(f"  Top Supporting Lines:  {[e.hsn_code for e in res.evidence[:2]]}")
        print("-" * 70)

if __name__ == "__main__":
    record_baseline()

