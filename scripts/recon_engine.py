"""
Module: scripts/recon_engine.py
Description: Performs reconciliation between purchase books and GSTR-2B files
for B2B, B2BA, CDN and CDNA. Classifies rows as Matched, Value Mismatch,
Tax Period Mismatch or Omitted / Missing in 2B.
Produces final recon_summary.csv + per-category files under data/processed/.
Output includes ALL original columns from both sides + recon_status + remarks
for high-quality training data.
"""

import os
import sys
import pandas as pd


def run_reconciliation():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    print("Running GSTIN GSTR-2B vs Books Reconciliation Engine...")
    print("Categories: B2B | B2BA | CDN | CDNA")
    os.makedirs("data/processed", exist_ok=True)

    # ------------------------------------------------------------------
    # File pairs: (books_file, gstr2b_file, category, note_mode)
    # note_mode=True → use dbt_crdt_no / note_val instead of invoice_no / invoice_val
    # ------------------------------------------------------------------
    pairs = [
        ("data/raw/books/books_b2b.csv",   "data/raw/gstr2b/gstr2b_b2b.csv",   "B2B",  False),
        ("data/raw/books/books_b2ba.csv",  "data/raw/gstr2b/gstr2b_b2ba.csv",  "B2BA", False),
        ("data/raw/books/books_cdn.csv",   "data/raw/gstr2b/gstr2b_cdnr.csv",  "CDN",  True),
        ("data/raw/books/books_cdna.csv",  "data/raw/gstr2b/gstr2b_cdnra.csv", "CDNA", True),
    ]

    all_results = []

    for books_path, gstr2b_path, category, note_mode in pairs:
        print(f"\n→ {category}")

        if not os.path.exists(books_path) or not os.path.exists(gstr2b_path):
            print(f"  ⚠  Skipping – file(s) missing")
            continue

        df_books = pd.read_csv(books_path, dtype=str, low_memory=False)
        df_2b = pd.read_csv(gstr2b_path, dtype=str, low_memory=False)

        # ----- Clean / standardise key columns (temporary, for matching only) -----
        df_books["_gstin_clean"] = df_books["counter_party_gstin"].astype(str).str.strip().str.upper()
        df_2b["_gstin_clean"] = df_2b["counter_party_gstin"].astype(str).str.strip().str.upper()

        if note_mode:
            inv_col = "dbt_crdt_no"
            val_col = "note_val"
        else:
            inv_col = "invoice_no"
            val_col = "invoice_val"

        df_books["_invoice_no_clean"] = df_books[inv_col].astype(str).str.strip().str.upper()
        df_2b["_invoice_no_clean"] = df_2b[inv_col].astype(str).str.strip().str.upper()

        # ----- Merge (prefer row_id when both sides have it) -----
        if "row_id" in df_books.columns and "row_id" in df_2b.columns:
            merged = pd.merge(
                df_books, df_2b,
                on="row_id",
                how="left",
                suffixes=("_books", "_2b"),
            )
        else:
            df_2b = df_2b.drop_duplicates(
                subset=["_gstin_clean", "_invoice_no_clean"], keep="first"
            )
            merged = pd.merge(
                df_books, df_2b,
                on=["_gstin_clean", "_invoice_no_clean"],
                how="left",
                suffixes=("_books", "_2b"),
            )

        # ----- Build recon_status & remarks for every row -----
        statuses = []
        remarks_list = []

        for _, row in merged.iterrows():
            status = "Matched"
            remarks = "OK"

            val_books_raw = row.get(f"{val_col}_books", row.get(val_col, 0))
            val_2b_raw = row.get(f"{val_col}_2b", None)

            # 1. Missing in 2B (PR-70)
            if pd.isna(val_2b_raw):
                status = "Omitted / Missing in 2B"
                remarks = "PR-70: Present in books but missing in GSTR-2B"
            else:
                try:
                    v_b = float(val_books_raw or 0)
                    v_2 = float(val_2b_raw or 0)
                except (ValueError, TypeError):
                    v_b, v_2 = 0.0, 0.0

                # 2. Value mismatch (PR-71) – tolerance ₹1
                if abs(v_b - v_2) > 1.0:
                    status = "Value Mismatch"
                    remarks = "PR-71: Value differs between Books and GSTR-2B"
                else:
                    # 3. Tax-period / filing-period mismatch (PR-75)
                    fp_b = row.get("fp_books", row.get("fp", None))
                    fp_2 = row.get("fp_2b", None)

                    if pd.isna(fp_2):
                        fp_2 = row.get("gstr2b_period_2b", row.get("gstr2b_period", None))
                    if pd.isna(fp_b):
                        fp_b = row.get("tax_period_books", row.get("tax_period", None))

                    if not pd.isna(fp_2) and not pd.isna(fp_b):
                        try:
                            if int(float(fp_b)) != int(float(fp_2)):
                                status = "Tax Period Mismatch"
                                remarks = "PR-75: Shifted filing period in GSTR-2B"
                        except (ValueError, TypeError):
                            if str(fp_b).strip() != str(fp_2).strip():
                                status = "Tax Period Mismatch"
                                remarks = "PR-75: Shifted filing period in GSTR-2B"

            statuses.append(status)
            remarks_list.append(remarks)

        # Add status columns
        merged["category"] = category
        merged["recon_status"] = statuses
        merged["remarks"] = remarks_list

        # Drop temporary matching helper columns
        drop_cols = [c for c in merged.columns if c.startswith("_")]
        merged = merged.drop(columns=drop_cols, errors="ignore")

        # Reorder: category, recon_status, remarks at the front
        front = ["category", "recon_status", "remarks"]
        other = [c for c in merged.columns if c not in front]
        merged = merged[front + other]

        all_results.append(merged)

        # Per-category file (full columns)
        cat_path = f"data/processed/recon_{category.lower()}.csv"
        merged.to_csv(cat_path, index=False)

        total = len(merged)
        matched = (merged["recon_status"] == "Matched").sum()
        pct = (matched / total * 100) if total else 0.0
        print(f"  Total: {total}  |  Matched: {matched} ({pct:.2f}%)")
        print(f"  Columns in output: {len(merged.columns)}")
        print(f"  ✓ {cat_path}")

    # ------------------------------------------------------------------
    # Final combined file
    # ------------------------------------------------------------------
    if all_results:
        df_all = pd.concat(all_results, ignore_index=True, sort=False)
        output_path = "data/processed/recon_summary.csv"
        df_all.to_csv(output_path, index=False)

        total_rows = len(df_all)
        matched_rows = (df_all["recon_status"] == "Matched").sum()
        match_percentage = (matched_rows / total_rows * 100) if total_rows else 0.0

        print(f"\n✓ Reconciliation complete. Total rows: {total_rows}")
        print(f"✓ Matched rows: {matched_rows} ({match_percentage:.2f}%)")
        print(f"✓ Total columns in final file: {len(df_all.columns)}")
        print(f"✓ Final recon summary saved to {output_path}")
    else:
        print("\n⚠ No files processed – check data/raw/ folders")

    print("=== RECONCILIATION ENGINE FINISHED ===")


if __name__ == "__main__":
    run_reconciliation()