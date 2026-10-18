import os
import numpy as np
import pandas as pd


def generate_supplier_responses(
    vendor_master_path="data/raw/masters/vendor_master.csv",
    books_b2b_path="data/raw/books/books_b2b.csv",
    output_path="data/raw/ledgers/supplier_responses.csv",
    target_count=300,
):
  print("Loading vendor master and B2B books...")
  try:
    vendors_df = pd.read_csv(vendor_master_path)
    books_df = pd.read_csv(books_b2b_path)
  except FileNotFoundError:                         
    print("Error loading required files. Please ensure files exist in 'data/raw/masters/' and 'data/raw/books/'.")
    return

  # Extract valid vendor IDs
  if "vendor_id" not in vendors_df.columns:
    print("Error: 'vendor_id' column missing in vendor_master.csv")
    return

  valid_vendors = vendors_df["vendor_id"].dropna().unique()

  # Check required columns in books_b2b
  if "vendor_id" not in books_df.columns or "invoice_no" not in books_df.columns:
    print(
        "Error: 'vendor_id' or 'invoice_no' missing in books_b2b.csv. Please"
        " verify columns."
    )
    return

  # Filter books to only include valid vendors
  filtered_books = books_df[books_df["vendor_id"].isin(valid_vendors)].copy()

  if filtered_books.empty:
    print(
        "Warning: No overlapping vendors found between vendor master and books."
        " Sampling from master and generating fallback invoices."
    )
    # Fallback simulation if books are sparse
    sampled_books = pd.DataFrame({
        "vendor_id": np.random.choice(valid_vendors, size=target_count),
        "invoice_no": [
            f"INV-2026-{i:05d}" for i in range(1, target_count + 1)
        ],
    })
  else:
    # Sample from actual invoices to match the target count (e.g., 300 records)
    if len(filtered_books) >= target_count:
      sampled_books = filtered_books.sample(
          n=target_count, random_state=42
      ).copy()
    else:
      # If books have fewer rows, sample with replacement
      sampled_books = filtered_books.sample(
          n=target_count, replace=True, random_state=42
      ).copy()

  response_types = ["Promised", "Filed", "Disputed"]
  dispute_notes = [
      "GSTIN mismatch on portal",
      "Invoice already declared in GSTR-1 under B2CS",
      "Tax rate amended by mutual agreement",
      "Will file in next tax period cycle",
      "Duplicate entry in books, checking with team",
  ]

  records = []
  np.random.seed(42)

  print("Generating supplier magic-link response log...")

  for _, row in sampled_books.iterrows():
    v_id = row["vendor_id"]
    inv_no = row["invoice_no"]

    # Categorize response status probability (~50% Promised, ~35% Filed, ~15% Disputed)
    resp_type = np.random.choice(
        response_types, p=[0.50, 0.35, 0.15]
    )

    # Generate dates and ARNs based on response type
    if resp_type == "Promised":
      days_ahead = np.random.randint(2, 15)
      promised_date = (
          pd.Timestamp("2026-06-01") + pd.Timedelta(days=days_ahead)
      ).strftime("%Y-%m-%d")
      arn = ""
    elif resp_type == "Filed":
      promised_date = ""
      # Generate a realistic 15-character alphanumeric GST ARN format (e.g., AA2706241234567)
      arn = f"AA{np.random.randint(10, 28):02d}26{np.random.randint(1000000, 9999999)}"
    else:  # Disputed
      promised_date = ""
      arn = ""

    # Timestamp of when the vendor submitted via the portal link
    resp_timestamp = (
        pd.Timestamp("2026-06-01")
        + pd.Timedelta(days=np.random.randint(0, 90), hours=np.random.randint(8, 20))
    ).strftime("%Y-%m-%d %H:%M:%S")

    records.append({
        "supplier_id": v_id,
        "invoice_no": inv_no,
        "response_type": resp_type,
        "promised_date": promised_date,
        "arn": arn,
        "responded_at": resp_timestamp,
    })

  response_df = pd.DataFrame(records)

  # Ensure output directory exists
  output_dir = os.path.dirname(output_path)
  if output_dir and not os.path.exists(output_dir):
    os.makedirs(output_dir, exist_ok=True)

  response_df.to_csv(output_path, index=False)
  print(
      f"Successfully generated '{output_path}' with {len(response_df)} supplier"
      " response logs."
  )
  print(response_df["response_type"].value_counts(normalize=True) * 100)


if __name__ == "__main__":
  generate_supplier_responses()