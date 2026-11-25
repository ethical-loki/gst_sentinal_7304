"""
tests/test_no_legacy_chapters.py
================================
Dynamic 97-Chapter Regression Guard.
Verifies that the obsolete hardcoded 9-chapter schedule restriction
(`VALID_SCHEDULE_CHAPTERS` and `OUT_OF_SCHEDULE` rejections for valid chapters)
has been completely removed and that Stage 1 covers the full statutory master dynamically.
"""

import pytest
import src.nlp.intent_extractor as intent_mod
from src.nlp.intent_extractor import IntentExtractor, DeterministicLLMClient, LLMIntentOutput


@pytest.fixture(scope="module")
def extractor():
    ext = IntentExtractor()
    ext._llm_client = DeterministicLLMClient()
    ext.interpretation_cache = {}
    return ext


def test_no_hardcoded_nine_chapter_constant(extractor):
    """Confirms VALID_SCHEDULE_CHAPTERS was removed and active schedule spans all 97 chapters dynamically."""
    assert not hasattr(intent_mod, "VALID_SCHEDULE_CHAPTERS")
    assert len(extractor.active_chapters) >= 97


@pytest.mark.parametrize(
    "query",
    [
        "fresh apples",
        "leather shoes",
        "gold coin",
        "crude petroleum",
        "coffee beans",
        "pharmaceutical medicine",
    ],
)
def test_cross_chapter_goods_no_longer_rejected_as_out_of_schedule(extractor, query):
    """Previously excluded 9-chapter items must be recognized dynamically under the full 97-chapter master."""
    res = extractor.extract_intent(query, use_cache=False)
    assert res.outcome_type in {"SUCCESS", "AMBIGUOUS_MATERIAL"}
    assert len(res.grounded_search_terms) > 0


def test_unrecognized_vague_query_still_abstains_without_chapter(extractor):
    """Vague non-commodity input must strictly return UNRECOGNIZED without fabricated terms or chapters."""
    res = extractor.extract_intent("aunty", use_cache=False)
    assert res.outcome_type == "UNRECOGNIZED"
    assert res.is_valid is False
    assert res.grounded_search_terms == []


def test_dynamic_out_of_schedule_when_active_subset_excludes_commodity():
    """Verifies dynamic OUT_OF_SCHEDULE detection via StatutoryMasterIndex when active chapters are a subset."""
    ext = IntentExtractor.__new__(IntentExtractor)
    ext.master_path = "custom_subset"
    ext.active_chapters = {"39", "73"}
    ext.word_to_rows = {"bottle": {0}, "plastic": {0}, "steel": {1}}
    ext.chapter_titles = ["Plastics", "Articles of iron or steel"]

    intent = LLMIntentOutput(
        physical_product="coffee beans",
        finished_article="coffee beans",
        search_terms=["coffee beans"],
        reading_confidence="clear",
    )
    outcome, reason = ext._determine_outcome_type(
        "coffee beans",
        intent,
        grounded_terms=[],
        top_headings=[],
        finished_article="coffee beans",
    )
    assert outcome == "OUT_OF_SCHEDULE"
    assert reason is not None
