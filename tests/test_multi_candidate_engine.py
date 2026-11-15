"""
Phase 7: Unit, Stress (>100 candidates), and Real-Dataset Integration Tests
for `src/ml/multi_candidate_engine.py`.
"""

from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

from src.ml.multi_candidate_engine import (
    AdaptiveCandidateDiscoverer,
    MultiCandidateEngine,
    group_candidates,
)
from src.ml.product_tariff_reranker import RerankedTariffCandidate
from src.ml.relevance_classifier import ClassifiedTariffCandidate, RelationLabel
from src.search.statutory_master_index import StatutoryComparisonResult


class _MockHybrid150:
    """Controlled 150-record corpus (120 relevant + 30 unrelated) for stress testing."""

    def __init__(self, n_relevant: int = 120, n_unrelated: int = 30):
        self.records: List[Dict[str, Any]] = []
        for i in range(n_relevant):
            h4 = f"84{10 + (i // 20):02d}"
            desc = (
                "Industrial centrifugal pump"
                if i < 4
                else f"Industrial pump assembly variant {i} stainless steel"
            )
            self.records.append({
                "hsn_code": f"{h4}{1000 + i:04d}",
                "chapter_code": "84",
                "chapter_title": "Nuclear reactors, boilers, machinery",
                "statutory_description": desc,
                "material_keywords": "stainless steel" if i % 2 == 0 else "cast iron",
            })
        for j in range(n_unrelated):
            self.records.append({
                "hsn_code": f"6109{1000 + j:04d}",
                "chapter_code": "61",
                "chapter_title": "Apparel knitted",
                "statutory_description": f"Cotton knitted garment {j}",
                "material_keywords": "cotton",
            })
        self.total_records = len(self.records)

    def _expand_abbreviated_query(self, q: str):
        return q.lower(), q.lower().split()

    def retrieve_with_lineage(self, raw_query: str, branch_k: int = 30):
        k = min(branch_k, self.total_records)
        out = []
        for idx in range(k):
            r = dict(self.records[idx])
            r["source_record_id"] = f"row_{idx}"
            r["retrieval_source"] = "bm25+dense"
            r["bm25_score"] = round(1.0 - idx * 0.001, 4)
            r["vector_score"] = round(0.9 - idx * 0.001, 4)
            r["rrf_score"] = round(0.03 - idx * 0.0001, 6)
            out.append(r)
        return out


class _MockClassifier:
    calibration_bundle = None
    reranker = MagicMock()

    def classify(self, product_intent: str, tariff_rows):
        out = []
        q_low = product_intent.lower()
        for row in tariff_rows:
            desc = str(row.get("statutory_description", "")).lower()
            hsn = str(row.get("hsn_code", ""))
            ch = str(row.get("chapter_code", ""))
            if "garment" in desc:
                rel = RelationLabel.UNRELATED
                score = 0.08
                logit = -2.4
            else:
                # If user confirmed 'stainless steel', stainless steel items get higher score
                boost = 0.05 if ("stainless steel" in q_low and "stainless steel" in str(row.get("material_keywords", ""))) else 0.0
                rel = RelationLabel.SAME_PRODUCT
                score = min(0.95, 0.80 + boost)
                logit = 1.4 + boost
            cand = RerankedTariffCandidate(
                hsn_code=hsn,
                chapter_code=ch,
                description=row.get("statutory_description", ""),
                relevance_score=score,
                raw_logit=logit,
                chapter_title=row.get("chapter_title", ""),
                material_keywords=row.get("material_keywords", ""),
            )
            out.append(ClassifiedTariffCandidate(candidate=cand, relation=rel, confidence=score, relevance_confidence=score))
        return out


def _make_mock_engine(max_eval_budget: int = 200, tmp_path=None):
    stat = MagicMock()
    stat.compare_active_vs_statutory.return_value = StatutoryComparisonResult(
        query="industrial pump",
        is_out_of_schedule=False,
        best_active_score=0.85,
        best_inactive_score=0.10,
        reason="Active schedule outranks inactive.",
    )
    from src.training.feedback_collector import FeedbackCollector
    fc = FeedbackCollector(feedback_dir=tmp_path) if tmp_path else MagicMock()
    return MultiCandidateEngine(
        hybrid_engine=_MockHybrid150(120, 30),
        relevance_classifier=_MockClassifier(),
        statutory_index=stat,
        feedback_collector=fc,
        initial_branch_k=30,
        max_eval_budget=max_eval_budget,
    )


def test_stress_over_100_candidates_no_truncation_pagination_and_grouping(tmp_path):
    engine = _make_mock_engine(max_eval_budget=200, tmp_path=tmp_path)
    res_p1 = engine.classify_adaptive("industrial pump", page=1, page_size=20)

    # All 120 relevant records must be preserved (no top-3/top-20 backend truncation!)
    assert res_p1["discovery"]["qualifying_candidates"] == 120
    assert res_p1["all_candidates_count"] == 120
    assert res_p1["audit"]["candidates_discarded"] == 30  # 30 unrelated garments excluded
    assert res_p1["discovery"]["discovery_complete"] is True
    assert res_p1["prediction_mode"] == "MULTIPLE_CANDIDATES"

    # Pagination checks: page 1 has 20, page 6 has 20 and has_next_page=False
    assert len(res_p1["candidates"]) == 20
    assert res_p1["pagination"]["total_candidates"] == 120
    assert res_p1["pagination"]["total_pages"] == 6
    assert res_p1["pagination"]["has_next_page"] is True

    res_p6 = engine.classify_adaptive("industrial pump", page=6, page_size=20)
    assert len(res_p6["candidates"]) == 20
    assert res_p6["pagination"]["has_next_page"] is False

    # Duplicate statutory descriptions grouped without losing individual HSNs
    dup_groups = [g for g in res_p1["candidate_groups"] if g["group_type"] == "DUPLICATE_DESCRIPTION"]
    assert len(dup_groups) == 1
    assert dup_groups[0]["count"] == 4
    assert len(dup_groups[0]["hsn_codes"]) == 4


def test_incomplete_discovery_honestly_reported_when_budget_hit():
    engine = _make_mock_engine(max_eval_budget=50)
    res = engine.classify_adaptive("industrial pump", page=1, page_size=20)
    assert res["discovery"]["discovery_complete"] is False
    assert "resource_budget_reached" in res["discovery"]["stopping_reason"]
    assert res["confidences"]["discovery_completeness"] < 1.0


def test_progressive_clarification_preserves_original_and_updates_ranking(tmp_path):
    engine = _make_mock_engine(max_eval_budget=200, tmp_path=tmp_path)
    r1 = engine.classify_adaptive("industrial pump", page=1, page_size=10)
    assert r1["clarification"]["required"] is True
    assert len(r1["clarification"]["questions"]) >= 1

    r2 = engine.clarify_and_refine(
        original_description="industrial pump",
        previous_confirmed=r1["confirmed_attributes"],
        new_answers={"material": "stainless steel"},
        page=1,
        page_size=10,
    )
    assert r2["input_description"] == "industrial pump"
    assert r2["confirmed_attributes"] == {"material": "stainless steel"}
    assert "stainless steel" in r2["effective_query"]
    assert r2["candidates"][0]["known_attributes"]["confirmed_by_user"] == {"material": "stainless steel"}

    # Feedback integration: writes to pending only, never verified_pairs
    fid = engine.record_feedback(
        original_description="industrial pump",
        selected_hsn="84101000",
        predicted_hsn=r2["candidates"][0]["hsn_code"],
        confirmed_attributes=r2["confirmed_attributes"],
        rejected_alternatives=[r2["candidates"][1]["hsn_code"]],
    )
    assert fid
    assert (tmp_path / "pending_feedback.jsonl").exists()
    assert not (tmp_path / "verified_pairs.parquet").exists()


@pytest.mark.slow
def test_real_dataset_integration_scenarios():
    engine = MultiCandidateEngine()

    # 1. Multi-candidate food query
    r_noodles = engine.classify_adaptive("Instant noodles made from wheat flour", page=1, page_size=5)
    assert r_noodles["discovery"]["qualifying_candidates"] >= 1
    assert r_noodles["pagination"]["total_candidates"] >= len(r_noodles["candidates"])

    # 2. Missing material ambiguity / insufficient info (asks for material/details)
    r_bottle = engine.classify_adaptive("water bottle", page=1, page_size=10)
    assert r_bottle["prediction_mode"] in (
        "MULTIPLE_CANDIDATES",
        "CLARIFY_AMBIGUOUS",
        "INSUFFICIENT_INFORMATION",
    )
    assert r_bottle["clarification"]["required"] is True

    # 3. Missing construction (knitted vs woven)
    r_shirt = engine.classify_adaptive("cotton shirt", page=1, page_size=10)
    assert "construction" in r_shirt["clarification"]["separating_attributes"]

    # 4. Abbreviated description
    r_abbr = engine.classify_adaptive("AUXI. MACH. FOR USE", page=1, page_size=10)
    assert r_abbr["discovery"]["qualifying_candidates"] >= 1

    # 5. Out-of-schedule
    r_coffee = engine.classify_adaptive("roasted arabica coffee beans", page=1, page_size=10)
    assert r_coffee["prediction_mode"] == "OUT_OF_SCHEDULE"
    assert r_coffee["final_chapter"] == "09"

    # 6. Insufficient / uninformative
    r_empty = engine.classify_adaptive("OTHER", page=1, page_size=10)
    assert r_empty["prediction_mode"] == "INSUFFICIENT_INFORMATION"


def test_fastapi_adaptive_endpoints_and_ui_wiring(tmp_path, monkeypatch):
    from pathlib import Path
    from fastapi.testclient import TestClient
    import backend.main as backend_main

    mock_eng = _make_mock_engine(max_eval_budget=10, tmp_path=tmp_path)
    monkeypatch.setattr(backend_main, "_multi_candidate_engine", mock_eng)
    client = TestClient(backend_main.app)

    r1 = client.post("/api/v1/hsn-v2/classify-adaptive", json={"description": "pump", "page": 1, "page_size": 2})
    assert r1.status_code == 200
    d1 = r1.json()
    assert len(d1["candidates"]) == 2
    assert d1["pagination"]["page"] == 1
    assert d1["pagination"]["has_next_page"] is True

    r2 = client.post("/api/v1/hsn-v2/classify-adaptive", json={"description": "pump", "page": 5, "page_size": 2})
    assert r2.status_code == 200
    d2 = r2.json()
    assert len(d2["candidates"]) == 2
    assert d2["pagination"]["page"] == 5
    assert d2["pagination"]["has_next_page"] is False

    r_clar = client.post(
        "/api/v1/hsn-v2/clarify-adaptive",
        json={"description": "pump", "confirmed_attributes": {"material": "stainless steel"}, "page": 1, "page_size": 10},
    )
    assert r_clar.status_code == 200
    dc = r_clar.json()
    assert dc["confirmed_attributes"] == {"material": "stainless steel"}
    assert "stainless steel" in dc["effective_query"]

    for ui_rel in ("frontend/index.html", "static/index.html"):
        html = Path(ui_rel).read_text(encoding="utf-8")
        for token in (
            "/api/v1/hsn-v2/classify-adaptive",
            "/api/v1/hsn-v2/clarify-adaptive",
            "adaptiveDiscoveryPanel",
            "runAdaptiveDiscovery",
            "submitAdaptiveClarification",
            "candidate_groups",
            "discovery_complete",
        ):
            assert token in html, f"Missing {token} in {ui_rel}"


def test_parent_vs_leaf_never_predicts_parent_as_exact_hsn(tmp_path):
    from src.training.feedback_collector import FeedbackCollector

    class _ParentOnlyHybrid:
        total_records = 2

        def _expand_abbreviated_query(self, q: str):
            return q.lower(), q.lower().split()

        def retrieve_with_lineage(self, raw_query: str, branch_k: int = 30):
            return [
                {
                    "hsn_code": "8410",
                    "chapter_code": "84",
                    "statutory_description": "Hydraulic turbines, water wheels",
                    "source_record_id": "p1",
                    "retrieval_source": "bm25",
                    "bm25_score": 1.0,
                    "vector_score": 0.9,
                    "rrf_score": 0.03,
                },
                {
                    "hsn_code": "841010",
                    "chapter_code": "84",
                    "statutory_description": "Hydraulic turbines of power <= 1000 kW",
                    "source_record_id": "p2",
                    "retrieval_source": "bm25",
                    "bm25_score": 0.9,
                    "vector_score": 0.8,
                    "rrf_score": 0.02,
                },
            ]

    class _ParentClassifier:
        calibration_bundle = None
        reranker = MagicMock()

        def classify(self, product_intent: str, tariff_rows):
            out = []
            for r in tariff_rows:
                cand = RerankedTariffCandidate(
                    hsn_code=r["hsn_code"],
                    chapter_code=r["chapter_code"],
                    description=r["statutory_description"],
                    relevance_score=0.92,
                    raw_logit=2.5,
                    tariff_level="HEADING_4DIGIT" if len(r["hsn_code"]) == 4 else "SUBHEADING_6DIGIT",
                )
                out.append(ClassifiedTariffCandidate(candidate=cand, relation=RelationLabel.SAME_PRODUCT, confidence=0.92, relevance_confidence=0.92))
            return out

    stat = MagicMock()
    stat.compare_active_vs_statutory.return_value = StatutoryComparisonResult(
        query="hydraulic turbine",
        is_out_of_schedule=False,
        best_active_score=0.92,
        best_inactive_score=0.10,
        reason="Active",
    )
    eng = MultiCandidateEngine(
        hybrid_engine=_ParentOnlyHybrid(),
        relevance_classifier=_ParentClassifier(),
        statutory_index=stat,
        feedback_collector=FeedbackCollector(feedback_dir=tmp_path),
    )
    res = eng.classify_adaptive("hydraulic turbine")
    assert res["prediction_mode"] in ("CHAPTER_ONLY_CLARIFY", "MULTIPLE_CANDIDATES")
    assert res["final_hsn"] is None
    assert res["clarification"]["required"] is True
    assert res["hierarchy_context"]["parent_candidates"] == 2
    assert res["hierarchy_context"]["leaf_candidates"] == 0


