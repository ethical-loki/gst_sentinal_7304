import sys
sys.path.insert(0, ".")
from src.chapter_predictor.normalize import extract_query_facts

items = [
    "Stainless Steel Blind Flange",
    "Steel Ingot",
    "Stainless Steel Sheet",
    "Steel Pipe Fitting",
    "Steel Bolt"
]

for item in items:
    f = extract_query_facts(item)
    print(f"Product: {item}")
    print(f"  Head Noun:          {f.get('article')}")
    print(f"  Material:           {f.get('material')}")
    print(f"  State / Form Stage: {f.get('form_stage')}")
    print(f"  Candidate Chapters: {f.get('vocabulary_candidate_chapters')}")
    print("-" * 50)
