"""
tests/test_passport.py — Unit Tests for Digital Product Passport Subsystem.
"""

import pytest
import tempfile
from pathlib import Path

from src.passport.passport_identity import (
    generate_passport_id,
    compute_deterministic_id,
    is_valid_passport_id,
    PassportIdentity,
)
from src.passport.passport_versioning import PassportVersionHistory
from src.passport.passport_exporter import PassportExporter
from src.passport.passport_importer import PassportImporter
from src.passport.passport_sharing import PassportShareManager
from src.passport.passport_revalidation import PassportRevalidationEngine
from src.passport.passport_manager import PassportManager, ProductPassport
from src.database.passport_schema import PassportStore


class TestPassportIdentity:
    def test_passport_id_format(self):
        pid = generate_passport_id(2026)
        assert is_valid_passport_id(pid)
        assert pid.startswith("DPP-IN-2026-")
        assert len(pid) == 24

    def test_deterministic_id(self):
        gstin = "27AAPFU0939F1ZV"
        prod = "SS 304 Hex Nipple 1/2 inch"
        sku = "SKU-HN-001"
        id1 = compute_deterministic_id(gstin, prod, sku, year=2026)
        id2 = compute_deterministic_id(gstin, prod, sku, year=2026)
        assert id1 == id2
        assert is_valid_passport_id(id1)


class TestPassportPersistenceAndVersioning:
    @pytest.fixture
    def temp_store(self, tmp_path):
        db_path = tmp_path / "test_passport.db"
        store = PassportStore(db_path=db_path)
        return store

    def test_store_and_retrieve_passport(self, temp_store):
        passport = {
            "passport_id": "DPP-IN-2026-A1B2C3D4E5F6",
            "product_name": "Industrial AC Servo Motor 5kW",
            "normalized_key": "industrial ac servo motor 5kw",
            "manufacturer_gstin": "27AAPFU0939F1ZV",
            "sku_code": "MOT-5KW-01",
            "hsn_code": "85015290",
            "official_description": "Multi-phase AC motors of an output exceeding 750 W but not exceeding 75 kW",
            "gst_rate": 18.0,
            "unit_price": 45000.0,
            "is_blocked_17_5": False,
            "status": "ACTIVE",
            "version": 1,
        }
        assert temp_store.upsert_passport(passport)
        fetched = temp_store.get_passport("DPP-IN-2026-A1B2C3D4E5F6")
        assert fetched is not None
        assert fetched["product_name"] == "Industrial AC Servo Motor 5kW"
        assert fetched["gst_rate"] == 18.0

        # Normalized key lookup
        lookup = temp_store.get_by_normalized_key("industrial ac servo motor 5kw", "27AAPFU0939F1ZV")
        assert lookup is not None
        assert lookup["passport_id"] == "DPP-IN-2026-A1B2C3D4E5F6"

    def test_version_recording_and_retrieval(self, temp_store):
        pid = "DPP-IN-2026-A1B2C3D4E5F6"
        passport = {
            "passport_id": pid,
            "product_name": "Test Item",
            "manufacturer_gstin": "27AAPFU0939F1ZV",
            "hsn_code": "73181500",
            "gst_rate": 18.0,
        }
        temp_store.upsert_passport(passport)

        # Record version 1
        temp_store.record_version(
            passport_id=pid,
            version=1,
            author="SYSTEM",
            change_reason="Initial creation",
            changes={"initial": True},
            snapshot=passport,
            checksum="chk_111",
        )

        # Record version 2
        passport["gst_rate"] = 12.0
        temp_store.record_version(
            passport_id=pid,
            version=2,
            author="TAX_OFFICER",
            change_reason="GST Council Rate Revision",
            changes={"gst_rate": 12.0},
            snapshot=passport,
            checksum="chk_222",
        )

        versions = temp_store.get_versions(pid)
        assert len(versions) == 2
        assert versions[0]["version"] == 1
        assert versions[1]["version"] == 2
        assert versions[1]["change_reason"] == "GST Council Rate Revision"


class TestPassportManagerAndModules:
    @pytest.fixture
    def manager(self, tmp_path):
        db_path = tmp_path / "mgr_test.db"
        store = PassportStore(db_path=db_path)
        return PassportManager(store=store)

    def test_create_and_export_passport(self, manager):
        passport = manager.create_passport(
            product_name="SS 304 Hex Nipple 1/2 inch",
            manufacturer_gstin="27AAPFU0939F1ZV",
            hsn_code="73072200",
            official_description="Threaded elbows, bends and sleeves of stainless steel",
            gst_rate=18.0,
            unit_price=120.0,
        )
        assert passport.version == 1
        assert passport.hsn_code == "73072200"

        # Export formats
        json_exp = manager.export_passport(passport.passport_id, "json")
        assert "73072200" in json_exp

        einvoice = manager.export_passport(passport.passport_id, "einvoice")
        assert einvoice["HsnCd"] == "73072200"
        assert einvoice["GstRt"] == 18.0

        qr_data = manager.export_passport(passport.passport_id, "qr")
        assert qr_data["dpp_id"] == passport.passport_id
        assert len(qr_data["sig"]) == 16

    def test_sharing_and_public_view(self, manager):
        passport = manager.create_passport(
            product_name="Allen Cap Screw M12x50",
            manufacturer_gstin="27AAPFU0939F1ZV",
            hsn_code="73181500",
            official_description="Other screws and bolts",
            gst_rate=18.0,
            unit_price=25.0,
        )

        share_rec = manager.share_passport(passport.passport_id, expiry_hours=24)
        assert share_rec.share_token is not None
        assert share_rec.is_valid()

        # Verify token resolves to passport ID
        resolved_pid = manager.share_mgr.verify_token(share_rec.share_token)
        assert resolved_pid == passport.passport_id

        # Public view sanitizes unit price
        public_view = manager.share_mgr.generate_public_view(passport.to_dict())
        assert "unit_price" not in public_view
        assert public_view["hsn_code"] == "73181500"