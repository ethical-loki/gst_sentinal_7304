"""
tests/test_banner_logic.py
==========================
Unit & Integration tests verifying statutory banner logic:
1. MULTI_CHAPTER_AMBIGUITY triggers IF AND ONLY IF distinct active candidate chapters > 1.
2. For single-chapter variants like 'laptop', banner_type MUST BE 'SAME_CHAPTER_VARIANT',
   status MUST BE 'NEEDS_SELECTION', and resolved_chapter MUST BE '84'.
3. Banner invariant: Never show MULTI_CHAPTER_AMBIGUITY when candidate options belong to only one chapter.
"""

import pytest
from src.search.ambiguity_controller import SmartAmbiguityController
from src.search.hybrid_retrieval import SearchCandidate


@pytest.fixture(scope="module")
def controller():
    return SmartAmbiguityController()


def make_cand(hsn: str, chap: str, title: str, desc: str, score: float, rank: int, mat: str = "", art: str = "") -> SearchCandidate:
    return SearchCandidate(
        hsn_code=hsn,
        chapter_code=chap,
        chapter_title=title,
        heading_4digit=hsn[:4] if len(hsn) >= 4 else "0000",
        heading_4digit_desc="Heading Desc",
        subheading_6digit=hsn[:6] if len(hsn) >= 6 else "000000",
        subheading_6digit_desc="Subheading Desc",
        tariff_item_desc=desc,
        statutory_description=desc,
        consumer_synonyms=desc,
        article_keywords=art or desc,
        material_keywords=mat,
        final_score=score,
        is_8digit_leaf=True,
        rank=rank
    )


def test_laptop_shows_same_chapter_variant(controller):
    """
    Test using 'laptop': candidates are within Chapter 84 (e.g., 8471 30 10 vs 8471 30 90).
    Must evaluate to SAME_CHAPTER_VARIANT, status NEEDS_SELECTION, resolved_chapter '84'.
    """
    candidates = [
        make_cand(
            hsn="8471 30 10",
            chap="84",
            title="Nuclear reactors, boilers, machinery and mechanical appliances; parts thereof",
            desc="Personal computer / Laptop",
            score=0.78,
            rank=1,
            mat="",
            art="laptop personal computer"
        ),
        make_cand(
            hsn="8471 30 90",
            chap="84",
            title="Nuclear reactors, boilers, machinery and mechanical appliances; parts thereof",
            desc="Other portable automatic data processing machine",
            score=0.76,
            rank=2,
            mat="",
            art="portable automatic data processing"
        ),
        # Distant runner up in Ch 85 (score margin > 0.15) should not contaminate banner
        make_cand(
            hsn="8517 13 00",
            chap="85",
            title="Electrical machinery and equipment and parts thereof",
            desc="Smartphones",
            score=0.50,
            rank=3,
            mat="",
            art="smartphones"
        )
    ]

    res = controller.evaluate_ambiguity(query="laptop", candidates=candidates)

    assert res.banner_type == "SAME_CHAPTER_VARIANT", f"Expected SAME_CHAPTER_VARIANT, got {res.banner_type}"
    assert res.status == "NEEDS_SELECTION", f"Expected NEEDS_SELECTION, got {res.status}"
    assert res.resolved_chapter == "84", f"Expected resolved_chapter '84', got {res.resolved_chapter}"
    assert res.is_ambiguous is False, "Same-chapter variants must have is_ambiguous=False"
    assert res.distinct_chapters_count == 1, "Only competing options within top margin should count"


def test_multi_chapter_ambiguity_only_when_multiple_chapters(controller):
    """
    When competing candidates genuinely span multiple chapters (e.g. Ch 39 Plastic vs Ch 73 Steel),
    banner_type must be MULTI_CHAPTER_AMBIGUITY and status AMBIGUOUS_MATERIAL.
    """
    candidates = [
        make_cand(
            hsn="3923 30 90",
            chap="39",
            title="Plastics and articles thereof",
            desc="Bottles, flasks and similar articles of plastics",
            score=0.74,
            rank=1,
            mat="plastic",
            art="bottles"
        ),
        make_cand(
            hsn="7323 93 90",
            chap="73",
            title="Articles of iron or steel",
            desc="Table, kitchen or other household articles of stainless steel",
            score=0.72,
            rank=2,
            mat="stainless steel",
            art="household articles"
        )
    ]

    res = controller.evaluate_ambiguity(query="water bottle", candidates=candidates)

    assert res.banner_type == "MULTI_CHAPTER_AMBIGUITY", f"Expected MULTI_CHAPTER_AMBIGUITY, got {res.banner_type}"
    assert res.status == "AMBIGUOUS_MATERIAL", f"Expected AMBIGUOUS_MATERIAL, got {res.status}"
    assert res.is_ambiguous is True
    assert res.distinct_chapters_count > 1


def test_banner_invariant_across_candidate_sets(controller):
    """
    Invariant: MULTI_CHAPTER_AMBIGUITY is STRICTLY FORBIDDEN when distinct active options == 1.
    """
    single_ch_candidates = [
        make_cand(
            hsn="6109 10 00",
            chap="61",
            title="Articles of apparel and clothing accessories, knitted or crocheted",
            desc="T-shirts, singlets and other vests, of cotton, knitted",
            score=0.75,
            rank=1,
            mat="cotton",
            art="t-shirts"
        ),
        make_cand(
            hsn="6109 90 10",
            chap="61",
            title="Articles of apparel and clothing accessories, knitted or crocheted",
            desc="Of other textile materials: Of synthetic fibres",
            score=0.73,
            rank=2,
            mat="synthetic fibres",
            art="t-shirts"
        )
    ]

    res = controller.evaluate_ambiguity(query="cotton t-shirt", candidates=single_ch_candidates)
    assert res.banner_type != "MULTI_CHAPTER_AMBIGUITY"
    assert res.banner_type in ("SAME_CHAPTER_VARIANT", "AUTO_LOCKED")
