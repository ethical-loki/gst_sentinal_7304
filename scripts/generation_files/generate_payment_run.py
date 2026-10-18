import os
import numpy as np
import pandas as pd


def generate_payment_runs(
    books_b2b_path="data/raw/books/books_b2b.csv",
    filing_history_path="data/raw/ledgers/supplier_filing_history.csv",
    output_path="data/raw/ledgers/payment_runs.csv",
):
  print("Loading B2B books and supplier filing history...")
  try:
    books_df = pd.read_csv(books_b2b_path)
    history_df = pd.read_csv(filing_history_path)
  except FileNotFoundError:
    print("Error loading required files. Please ensure files exist in 'data/raw/books/' and 'data/raw/ledgers'.")
    return

  # Dynamically find the date column in books_b2b
  date_col = next(
      (
          c
          for c in ["invoice_dt", "invoice_date", "bill_date", "date"]
          if c in books_df.columns
      ),
      None,
  )
  if not date_col:
    print("Error: Could not find invoice date column in books_b2b.csv")
    return

  # Parse dates dynamically based on format (handling both DD-MM-YYYY or standard YYYY-MM-DD)
  books_df[date_col] = pd.to_datetime(books_df[date_col], errors="coerce")
  books_df["period_str"] = books_df[date_col].dt.strftime("%Y-%m")

  # Drop rows where period couldn't be determined
  books_df = books_df.dropna(subset=["period_str"])

  # Merge books with filing history dynamically on vendor and period
  merged_df = pd.merge(
      books_df,
      history_df,
      left_on=["vendor_id", "period_str"],
      right_on=["vendor_id", "period"],
      how="left",
  )

  # Dynamically derive unique periods present in the books to build corresponding payment runs
  unique_periods = sorted(merged_df["period_str"].unique())
  print(
      f"Discovered {len(unique_periods)} unique transaction periods in books:"
      f" {unique_periods}"
  )

  run_cycles = []
  for p in unique_periods:
    # Convert period 'YYYY-MM' to a payment run execution date (e.g., 5th of the following month)
    p_date = pd.to_datetime(p + "-01")
    run_date = (p_date + pd.DateOffset(months=1, days=4)).strftime("%Y-%m-%d")
    run_id = f"RUN-{p.replace('-', '-')}"
    run_cycles.append((run_id, run_date, p))

  approvers = [
      "CFO_Office",
      "Finance_Lead_A",
      "Finance_Lead_B",
      "Automated_Gateway",
  ]
  override_reasons = [
      "",
      "",
      "",
      "Vendor emergency sign-off by Finance Head",
      "Exigency approval for strategic vendor",
      "Verified offline challan proof",
  ]

  payment_records = []
  np.random.seed(42)

  print(
      "Simulating payment execution decisions and split calculations"
      " dynamically..."
  )

  for run_id, run_date, target_period in run_cycles:
    # Filter invoices belonging to this specific dynamic period
    cycle_invoices = merged_df[merged_df["period_str"] == target_period]

    if cycle_invoices.empty:
      continue

    for _, inv in cycle_invoices.iterrows():
      total_val = (
          inv["invoice_val"]
          if "invoice_val" in inv and not pd.isna(inv["invoice_val"])
          else 10000.0
      )

      # Sum tax amounts safely
      tax_val = sum(
          [
              inv.get("igst_amnt", 0) or 0,
              inv.get("cgst_amnt", 0) or 0,
              inv.get("sgst_amnt", 0) or 0,
          ]
      )
      base_val = total_val - tax_val

      appeared_2b = inv.get("appeared_in_2b", True)
      profile = inv.get("profile_type", "Regular")

      # Pay-Safe Gate Logic
      if appeared_2b and profile == "Regular":
        decision = "Pay in Full"
        paid_now = total_val
        held_amount = 0.0
        hold_status = "Released"
        release_on = run_date
      elif not appeared_2b and profile == "Chronic":
        decision = "Hold Fully"
        paid_now = 0.0
        held_amount = total_val
        hold_status = "Active"
        release_on = ""
      else:  # Occasional or temporarily missing in 2B
        decision = "Pay Base, Hold GST"
        paid_now = base_val
        held_amount = tax_val
        hold_status = "Active" if np.random.rand() > 0.4 else "Released"
        release_on = run_date if hold_status == "Released" else ""

      # Check for manual overrides (~5% chance)
      override_reason = ""
      approver = np.random.choice(approvers, p=[0.1, 0.2, 0.2, 0.5])
      if decision != "Pay in Full" and np.random.rand() < 0.05:
        decision = "Pay in Full (Overridden)"
        paid_now = total_val
        held_amount = 0.0
        override_reason = np.random.choice(override_reasons[3:])
        hold_status = "Overridden"

      payment_records.append({
          "run_id": run_id,
          "run_date": run_date,
          "payable_id": inv.get("row_id", "B2B-00001"),
          "vendor_id": inv.get("vendor_id", "VND-001"),
          "decision": decision,
          "paid_now": round(paid_now, 2),
          "held_amount": round(held_amount, 2),
          "approver": approver,
          "override_reason": override_reason,
          "hold_status": hold_status,
          "release_on": release_on,
      })

  runs_df = pd.DataFrame(payment_records)

  # Ensure output directory exists
  output_dir = os.path.dirname(output_path)
  if output_dir and not os.path.exists(output_dir):
    os.makedirs(output_dir, exist_ok=True)

  runs_df.to_csv(output_path, index=False)
  print(
      f"Successfully generated '{output_path}' with {len(runs_df)} payment records"
      f" covering {len(run_cycles)} dynamic runs."
  )
if __name__ == "__main__":
  generate_payment_runs()