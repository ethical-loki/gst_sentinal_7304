import pandas as pd

from src.search.normalization import MasterHSNEnricher, validate_enriched_master


def test_enriched_master_validation_and_itc_restoration():
    df = pd.read_parquet("data/enriched_master_hsn.parquet")
    report = validate_enriched_master(df)

    assert report["total_rows"] == 4851
    assert report["invalid_or_missing_codes"] == 0
    assert report["duplicate_codes"] == 0
    # 1,066 Excel-truncated 255-char records reduced to <= 35 via itc_hs_codes.json
    assert report["truncated_255_count"] <= 35
    assert "2025-09-22" in report["distinct_effective_dates"]

    for col in (
        "is_residual",
        "is_truncated",
        "is_incomplete",
        "source_provenance",
        "effective_date",
        "notification_ref",
    ):
        assert col in df.columns


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

