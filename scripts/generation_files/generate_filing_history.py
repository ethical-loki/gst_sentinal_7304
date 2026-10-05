import os
import numpy as np
import pandas as pd


def generate_supplier_filing_history(
    vendor_master_path="data/raw/masters/vendor_master.csv",
    books_b2b_path="data/raw/books/books_b2b.csv",
    output_path="data/raw/ledgers/supplier_filing_history.csv",
):
  print("Loading master and B2B transaction data...")
  try:
    vendors_df = pd.read_csv(vendor_master_path)
  except FileNotFoundError as e:
    print(f"Error loading vendor master: {e}")
    return

  try:
    books_df = pd.read_csv(books_b2b_path)
  except FileNotFoundError as e:
    print(
        f"Error loading B2B books file from '{books_b2b_path}': {e}. Proceeding"
        " without transactional cross-check."
    )
    books_df = None

  # 1. Precise column mappings based on your actual schema
  v_col = "vendor_id"
  g_col = (
      "vendor_gstin" if "vendor_gstin" in vendors_df.columns else "GSTIN"
  )

  if v_col not in vendors_df.columns or g_col not in vendors_df.columns:
    print(f"Error: Could not find required columns in {vendor_master_path}.")
    print(f"Available columns: {list(vendors_df.columns)}")
    return

  # Step 1: Extract unique vendor_id and GSTIN pairs
  unique_vendors = vendors_df[[v_col, g_col]].drop_duplicates().copy()
  unique_vendors.columns = ["vendor_id", "GSTIN"]  # Normalize names

  # Step 2: Define the 12-Month Timeline (Oct 2025 to Sep 2026)
  periods = pd.period_range(start="2025-10", end="2026-09", freq="M")

  # Step 3: Extract active vendor-months strictly from books_b2b.csv
  active_vendor_months = set()
  if books_df is not None and not books_df.empty:
    book_v_col = "vendor_id"
    # Based on your schema, invoice dates are in 'invoice_dt' (format: DD-MM-YYYY)
    date_col = next(
        (
            c
            for c in ["invoice_dt", "invoice_date", "bill_date", "date"]
            if c in books_df.columns
        ),
        None,
    )

    if book_v_col in books_df.columns and date_col:
      # Parse dates with dayfirst=True since format is DD-MM-YYYY
      books_df[date_col] = pd.to_datetime(
          books_df[date_col], format="%d-%m-%Y", errors="coerce"
      )
      books_df["period_str"] = books_df[date_col].dt.strftime("%Y-%m")

      for _, row in books_df.dropna(subset=[book_v_col, "period_str"]).iterrows():
        active_vendor_months.add((row[book_v_col], row["period_str"]))
      print(
          f"Successfully cross-referenced {len(active_vendor_months)}"
          " active vendor-month records from books_b2b.csv."
      )
    else:
      print(
          "Warning: Could not find 'vendor_id' or date column in books_b2b.csv."
      )

  # Step 4: Assign Vendor Compliance Profiles (~80% Regular, ~15% Occasional, ~5% Chronic)
  np.random.seed(42)
  n_vendors = len(unique_vendors)
  profiles = np.random.choice(
      ["Regular", "Occasional", "Chronic"],
      size=n_vendors,
      p=[0.80, 0.15, 0.05],
  )
  unique_vendors["compliance_profile"] = profiles

  records = []
  print("Generating 12-month compliance timeline...")

  for _, row in unique_vendors.iterrows():
    v_id = row["vendor_id"]
    gstin = row["GSTIN"]
    profile = row["compliance_profile"]

    for period in periods:
      period_str = period.strftime("%Y-%m")

      if profile == "Regular":
        gstr1_filed = np.random.choice([True, False], p=[0.97, 0.03])
        appeared_in_2b = gstr1_filed
        day = np.random.randint(10, 14) if gstr1_filed else None
      elif profile == "Occasional":
        gstr1_filed = np.random.choice([True, False], p=[0.75, 0.25])
        appeared_in_2b = gstr1_filed and np.random.choice(
            [True, False], p=[0.85, 0.15]
        )
        day = np.random.randint(14, 28) if gstr1_filed else None
      else:
        gstr1_filed = False
        appeared_in_2b = False
        day = None

      # Cross-Check with books_b2b data: ensure active transacting vendors maintain compliance
      has_transactions = (v_id, period_str) in active_vendor_months
      if has_transactions and profile == "Regular":
        gstr1_filed = True
        appeared_in_2b = True
        if not day:
          day = np.random.randint(10, 13)

      filing_date = f"{period_str}-{day:02d}" if day else ""

      records.append({
          "vendor_id": v_id,
          "GSTIN": gstin,
          "period": period_str,
          "gstr1_filed": gstr1_filed,
          "appeared_in_2b": appeared_in_2b,
          "filing_date": filing_date,
          "profile_type": profile,
      })

  history_df = pd.DataFrame(records)
  history_df.to_csv(output_path, index=False)
  print(f"Successfully generated '{output_path}' with {len(history_df)} rows.")
  print(history_df["profile_type"].value_counts(normalize=True) * 100)


if __name__ == "__main__":
  generate_supplier_filing_history()