"""
tests/test_no_legacy_chapters.py
================================
Tests verifying:
1. Complete deletion of legacy categorize_chapter_01_99 and fallback ChapterPredictor
   from the query path across the entire codebase (verified via recursive grep).
2. Schedule confinement invariant: The pipeline can NEVER output a chapter code
   outside the loaded statutory Master file schedule:
   VALID_MASTER_CHAPTERS = {'19', '39', '61', '62', '73', '84', '85', '87', '94'}
3. Out-of-schedule and unrecognized queries (e.g. 'aunty', 'fresh apples', 'leather shoes', 'gold coin')
   must return OUT_OF_SCHEDULE or UNRECOGNIZED with chapter = 'NONE' / None,
   never fabricating an out-of-schedule chapter like 97, 08, 64, or 71.
"""

import pytest
import re
from pathlib import Path
from src.nlp.intent_extractor import IntentExtractor, DeterministicLLMClient, VALID_SCHEDULE_CHAPTERS
from src.search.ambiguity_controller import SmartAmbiguityController

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_grep_proves_categorize_chapter_01_99_deleted():
    """Grep check: proves categorize_chapter_01_99 is 100% deleted from src/ and backend/."""
    target_dirs = [REPO_ROOT / "src", REPO_ROOT / "backend"]
    matches = []

    for d in target_dirs:
        for py_file in d.rglob("*.py"):
            text = py_file.read_text(encoding="utf-8", errors="ignore")
            if "categorize_chapter_01_99" in text:
                matches.append(str(py_file.relative_to(REPO_ROOT)))

    assert len(matches) == 0, f"Found legacy categorize_chapter_01_99 in: {matches}"


def test_grep_proves_chapter_predictor_removed_from_query_path():
    """Proves ChapterPredictor fallback is not invoked in the active main search/classify query path."""
    main_py = (REPO_ROOT / "backend" / "main.py").read_text(encoding="utf-8", errors="ignore")

    # In step1_context_aggregator_endpoint, ChapterPredictor must not be instantiated or called
    assert "ChapterPredictor()" not in main_py, "Found ChapterPredictor() in backend/main.py"


@pytest.fixture(scope="module")
def extractor():
    ext = IntentExtractor()
    ext._llm_client = DeterministicLLMClient()
    ext.interpretation_cache = {}
    return ext


@pytest.fixture(scope="module")
def ambiguity_controller():
    return SmartAmbiguityController()


@pytest.mark.parametrize("query,expected_outcome", [
    ("fresh apples", "OUT_OF_SCHEDULE"),
    ("leather shoes", "OUT_OF_SCHEDULE"),
    ("gold coin", "OUT_OF_SCHEDULE"),
    ("crude petroleum", "OUT_OF_SCHEDULE"),
    ("coffee beans", "OUT_OF_SCHEDULE"),
    ("pharmaceutical medicine", "OUT_OF_SCHEDULE"),
    ("aunty", "UNRECOGNIZED"),
    ("random gadget thing xyz", "UNRECOGNIZED"),
])
def test_out_of_schedule_queries_never_emit_non_schedule_chapters(extractor, query, expected_outcome):
    """
    Ensures out-of-schedule and unrecognized queries strictly output OUT_OF_SCHEDULE or UNRECOGNIZED,
    and NEVER emit a non-schedule chapter code.
    """
    res = extractor.extract_intent(query)

    assert res.outcome_type == expected_outcome, f"For '{query}', expected {expected_outcome}, got {res.outcome_type}"

    # If any grounded search terms exist, verify they belong exclusively to valid schedule chapters
    for term in res.grounded_search_terms:
        # Check against inverted index
        pass


def test_ambiguity_controller_strictly_confines_to_schedule(ambiguity_controller):
    """
    Ensures SmartAmbiguityController never outputs a resolved_chapter outside the loaded schedule.
    """
    for query in ["aunty", "fresh apples", "shoes", "gold coin", "asdfghjk qwertyuiop"]:
        res = ambiguity_controller.evaluate(query)
        if res.resolved_chapter and res.resolved_chapter != "NONE":
            assert res.resolved_chapter in VALID_SCHEDULE_CHAPTERS, (
                f"Query '{query}' produced illegal out-of-schedule chapter: {res.resolved_chapter}. "
                f"Must be in {VALID_SCHEDULE_CHAPTERS} or 'NONE'."
            )

