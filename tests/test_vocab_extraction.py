"""
tests/test_vocab_extraction.py
==============================
Tests Task 2, Task 3, Task 4, Task 5:
- Preserves word spelling & plurals (flanges, pipes, bolts)
- No noise words or hardcoded product rules in normalize.py
- Extract article, form, and material as separate fields using data/article_form_vocabulary.json
"""

import pytest
from src.chapter_predictor.normalize import (
    normalize_product_name,
    extract_query_facts,
    load_noise_words,
    load_vocabulary
)


def test_plural_spelling_preservation():
    """Plurals like flanges, pipes, bolts must retain original spelling."""
    text = "flanges pipes bolts nuts washers screws"
    cleaned, tokens = normalize_product_name(text)
    assert cleaned == "flanges pipes bolts nuts washers screws"
    assert tokens == ["flanges", "pipes", "bolts", "nuts", "washers", "screws"]


def test_noise_words_file_loaded():
    """Noise words must be read from external data file without code hardcoding."""
    data = load_noise_words()
    assert isinstance(data, dict)
    assert len(data.get("brand_names", [])) > 0
    assert len(data.get("marketing_adjectives", [])) > 0


def test_article_form_vocabulary_loaded():
    """Vocabulary dataset must be loaded from data/article_form_vocabulary.json."""
    vocab = load_vocabulary()
    assert len(vocab) >= 50
    types = {item["type"] for item in vocab}
    assert "article" in types
    assert "form" in types
    assert "material" in types


def test_extract_facts_ceramic_mug():
    """Branded product extracts mug as article, ceramic as material."""
    facts = extract_query_facts("Harry Potter Gryffindor Crest Heat-Changing Ceramic Mug")
    assert facts["article"] == "mug" or facts["article"] == "mugs"
    assert facts["material"] == "Ceramic"
    assert facts["family"] == "containers"


def test_extract_facts_seamless_pipe():
    """Seamless SS Pipe extracts line pipe/pipes as article, seamless as form, stainless steel as material."""
    facts = extract_query_facts("Seamless Stainless Steel Line Pipe for Oil & Gas")
    assert facts["article"] in ("line pipe", "pipes", "pipe")
    assert facts["form"] == "seamless"
    assert facts["material"] == "Stainless steel"


def test_extract_facts_knitted_tshirt():
    """Knitted Cotton T-shirt extracts t-shirt as article, knitted as form, cotton as material."""
    facts = extract_query_facts("Men Knitted 100% Cotton T-Shirt")
    assert facts["article"] in ("t-shirt", "t-shirts", "shirt")
    assert facts["form"] == "knitted"
    assert facts["material"] == "Cotton"


def test_extract_facts_generic_noise_returns_none_article():
    """Vague query with no identifiable commodity noun returns article=None."""
    facts = extract_query_facts("xyz unbranded assorted lot 500 pcs miscellaneous")
    assert facts["article"] is None


def test_task1_direct_predictor_and_endpoint_parity():
    """Task 1 Test: direct predictor call and endpoint call return identical chapter and status."""
    from fastapi.testclient import TestClient
    from backend.main import app
    from src.chapter_predictor.predictor import ChapterPredictor

    client = TestClient(app)
    prod = "Seamless Stainless Steel Line Pipe for Oil & Gas"
    direct = ChapterPredictor.get_instance().predict(prod)

    resp = client.post("/api/v1/hsn-rag/step1-context-aggregator", json={"product": prod})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["catalogue_version"] == "v1.0.0-closed98"
    assert data["index_version"] == "bge-m3-lineage-v1"

    pred_data = data["chapter_prediction"]
    assert pred_data["chapter"] == direct.chapter
    assert pred_data["status"] == direct.status
    assert pred_data["total_active_chapters"] == 98


def test_task3_no_hardcoded_eval_products_in_code():
    """Task 3 Guardrail: Fails build if any product name from eval fixtures appears as a hardcoded rule in code."""
    import csv
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    eval_csv = root / "tests" / "fixtures" / "chapter_eval.csv"
    assert eval_csv.exists()

    eval_products = []
    with open(eval_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            p = row["product_name"].strip().lower()
            if len(p) > 5 and len(p.split()) > 1:
                eval_products.append(p)

    # Scan python files in src/chapter_predictor/
    code_dir = root / "src" / "chapter_predictor"
    for py_file in code_dir.glob("*.py"):
        content = py_file.read_text(encoding="utf-8").lower()
        for prod in eval_products:
            # Check for hardcoded equality/exact match rules like == "whole roasted coffee beans" or in ["whole roasted..."]
            assert f'"{prod}"' not in content, f"Hardcoded product '{prod}' found in {py_file.name}!"
            assert f"'{prod}'" not in content, f"Hardcoded product '{prod}' found in {py_file.name}!"

