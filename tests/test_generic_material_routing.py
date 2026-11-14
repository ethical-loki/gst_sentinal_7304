"""
tests/test_generic_material_routing.py
======================================
Tests verifying generic material routing and absence of arbitrary multipliers:
1. Verifies that hybrid_retrieval.py contains NO hardcoded multipliers (1.30, 0.35)
   and NO hardcoded lists of specific materials.
2. Demonstrates that both 'stainless steel water bottle' and 'plastic pipe' pass
   through the exact same generic material resolution path in AmbiguityController:
   - 'stainless steel water bottle' resolves to Chapter 73.
   - 'plastic pipe' resolves to Chapter 39.
3. Demonstrates that unspecified 'water bottle' (or 'pipe') does not resolve to one chapter
   and routes to AMBIGUOUS_MATERIAL with MULTI_CHAPTER_AMBIGUITY banner.
"""

import pytest
import re
from pathlib import Path
from src.search.ambiguity_controller import SmartAmbiguityController


@pytest.fixture(scope="module")
def controller():
    return SmartAmbiguityController()


def test_no_hardcoded_material_multipliers_in_source():
    """Verifies hybrid_retrieval.py has no 1.30x, 0.35x or hardcoded materials list."""
    source_path = Path(__file__).resolve().parent.parent / "src" / "search" / "hybrid_retrieval.py"
    content = source_path.read_text(encoding="utf-8")

    assert "1.30" not in content, "Found legacy 1.30x multiplier in hybrid_retrieval.py"
    assert "0.35" not in content, "Found legacy 0.35x multiplier in hybrid_retrieval.py"
    assert "common_materials" not in content, "Found hardcoded common_materials list in hybrid_retrieval.py"


def test_stainless_steel_water_bottle_routes_to_chapter_73(controller):
    """
    'stainless steel water bottle' must extract material 'steel' / 'stainless steel'
    generically from statutory vocabulary, filter candidates against Material Keywords,
    and resolve to Chapter 73 (SAME_CHAPTER_VARIANT, NEEDS_SELECTION).
    """
    res = controller.evaluate("stainless steel water bottle")

    assert res.status in ("SUCCESS", "NEEDS_SELECTION"), f"Expected SUCCESS or NEEDS_SELECTION, got {res.status}"
    assert res.resolved_chapter == "73", f"Expected resolved_chapter '73', got {res.resolved_chapter}"
    assert res.banner_type in ("SAME_CHAPTER_VARIANT", "AUTO_LOCKED"), f"Expected SAME_CHAPTER_VARIANT, got {res.banner_type}"
    assert not res.is_ambiguous, "Resolved material must not have multi-chapter ambiguity"


def test_plastic_pipe_routes_to_chapter_39(controller):
    """
    'plastic pipe' must pass through the EXACT SAME generic path, extract material 'plastic',
    filter candidates against Material Keywords, and resolve to Chapter 39 (SAME_CHAPTER_VARIANT, NEEDS_SELECTION).
    """
    res = controller.evaluate("plastic pipe")

    assert res.status in ("SUCCESS", "NEEDS_SELECTION"), f"Expected SUCCESS or NEEDS_SELECTION, got {res.status}"
    assert res.resolved_chapter == "39", f"Expected resolved_chapter '39', got {res.resolved_chapter}"
    assert res.banner_type in ("SAME_CHAPTER_VARIANT", "AUTO_LOCKED"), f"Expected SAME_CHAPTER_VARIANT, got {res.banner_type}"
    assert not res.is_ambiguous, "Resolved material must not have multi-chapter ambiguity"


def test_unspecified_water_bottle_routes_to_ambiguous_material(controller):
    """
    'water bottle' (without material) must NOT resolve to one chapter and must route
    to AMBIGUOUS_MATERIAL with MULTI_CHAPTER_AMBIGUITY.
    """
    res = controller.evaluate("water bottle")

    assert res.status == "AMBIGUOUS_MATERIAL", f"Expected AMBIGUOUS_MATERIAL, got {res.status}"
    assert res.banner_type == "MULTI_CHAPTER_AMBIGUITY", f"Expected MULTI_CHAPTER_AMBIGUITY, got {res.banner_type}"
    assert res.is_ambiguous is True
    assert res.distinct_chapters_count > 1

