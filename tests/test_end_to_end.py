"""
tests/test_end_to_end.py — End-to-End Pipeline Integration Test.

Validates the complete lifecycle:
Inbound Multilingual Description -> Product Normalizer -> Ambiguity Analyzer ->
Clarification Question -> Description Enricher -> Statutory Verification ->
Digital Product Passport Creation, Versioning, and Export.
"""

import pytest
import tempfile
from pathlib import Path

from src.nlp.multilingual_processor import get_multilingual_processor
from src.nlp.product_normalizer import get_product_normalizer
from src.ml.qwen_ambiguity_analyzer import get_ambiguity_analyzer
from src.ml.qwen_question_generator import get_question_generator
from src.ml.qwen_description_enricher import get_description_enricher
from src.passport.passport_manager import PassportManager
from src.database.passport_schema import PassportStore


class TestEndToEndPipeline:
    @pytest.fixture
    def pipeline(self, tmp_path):
        db_path = tmp_path / "e2e_passports.db"
        store = PassportStore(db_path=db_path)
        mgr = PassportManager(store=store)
        return {
            "multilingual": get_multilingual_processor(),
            "normalizer": get_product_normalizer(),
            "ambiguity": get_ambiguity_analyzer(),
            "question_gen": get_question_generator(),
            "enricher": get_description_enricher(),
            "passport_mgr": mgr,
        }

    def test_full_multilingual_to_passport_lifecycle(self, pipeline):
        multi_proc = pipeline["multilingual"]
        normalizer = pipeline["normalizer"]
        ambiguity_analyzer = pipeline["ambiguity"]
        question_gen = pipeline["question_gen"]
        enricher = pipeline["enricher"]
        passport_mgr = pipeline["passport_mgr"]

        # Step 1: Raw Indian Trade Inbound (Bilingual Devanagari Hindi)
        raw_trade_query = "पाइप फिटिंग 1/2 inch"

        # Step 2: Multilingual Processing
        multi_result = multi_proc.process(raw_trade_query)
        assert multi_result.is_multilingual
        assert "pipe" in multi_result.translated_text.lower()
        translated_text = multi_result.translated_text

        # Step 3: Product Normalization
        norm_result = normalizer.normalize(translated_text)
        assert "1/2 inch" in norm_result.attributes.dimensions or "pipe" in norm_result.clean_trade_name

        # Step 4: Ambiguity Detection (Pipe fitting without material is ambiguous across Ch 73, 39, 74)
        ambiguity_report = ambiguity_analyzer.analyze(norm_result.canonical_description)
        assert ambiguity_report.is_ambiguous
        assert ambiguity_report.ambiguity_type == "MISSING_MATERIAL"

        # Step 5: Clarification Question Generation
        questions = question_gen.generate_questions(ambiguity_report)
        assert len(questions) > 0
        q = questions[0]
        assert "material" in q.question_text.lower()

        # Step 6: User answers clarification question (e.g. vendor selects Stainless Steel)
        user_answers = {"material": "Stainless Steel"}
        enriched_result = enricher.enrich(
            original_query=norm_result.canonical_description,
            answers=user_answers,
            heading_hint="7307",
            hsn_hint="73072200",
        )
        assert "stainless steel" in enriched_result.enriched_query.lower()
        assert "7307" in enriched_result.target_heading_hint

        # Step 7: Creation of Statutory Digital Product Passport
        passport = passport_mgr.create_passport(
            product_name=enriched_result.enriched_query,
            manufacturer_gstin="27AAPFU0939F1ZV",
            hsn_code="73072200",
            official_description="Threaded elbows, bends and sleeves of stainless steel",
            gst_rate=18.0,
            unit_price=350.0,
            sku_code="SS-ELB-05",
            creation_reason="Audited and confirmed via Qwen clarification pipeline",
        )

        assert passport.passport_id.startswith("DPP-IN-")
        assert passport.version == 1

        # Step 8: Multi-format Export & Supply Chain Verification
        einvoice_payload = passport_mgr.export_passport(passport.passport_id, "einvoice")
        assert einvoice_payload["HsnCd"] == "73072200"
        assert einvoice_payload["GstRt"] == 18.0

        qr_payload = passport_mgr.export_passport(passport.passport_id, "qr")
        assert qr_payload["dpp_id"] == passport.passport_id
        assert "sig" in qr_payload

        # Step 9: Revalidation & Version Tracking
        versions = passport_mgr.get_version_history(passport.passport_id)
        assert len(versions) == 1

        # Update passport when rate revision occurs
        updated_p = passport_mgr.update_passport(
            passport_id=passport.passport_id,
            updates={"unit_price": 380.0},
            change_reason="Price escalation index update",
            author="FINANCE_DEPT",
        )
        assert updated_p.version == 2

        versions_after = passport_mgr.get_version_history(passport.passport_id)
        assert len(versions_after) == 2
        assert versions_after[1]["version"] == 2