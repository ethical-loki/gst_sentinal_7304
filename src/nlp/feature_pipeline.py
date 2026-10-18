import numpy as np
import pandas as pd
from src.nlp.preprocessor import DynamicHSNMasterEngine, clean_text


def build_commercial_features(
    df: pd.DataFrame,
    engine: DynamicHSNMasterEngine,
    hsn_col: str = "declared_hsn",
    desc_col: str = "product_description",
) -> pd.DataFrame:
  """Builds tabular features using Early-Exit Gating on Shannon Entropy.

  Args:
      df: Input DataFrame containing invoice line items.
      engine: Initialized DynamicHSNMasterEngine with statutory tariff master.
      hsn_col: Column name containing the declared HSN/SAC code.
      desc_col: Column name containing product/service text description.

  Returns:
      Enriched DataFrame with calculated commercial, statutory, and entropy features.
  """
  if not isinstance(df, pd.DataFrame):
    raise TypeError(f"Expected pandas DataFrame, got {type(df).__name__}")

  if hsn_col not in df.columns:
    raise KeyError(f"Required HSN column '{hsn_col}' not found in DataFrame.")
  if desc_col not in df.columns:
    raise KeyError(f"Required description column '{desc_col}' not found in DataFrame.")

  processed = df.copy()

  # Handle empty dataframe edge case
  if processed.empty:
    for col in [
        "text_entropy",
        "is_valid_text_structure",
        "clean_description",
        "is_valid_statutory_hsn",
        "official_statutory_description",
        "statutory_gst_rate",
        "text_gate_status",
    ]:
      processed[col] = []
    if "supplier_state" in processed.columns and "declared_pos" in processed.columns:
      processed["is_intra_state"] = []
    if {"cgst_amount", "sgst_amount", "igst_amount", "item_taxable_value"}.issubset(processed.columns):
      processed["declared_effective_rate"] = []
    return processed

  # 1. Step 1: Calculate Entropy and Check Quality Gate
  entropy_evaluations = processed[desc_col].apply(engine.check_entropy_quality)
  processed["text_entropy"] = [res[0] for res in entropy_evaluations]
  processed["is_valid_text_structure"] = [res[1] for res in entropy_evaluations]
  processed["clean_description"] = processed[desc_col].apply(clean_text)

  # 2. Step 2: Quality Gated HSN Lookups
  valid_hsn_flags = []
  official_descs = []
  statutory_rates = []
  processing_status = []

  for _, row in processed.iterrows():
    # If entropy check fails, block and skip HSN processing
    if not row["is_valid_text_structure"]:
      valid_hsn_flags.append(0)
      official_descs.append("BLOCKED_DUE_TO_CORRUPT_DESCRIPTION")
      statutory_rates.append(0.0)
      processing_status.append("BLOCKED_CORRUPT_TEXT")
    else:
      # Valid text passes through to official HSN matching
      hsn_val = row[hsn_col]
      valid_hsn_flags.append(engine.is_valid_hsn(hsn_val))
      official_descs.append(engine.get_statutory_description(hsn_val))
      statutory_rates.append(engine.get_statutory_rate(hsn_val))
      processing_status.append("PROCESSED_SUCCESS")

  processed["is_valid_statutory_hsn"] = valid_hsn_flags
  processed["official_statutory_description"] = official_descs
  processed["statutory_gst_rate"] = statutory_rates
  processed["text_gate_status"] = processing_status

  # 3. Standard Statutory and Commercial Calculations
  if "supplier_state" in processed.columns and "declared_pos" in processed.columns:
    s_state = (
        processed["supplier_state"]
        .astype(str)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
        .str.zfill(2)
    )
    d_pos = (
        processed["declared_pos"]
        .astype(str)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
        .str.zfill(2)
    )
    processed["is_intra_state"] = (s_state == d_pos).astype(int)

  tax_req_cols = {
      "cgst_amount",
      "sgst_amount",
      "igst_amount",
      "item_taxable_value",
  }
  if tax_req_cols.issubset(processed.columns):
    cgst = pd.to_numeric(processed["cgst_amount"], errors="coerce").fillna(0.0)
    sgst = pd.to_numeric(processed["sgst_amount"], errors="coerce").fillna(0.0)
    igst = pd.to_numeric(processed["igst_amount"], errors="coerce").fillna(0.0)
    taxable = pd.to_numeric(processed["item_taxable_value"], errors="coerce").fillna(0.0)

    total_tax = cgst + sgst + igst
    processed["declared_effective_rate"] = np.where(
        taxable > 0,
        ((total_tax / taxable) * 100.0).round(2),
        0.0,
    )

  return processed