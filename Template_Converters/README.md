# GST E-Invoice & E-Way Bill Template Converter Engine

A robust, enterprise-grade data transformation, sanitization, and compliance validation engine designed for Indian Goods and Services Tax (GST) **E-Invoicing (NIC IRN)** and **E-Way Bill (EWB)** systems.

This module automates the ingestion of unformatted or "dirty" ERP/accounting payloads, normalizes structures and data formats, validates them against 50+ official National Informatics Centre (NIC) statutory rules, and produces production-ready payloads alongside complete audit trails in multiple formats.

---

## Table of Contents
1. [Architecture & Pipeline Workflow](#architecture--pipeline-workflow)
2. [Key Design Principles & Compliance Rules](#key-design-principles--compliance-rules)
   - [Strict Non-Normalization of GSTINs](#1-strict-non-normalization-of-gstins)
   - [Cross-State PIN Code Validation (NIC 3039 & 3041)](#2-cross-state-pin-code-validation-nic-3039--3041)
   - [Automated Rectification vs. Compliance Errors](#3-automated-rectification-vs-compliance-errors)
   - [Tax Math & Interstate vs. Intrastate Reconciliation](#4-tax-math--interstate-vs-intrastate-reconciliation)
3. [File-by-File Technical Breakdown](#file-by-file-technical-breakdown)
4. [Official NIC Error Catalog & Resolutions](#official-nic-error-catalog--resolutions)
5. [Execution Guide & How-To](#execution-guide--how-to)
6. [Output Artifacts & Audit Reporting](#output-artifacts--audit-reporting)

---

## Architecture & Pipeline Workflow

The conversion engine processes invoices through a four-stage pipeline:

```
+-----------------------------------------------------------------------------------+
|                           1. Dirty Input Layer                                    |
|  - Ingests dirty_customer_input.json                                              |
|  - Handles comma decimals, irregular dates, unpadded state codes, and whitespace  |
+-----------------------------------------------------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                     2. Normalization & Tax Math Layer                             |
|                           (payload_builder.py)                                    |
|  - Cleans dates (DD-MM-YYYY), parses decimal numbers, pads state codes            |
|  - Re-computes tax splits (CGST+SGST vs IGST based on POS and Supplier State)     |
|  - Formats data strictly into official NIC JSON schema structure                  |
|  - Preserves invalid GSTINs untouched (no guessing or artificial completions)    |
|  - Logs every change under AUTO_CORRECTION in the audit stream                    |
+-----------------------------------------------------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                      3. Statutory Compliance Validator                            |
|                                (validator.py)                                     |
|  - Validates against 50+ official NIC error codes                                 |
|  - Checks PIN code vs. State matching using STATE_MASTER                          |
|  - Checks Export/SEZ foreign currencies and port codes                            |
|  - Reconciles line-item totals against header value summaries                     |
+-----------------------------------------------------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                        4. Multi-Format Output Layer                               |
|                     (E-invoice_e_way coverter.py)                                 |
|  - corrected_payload.json         (Clean NIC-ready JSON)                          |
|  - correction_audit_report.csv    (Line-by-line audit spreadsheet)                |
|  - audit_summary.txt              (Executive human-readable summary)              |
|  - validation_report.json         (Detailed machine-readable validation result)   |
+-----------------------------------------------------------------------------------+
```

---

## Key Design Principles & Compliance Rules

### 1. Strict Non-Normalization of GSTINs
- **Policy**: GSTINs (`self_gstin`, `supplier_gstin`, `buyer_gstin`, `disp_gstin`, `ship_gstin`) are legal identifiers and must **never** be auto-completed, trimmed, or guessed.
- If a customer inputs a 10-character PAN or truncated string (e.g. `36SQORB466`), the engine leaves the input exactly as entered.
- The validator marks the invoice as `INVALID` and flags **NIC Error 2289** or **2288** in the audit logs:
  - *Error*: `Invalid self_gstin length (10). Must be exactly 15 characters.`
  - *Resolution*: `Provide valid 15-character supplier GSTIN`.

### 2. Cross-State PIN Code Validation (NIC 3039 & 3041)
- **Policy**: Every 6-digit postal PIN code must belong to the geographic jurisdiction of the declared State Code.
- In `error_mappings.py`, `STATE_MASTER` maintains the complete 2-digit PIN prefix mapping for all 38 Indian States and Union Territories.
  - *Example*: State `27` (Maharashtra) allows PIN prefixes `["40", "41", "42", "43", "44"]`.
  - *Example*: State `33` (Tamil Nadu) allows PIN prefixes `["60", "61", "62", "63", "64"]`.
- If a customer specifies State Code `27` with PIN `641001` (Coimbatore, Tamil Nadu), the engine rejects the record and generates:
  - **Error 3039** on `supplierdt1.supplier_pin`: `Pincode '641001' of supplier does not belong to State '27' (Maharashtra).`
  - **Error 3041** on `buyerdt1.buyer_pin` or `shipdtl.ship_pin`: `Buyer Pincode '641001' does not belong to State '27' (Maharashtra).`

### 3. Automated Rectification vs. Compliance Errors
The engine classifies findings into two distinct categories:

1. **`AUTO_CORRECTION`**: Safe, non-destructive data repairs that do not alter commercial terms:
   - Date formats (`YYYY-MM-DD`, `DD.MM.YYYY`, `DD/MM/YYYY`) standardized to `DD-MM-YYYY`.
   - Comma-delimited decimals (e.g. `"145423,37"`) converted to standard floats (`145423.37`).
   - Single-digit state codes (e.g. `"7"`) zero-padded to 2 digits (`"07"`).
   - Stripping unwanted leading/trailing whitespace.
2. **`COMPLIANCE_ERROR`**: Statutory or regulatory violations that prevent legal filing on the government portal (e.g., mismatched tax splits, invalid GSTINs, state-to-PIN mismatches).

### 4. Tax Math & Interstate vs. Intrastate Reconciliation
The engine computes and verifies tax amounts according to Indian GST law:
- **Intrastate Supply** (`pos == supplier_state`):
  - Must apply **CGST** and **SGST** (each at exactly `Rate / 2`).
  - **IGST** must be `0.0`.
- **Interstate Supply** (`pos != supplier_state`):
  - Must apply **IGST** (at full `Rate`).
  - **CGST** and **SGST** must be `0.0`.
- **Line & Header Reconciliation**:
  - `totamt = qty * unitprice`
  - `assamt = totamt - discount + othchrg`
  - Line Item Total: `totitemval = assamt + cgstamt + sgstamt + igstamt + cessamt + cesnonadval`
  - Header Total: `totinvval == sum(totitemval) + rndoffamt` (with a ±₹2 rounding tolerance allowed).

---

## File-by-File Technical Breakdown

| File | Purpose & Responsibilities |
| :--- | :--- |
| **`E-invoice_e_way coverter.py`** | Main entry point and workflow orchestrator. Reads input JSON, calls normalization and validation layers, and exports all 4 output reports. |
| **`validator.py`** | Core statutory validation engine (`GSTValidator`). Implements 50+ official NIC validation rules across Document, Supplier, Buyer, Dispatch, Shipping, Item, Valuation, Export, and E-Way Bill sections. |
| **`payload_builder.py`** | Data sanitizer and schema transformer (`PayloadBuilder`). Normalizes dirty values, performs tax math recomputations, assembles the official NIC structure, and logs change events. |
| **`error_mappings.py`** | Master reference data and catalog repository. Contains `STATE_MASTER` (state codes & PIN prefixes), `COUNTRY_MASTER`, `COUNTRY_CURRENCY_MAP`, `ALLOWED_UQC`, `PORT_CODES`, and the official `NIC_ERROR_CODES` dictionary. |
| **`generate_sample_dirty_input.py`** | Synthetic dirty test data generator. Emits realistic test invoices with dirty values (mixed dates, comma decimals, unpadded state codes, messy spacing) for testing. |
| **`dirty_customer_input.json`** | Default input file containing raw, unformatted, or dirty customer invoices. |

---

## Official NIC Error Catalog & Resolutions

The validator checks for and reports official NIC error codes, including:

| Code | Field / Area | Trigger Condition | Recommended Resolution |
| :---: | :--- | :--- | :--- |
| **2289** | `self_gstin` / `supplier_gstin` | Missing, blank, truncated (< 15 chars), or format error | Provide valid 15-character supplier GSTIN |
| **2288** | `buyer_gstin` | Invalid length, bad format, or non-alphanumeric | Provide valid 15-character buyer GSTIN or 'URP' |
| **2264** | `supplier_state` | Supplier state does not match first 2 digits of supplier GSTIN | Ensure state code matches GSTIN prefix |
| **2265** | `buyer_state` | Buyer state does not match first 2 digits of buyer GSTIN | Ensure buyer state matches buyer GSTIN prefix |
| **3039** | `supplier_pin` | Supplier PIN code prefix does not belong to Supplier State | Provide PIN code belonging to the supplier state |
| **3041** | `buyer_pin` / `ship_pin` | Buyer/Ship PIN prefix does not belong to specified State | Provide PIN code belonging to the destination state |
| **2211** | `buyer_gstin` | Supplier GSTIN and Buyer GSTIN are identical (self-invoicing) | Supplier and recipient GSTIN must be different |
| **2212** | `buyer_gstin` | Buyer GSTIN is set to 'URP' for B2B / B2G / SEZ transactions | Buyer GSTIN cannot be 'URP' for registered B2B supplies |
| **2248** | `buyer_gstin` | Buyer GSTIN is not 'URP' for Direct Export transactions | Recipient must be 'URP' for export supplies |
| **2276** | `supplier_pin` | Supplier PIN code is 999999 | Supplier PIN code cannot be 999999 |
| **2274** | `buyer_pin` | Domestic buyer PIN code is 999999 | PIN code 999999 is only allowed for foreign exports |
| **2275** | `buyer_pin` | Export buyer PIN code is not 999999 | Foreign export recipient PIN must be 999999 |
| **2202** | `cntcode` | Export country code missing or invalid ISO code | Provide valid 2-letter ISO country code |
| **2203** | `forcur` | Currency code does not match export destination country | Provide matching currency code (e.g. US -> USD) |
| **2220** | `itemdtls.cgstamt` | Intra-state CGST rate != SGST rate | CGST and SGST rates must be equal (Rate/2) |
| **2221** | `itemdtls.igstamt` | CGST/SGST charged on inter-state, or IGST on intra-state | Apply IGST for inter-state and CGST+SGST for intra-state |

---

## Execution Guide & How-To

### Prerequisites
- Python 3.8 or higher.
- Standard Python libraries (`json`, `csv`, `re`, `datetime`, `collections`). No external packages required.

### 1. Generating Test Input Data
To generate a sample batch of dirty invoices:
```powershell
py "Template_Converters/generate_sample_dirty_input.py"
```
*Creates or refreshes `Template_Converters/dirty_customer_input.json`.*

### 2. Running the Converter & Validation Pipeline
To run the full conversion, normalization, validation, and audit process:
```powershell
py "Template_Converters/E-invoice_e_way coverter.py"
```

### Terminal Output Sample:
```text
[FILE] Reading input file: C:\Users\User\OneDrive\Desktop\GST_Sentinal\Template_Converters\dirty_customer_input.json
[PROCESSING] Normalizing dirty keys, formats, and re-calculating tax math...
[VALIDATING] Checking against official NIC IRN & EWB compliance rules...
[FILE GENERATED] Clean NIC Payload (JSON)  : C:\Users\User\OneDrive\Desktop\GST_Sentinal\Template_Converters\corrected_payload.json
[FILE GENERATED] Validation Report (JSON)  : C:\Users\User\OneDrive\Desktop\GST_Sentinal\Template_Converters\validation_report.json
[FILE GENERATED] Audit Report (Excel/CSV)  : C:\Users\User\OneDrive\Desktop\GST_Sentinal\Template_Converters\correction_audit_report.csv
[FILE GENERATED] Audit Summary (Text File) : C:\Users\User\OneDrive\Desktop\GST_Sentinal\Template_Converters\audit_summary.txt

=== Completed Pipeline: Total: 2 | Valid: 1 | Errors: 1 ===
All details and corrections have been logged to the generated files above.
```

---

## Output Artifacts & Audit Reporting

Upon execution, four output files are automatically produced:

### 1. `corrected_payload.json`
The cleaned, sanitized JSON payload conforming to the official NIC E-Invoice JSON schema. This payload is ready for submission to government E-Invoice registration portals.

### 2. `correction_audit_report.csv`
A detailed spreadsheet tracking every modification and flagged error with the following columns:
- `Invoice Number`: Document number.
- `Invoice Status`: Overall status (`VALID` or `INVALID`).
- `Type`: `AUTO_CORRECTION` (system fixed) or `COMPLIANCE_ERROR` (user must fix).
- `Category / Error Code`: Rule identifier or official NIC Error Code.
- `Field / JSON Path`: Exact target field path (e.g. `docdt1.docdt`, `itemdtls[1].assamt`).
- `Customer Original Value`: Value as provided by the customer.
- `System Corrected Value`: Value after system normalization.
- `Description / Rule Reason`: Detailed rationale and guidance.

### 3. `audit_summary.txt`
A concise executive summary outlining total invoice counts, compliance rates, a breakdown of automatic corrections, and unresolved compliance issues with actionable steps.

### 4. `validation_report.json`
A machine-readable JSON report listing each invoice's compliance status and complete array of validation errors for programmatic downstream integration.
