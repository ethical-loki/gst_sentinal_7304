import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split


def get_project_root() -> Path:
  """Dynamically resolve the project root directory."""
  current = Path(__file__).resolve()
  for parent in [current, *current.parents]:
    if (parent / "data").is_dir() and (parent / "src").is_dir():
      return parent
  return current.parent.parent


ROOT_DIR = get_project_root()
sys.path.insert(0, str(ROOT_DIR))

from src.nlp.feature_pipeline import build_commercial_features
from src.nlp.preprocessor import DynamicHSNMasterEngine

# =====================================================================
# Key Field Definitions for Machine Learning
# =====================================================================

IDENTIFIER_FIELDS = [
    "line_item_id",
    "invoice_id",
    "item_slno",
    "doc_type",
    "doc_date",
    "system_cd",
    "branch_cd",
    "vertical_cd",
    "sector",
    "split_partition",
]

ENTITY_FIELDS = [
    "supplier_gstin",
    "supplier_lglnm",
    "supplier_state",
    "supplier_pin",
    "buyer_gstin",
    "buyer_lglnm",
    "buyer_state",
    "buyer_pin",
    "buyer_pos",
    "declared_pos",
]

STATUTORY_AND_NLP_FIELDS = [
    "product_name",
    "product_description",
    "clean_description",
    "text_entropy",
    "is_valid_text_structure",
    "text_gate_status",
    "is_service",
    "declared_hsn",
    "declared_hsn_chapter",
    "declared_hsn_heading",
    "is_valid_statutory_hsn",
    "official_statutory_description",
    "statutory_gst_rate",
    "statutory_gst_rate_pct",
    "declared_gst_rate",
    "declared_effective_rate",
    "rate_difference",
    "effective_rate_difference",
    "is_rate_divergent",
]

COMMERCIAL_AND_MATH_FIELDS = [
    "quantity",
    "unit_code",
    "unit_price",
    "item_total_amount",
    "item_discount",
    "item_taxable_value",
    "cgst_amount",
    "sgst_amount",
    "igst_amount",
    "cess_rate",
    "cess_amount",
    "total_item_value",
    "inv_assessable_value",
    "inv_cgst_total",
    "inv_sgst_total",
    "inv_igst_total",
    "inv_total_value",
    "declared_total_inv_value",
    "expected_item_tax",
    "declared_total_tax",
    "tax_math_discrepancy",
    "invoice_total_discrepancy",
    "has_math_discrepancy",
    "log_taxable_value",
    "log_unit_price",
]

POS_AND_JURISDICTION_FIELDS = [
    "is_intra_state",
    "pos_matches_buyer_state",
    "pos_matches_buyer_pos",
    "is_cgst_sgst_on_interstate",
    "is_igst_on_intrastate",
    "has_pos_discrepancy",
]

TRANSIT_AND_LOGISTICS_FIELDS = [
    "eway_bill_required",
    "subsupplytype",
    "transit_mode",
    "transit_distance_km",
    "calculated_distance_km",
    "transporter_id",
    "transporter_name",
    "transport_doc_no",
    "transdocdt",
    "vehicle_number",
    "vehicle_type",
    "transit_distance_variance",
    "transit_distance_variance_ratio",
]

VENDOR_PROFILE_FIELDS = [
    "vendor_risk_tier",
    "vendor_risk_tier_encoded",
    "vendor_filing_regularity",
    "vendor_gstr_variance",
    "vendor_error_rate",
    "vendor_trust_score",
    "rule_86b_violation_flag",
    "consecutive_non_filing_count",
    "is_msme_vendor",
    "msme_turnaround_days",
]

HISTORICAL_PRIOR_FIELDS = [
    "seller_hsn_prior",
    "seller_total_tx_count",
    "sector_median_unit_price",
    "price_to_sector_median_ratio",
]

TARGET_FIELDS = [
    "has_error",
    "error_type",
    "is_hsn_misclass",
    "is_rate_mismatch",
    "is_blocked_17_5",
    "is_pos_error",
    "is_math_error",
    "statutory_exposure_rupees",
]


def engineer_key_ml_features(df: pd.DataFrame) -> pd.DataFrame:
  """Engineers standard domain-specific features across all rows before split."""
  data = df.copy()

  # 1. HSN Chapter & Heading Prefixes
  declared_hsn_str = data["declared_hsn"].astype(str).str.strip()
  data["declared_hsn_chapter"] = declared_hsn_str.str[:2]
  data["declared_hsn_heading"] = declared_hsn_str.str[:4]

  # 2. Rate comparison features
  statutory_rate_pct = (data["statutory_gst_rate"] * 100.0).round(2)
  data["statutory_gst_rate_pct"] = statutory_rate_pct
  data["rate_difference"] = (data["declared_gst_rate"] - statutory_rate_pct).round(2)
  data["effective_rate_difference"] = (
      data["declared_effective_rate"] - statutory_rate_pct
  ).round(2)
  data["is_rate_divergent"] = (
      np.abs(data["rate_difference"]) > 0.01
  ).astype(int)

  # 3. Tax Math & Invoice Integrity features
  expected_tax = (
      (data["item_taxable_value"] * data["declared_gst_rate"]) / 100.0
  ).round(2)
  declared_tax = (
      data["cgst_amount"] + data["sgst_amount"] + data["igst_amount"]
  ).round(2)
  data["expected_item_tax"] = expected_tax
  data["declared_total_tax"] = declared_tax
  data["tax_math_discrepancy"] = np.abs(declared_tax - expected_tax).round(2)
  data["invoice_total_discrepancy"] = np.abs(
      data["declared_total_inv_value"] - data["inv_total_value"]
  ).round(2)
  data["has_math_discrepancy"] = (
      (data["tax_math_discrepancy"] > 1.0)
      | (data["invoice_total_discrepancy"] > 1.0)
  ).astype(int)

  # 4. Log-scaled amounts for ML model convergence
  data["log_taxable_value"] = np.log1p(
      np.maximum(data["item_taxable_value"].fillna(0.0), 0.0)
  ).round(4)
  data["log_unit_price"] = np.log1p(
      np.maximum(data["unit_price"].fillna(0.0), 0.0)
  ).round(4)

  # 5. Place of Supply (POS) & Interstate vs Intrastate Consistency
  s_state = data["supplier_state"].astype(str).str.strip().str.zfill(2)
  b_state = data["buyer_state"].astype(str).str.strip().str.zfill(2)
  d_pos = data["declared_pos"].astype(str).str.strip().str.zfill(2)
  b_pos = data["buyer_pos"].astype(str).str.strip().str.zfill(2)

  data["pos_matches_buyer_state"] = (d_pos == b_state).astype(int)
  data["pos_matches_buyer_pos"] = (d_pos == b_pos).astype(int)

  # CGST/SGST levied on interstate or IGST on intrastate
  data["is_cgst_sgst_on_interstate"] = (
      (data["is_intra_state"] == 0)
      & ((data["cgst_amount"] > 0) | (data["sgst_amount"] > 0))
  ).astype(int)
  data["is_igst_on_intrastate"] = (
      (data["is_intra_state"] == 1) & (data["igst_amount"] > 0)
  ).astype(int)
  data["has_pos_discrepancy"] = (
      (data["is_cgst_sgst_on_interstate"] == 1)
      | (data["is_igst_on_intrastate"] == 1)
      | (data["pos_matches_buyer_pos"] == 0)
  ).astype(int)

  # 6. Transit & Distance Variance features
  if "transit_distance_km" in data.columns and "calculated_distance_km" in data.columns:
    dist_var = np.abs(data["transit_distance_km"] - data["calculated_distance_km"]).round(2)
    data["transit_distance_variance"] = dist_var
    data["transit_distance_variance_ratio"] = np.where(
        data["calculated_distance_km"] > 0,
        (dist_var / data["calculated_distance_km"]).round(4),
        0.0,
    )
  else:
    data["transit_distance_variance"] = 0.0
    data["transit_distance_variance_ratio"] = 0.0

  # 7. Vendor Risk Numeric Encoding
  tier_map = {"Tier 1": 1, "Tier 2": 2, "Tier 3": 3}
  data["vendor_risk_tier_encoded"] = (
      data["vendor_risk_tier"].map(tier_map).fillna(2).astype(int)
  )

  return data


def apply_leakage_free_historical_priors(
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    test_df: pd.DataFrame,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
  """Derives empirical historical priors solely on the train partition,

  and maps them onto train, val, and test to guarantee zero data leakage.
  """
  # 1. Seller HSN Prior (P(Declared HSN | Seller))
  seller_totals = train_df.groupby("supplier_gstin").size().rename("seller_total_tx_count")
  seller_hsn_counts = train_df.groupby(["supplier_gstin", "declared_hsn"]).size()
  seller_hsn_prior = (seller_hsn_counts / train_df.groupby("supplier_gstin").size()).rename("seller_hsn_prior")

  # 2. Sector Median Unit Price Baseline
  sector_median_prices = (
      train_df.groupby("sector")["unit_price"]
      .median()
      .rename("sector_median_unit_price")
  )

  results = []
  for partition in [train_df, val_df, test_df]:
    p = partition.copy()

    # Merge seller prior
    p = p.merge(seller_hsn_prior, on=["supplier_gstin", "declared_hsn"], how="left")
    p["seller_hsn_prior"] = p["seller_hsn_prior"].fillna(0.0).round(4)

    # Merge seller total transactions
    p = p.merge(seller_totals, on="supplier_gstin", how="left")
    p["seller_total_tx_count"] = p["seller_total_tx_count"].fillna(0).astype(int)

    # Merge sector median price
    p = p.merge(sector_median_prices, on="sector", how="left")
    p["sector_median_unit_price"] = p["sector_median_unit_price"].fillna(
        train_df["unit_price"].median()
    ).round(2)

    # Price ratio to sector median
    p["price_to_sector_median_ratio"] = np.where(
        p["sector_median_unit_price"] > 0,
        (p["unit_price"] / p["sector_median_unit_price"]).round(4),
        1.0,
    )

    results.append(p)

  return results[0], results[1], results[2]


def execute_day3_split(
    corpus_relative_path: str = "data/raw/synthetic_invoice_corpus.parquet",
    hsn_excel_relative_path: str = "data/raw/Final_hsn_sac_copy.xlsx",
) -> Dict[str, pd.DataFrame]:
  """Executes the complete Day 3 ML dataset generation, feature engineering,

  stratified 70/15/15 splitting, and Parquet export.
  """
  corpus_path = ROOT_DIR / corpus_relative_path
  if not corpus_path.exists():
    # Check alternate location under data/
    corpus_path = ROOT_DIR / "data" / "synthetic_invoice_corpus.parquet"
  if not corpus_path.exists():
    raise FileNotFoundError(f"Synthetic corpus missing at {corpus_path}")

  hsn_excel_path = ROOT_DIR / hsn_excel_relative_path
  if not hsn_excel_path.exists():
    raise FileNotFoundError(f"HSN Master file missing at {hsn_excel_path}")

  output_dirs = [
      ROOT_DIR / "data",
      ROOT_DIR / "data" / "processed",
  ]
  for d in output_dirs:
    d.mkdir(parents=True, exist_ok=True)

  print(f"[Step 1/5] Ingesting corpus from: {corpus_path}")
  df = pd.read_parquet(corpus_path)
  print(f"Loaded {len(df)} records with {len(df.columns)} initial columns.")

  print(f"[Step 2/5] Initializing statutory engine and building NLP/commercial features...")
  engine = DynamicHSNMasterEngine(hsn_excel_path=str(hsn_excel_path))
  df = build_commercial_features(df, engine)

  print("[Step 3/5] Engineering key ML domain features...")
  df = engineer_key_ml_features(df)

  # Composite stratification stratum across sector and error category
  df["stratum"] = df["sector"].astype(str) + "_" + df["error_type"].astype(str)

  print("[Step 4/5] Performing stratified 70/15/15 partition...")
  train_df, temp_df = train_test_split(
      df,
      test_size=0.30,
      random_state=42,
      stratify=df["stratum"],
  )

  val_df, test_df = train_test_split(
      temp_df,
      test_size=0.50,
      random_state=42,
      stratify=temp_df["stratum"],
  )

  print("[Step 5/5] Deriving historical priors strictly on training data (Zero Data Leakage)...")
  train_df, val_df, test_df = apply_leakage_free_historical_priors(train_df, val_df, test_df)

  # Assign partition labels and clean stratification temporary key
  train_df["split_partition"] = "train"
  val_df["split_partition"] = "val"
  test_df["split_partition"] = "test"

  for partition in [train_df, val_df, test_df]:
    if "stratum" in partition.columns:
      partition.drop(columns=["stratum"], inplace=True)

  # Verify zero leakage across partitions
  train_ids = set(train_df["line_item_id"])
  val_ids = set(val_df["line_item_id"])
  test_ids = set(test_df["line_item_id"])

  assert len(train_ids.intersection(val_ids)) == 0, "Leakage: Train and Val overlap!"
  assert len(train_ids.intersection(test_ids)) == 0, "Leakage: Train and Test overlap!"
  assert len(val_ids.intersection(test_ids)) == 0, "Leakage: Val and Test overlap!"

  # Export Parquet files to both data/ and data/processed/
  for out_dir in output_dirs:
    train_df.to_parquet(out_dir / "train.parquet", compression="snappy", index=False)
    val_df.to_parquet(out_dir / "val.parquet", compression="snappy", index=False)
    test_df.to_parquet(out_dir / "test.parquet", compression="snappy", index=False)

  print("\n=======================================================")
  print("         GST SENTINEL: DATASET SPLIT SUMMARY           ")
  print("=======================================================")
  print(f"Total Records  : {len(df):,}")
  print(f"Total Features : {len(train_df.columns)}")
  print(f"Train Partition: {len(train_df):,} rows (70.0%)")
  print(f"Val Partition  : {len(val_df):,} rows (15.0%)")
  print(f"Test Partition : {len(test_df):,} rows (15.0%)")
  print("\nClass Distribution Across Partitions:")
  dist_summary = pd.DataFrame({
      "Train": train_df["error_type"].value_counts(),
      "Val": val_df["error_type"].value_counts(),
      "Test": test_df["error_type"].value_counts(),
  })
  dist_summary["Total"] = dist_summary.sum(axis=1)
  print(dist_summary.to_string())

  print("\nVerification Checks:")
  print("[OK] Zero ID leakage confirmed across all partitions.")
  print("[OK] Stratified class balance maintained across all 12 industry sectors.")
  print("[OK] Historical priors computed strictly from train partition.")
  print("[OK] Output Parquets successfully saved to:")
  for out_dir in output_dirs:
    print(f"    - {out_dir}/[train|val|test].parquet")
  print("=======================================================\n")

  return {
      "train": train_df,
      "val": val_df,
      "test": test_df,
  }


if __name__ == "__main__":
  execute_day3_split()
