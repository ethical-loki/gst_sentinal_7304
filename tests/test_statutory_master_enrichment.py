import pandas as pd

from src.search.normalization import MasterHSNEnricher, validate_enriched_master


def test_enriched_master_validation_and_itc_restoration():
    df = pd.read_parquet("data/enriched_master_hsn.parquet")
    sac_df = pd.read_parquet("data/enriched_sac_master.parquet")
    report = validate_enriched_master(df, sac_df=sac_df)

    # Full statutory goods coverage across all 97 non-empty chapters (01-98 excl. reserved Ch 77)
    assert report["total_rows"] >= 18797
    assert report["sac_total_rows"] >= 600
    assert report["distinct_chapters"] == 97
    assert report["invalid_or_missing_codes"] == 0
    assert report["duplicate_codes"] == 0
    # 1,538+ Excel-truncated 255-char descriptions recovered from itc_hs_codes.json across all chapters
    assert report["truncated_255_count"] <= 95
    assert "2025-09-22" in report["distinct_effective_dates"]
    # Legal-note coverage must be reported honestly without inventing missing notes
    assert report["chapters_with_legal_notes"] == 11
    assert report["chapters_without_legal_notes"] == 86

    for col in (
        "section_code",
        "section_title",
        "tariff_schedule",
        "parent_code",
        "is_residual",
        "is_truncated",
        "is_incomplete",
        "missing_parent_heading",
        "missing_parent_subheading",
        "invalid_code_format",
        "quality_flags",
        "source_provenance",
        "source_authority",
        "publication_version",
        "effective_date",
        "notification_ref",
        "legal_notes_count",
        "legal_note_ids",
        "legal_note_coverage_status",
    ):
        assert col in df.columns

    # Missing-note chapters must be explicitly flagged rather than claiming no restrictions exist
    ch01_notes = df[df["chapter_code"] == "01"]["legal_note_coverage_status"].iloc[0]
    assert ch01_notes == "NO_AUTHORITATIVE_NOTES_LOADED"

    # Non-legacy newly imported chapters (e.g., 01, 09, 30, 64, 71, 97) must be present with full hierarchy
    codes = set(df["hsn_code"].astype(str))
    assert "22087011" in codes
    assert len(df[df["chapter_code"] == "09"]) > 0
    assert len(df[df["chapter_code"] == "30"]) > 0
    assert len(df[df["chapter_code"] == "97"]) > 0


def test_seven_audit_hsns_have_authoritative_untruncated_fields():
    df = pd.read_parquet("data/enriched_master_hsn.parquet")
    by_code = df.set_index("hsn_code")

    assert len(str(by_code.loc["84191910", "statutory_description"])) > 255
    assert len(str(by_code.loc["84193900", "statutory_description"])) > 255
    assert "DRYERS" in str(by_code.loc["84193900", "subheading_6digit_desc"]).upper()
    assert len(str(by_code.loc["84198120", "statutory_description"])) > 255
    assert "HOT DRINKS" in str(by_code.loc["84198120", "subheading_6digit_desc"]).upper()
    assert len(str(by_code.loc["85176250", "statutory_description"])) > 255
    assert len(str(by_code.loc["85252011", "statutory_description"])) > 255
    assert "WALKIE TALKIE" in str(by_code.loc["85252011", "tariff_item_desc"]).upper()

    # Genuine residual "OTHER" categories must be preserved honestly
    assert bool(by_code.loc["39219099", "is_residual"]) is True
    assert str(by_code.loc["39219099", "tariff_item_desc"]).upper() == "OTHER"
    assert bool(by_code.loc["85044090", "is_residual"]) is True
    assert "STATIC CONVERTERS" in str(by_code.loc["85044090", "subheading_6digit_desc"]).upper()


def test_config_driven_update_and_explicit_incomplete_flags(tmp_path):
    import json

    stat_rows = [
        {
            "hsn_code": "1001",
            "chapter": "10",
            "description": "WHEAT AND MESLIN",
            "hsn_description": "WHEAT AND MESLIN",
            "effective_date": "2026-01-01",
            "is_blocked_17_5": 0,
            "blocked_17_5_reason": "",
        },
        {
            "hsn_code": "10019910",
            "chapter": "10",
            "description": "WHEAT AND MESLIN - OTHER : SEED QUALITY",
            "hsn_description": "WHEAT AND MESLIN - OTHER : SEED QUALITY",
            "effective_date": "2026-01-01",
            "is_blocked_17_5": 0,
            "blocked_17_5_reason": "",
        },
        {
            "hsn_code": "98060000",
            "chapter": "98",
            "description": "MISSING HEADING PARENT SAMPLE",
            "hsn_description": "MISSING HEADING PARENT SAMPLE",
            "effective_date": "2026-01-01",
            "is_blocked_17_5": 0,
            "blocked_17_5_reason": "",
        },
    ]
    stat_pq = tmp_path / "stat.parquet"
    pd.DataFrame(stat_rows).to_parquet(stat_pq, index=False)

    cfg = {
        "source_authority": "TEST_AUTHORITY",
        "publication_version": "TEST_V2",
        "default_effective_date": "2026-01-01",
        "default_notification_ref": "TEST_NOTIF",
        "sources": {
            "primary_statutory_parquet": str(stat_pq),
            "hierarchy_map_parquet": str(tmp_path / "missing_hm.parquet"),
            "keyword_enrichment_parquet": str(tmp_path / "missing_mc.parquet"),
            "keyword_enrichment_excel": str(tmp_path / "missing_mc.xlsx"),
            "itc_untruncated_json": str(tmp_path / "missing_itc.json"),
            "gst_rates_json": str(tmp_path / "missing_gst.json"),
            "legal_notes_json": str(tmp_path / "missing_notes.json"),
        },
        "wco_sections": [
            {"start": 6, "end": 14, "section": "Section II", "title": "Vegetable Products"},
        ],
    }
    cfg_path = tmp_path / "cfg.json"
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")

    enricher = MasterHSNEnricher(config_path=cfg_path)
    out_df = enricher.process().set_index("hsn_code")
    assert out_df.loc["10019910", "source_authority"] == "TEST_AUTHORITY"
    assert out_df.loc["10019910", "publication_version"] == "TEST_V2"
    assert out_df.loc["10019910", "section_code"] == "Section II"
    assert bool(out_df.loc["98060000", "missing_parent_heading"]) is True
    assert bool(out_df.loc["98060000", "is_incomplete"]) is True
    assert "MISSING_PARENT_HEADING" in str(out_df.loc["98060000", "quality_flags"])


