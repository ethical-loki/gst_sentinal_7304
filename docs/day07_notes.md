# Day 07: Plain English Guide — Models, Artifacts, Fraud Detection & Customer Benefits

---

## 1. What is Day 07 in Simple Words?

Imagine you run a company that processes thousands of supplier invoices every month. 

Before Day 07, if an invoice looked suspicious, older systems would just show an error:
> ❌ **"Error: High Risk Invoice"**

This was frustrating for the billing team and tax accountants because:
1. They didn't know **why** it was risky.
2. They didn't know **how to fix it** without reading through a 1,500-page government tax book.

**Day 07 fixes this completely:**
- It uses Artificial Intelligence to explain the problem in plain English (e.g., *"You declared this as a chemical, but the description says it's steel screws"*).
- It gives a **1-Click Green Button** to fix it automatically with the legally correct code.
- It catches **Tax Fraud and Fake Invoices** before they get sent to the government tax portal.

---

## 2. How Does It Catch Fraud? (With Real-World Examples)

In GST, companies lose millions of rupees to 3 common types of tax fraud. Day 07 detects all three:

### Fraud Type 1: Tax Rate Arbitrage (Cheating on Tax Rates)
* **The Scam:** A vendor sells **High-Strength Steel Industrial Screws** (which should be taxed at **18% GST** under Chapter 73). To avoid paying tax, the vendor declares it under **Chapter 28 (Agricultural/Inorganic Chemicals)** which is taxed at only **5% GST**.
* **How Day 07 Catches It:** 
  - Day 05 NLP reads the text: *"Screws bolts nuts of iron or steel"*. It recognizes this is 100% steel fasteners (Chapter 73).
  - The Gatekeeper compares Vendor Chapter (`28`) with statutory Chapter (`73`).
  - **The System Alerts:** 
    > 🔴 *"Declared HSN belongs to Chapter 28 (Chemicals), but product text matches Chapter 73 (Iron/Steel) with 100% confidence. High risk of tax evasion."*
  - **The 1-Click Fix:** Suggests `HSN 73181300` and drops audit risk from **74% down to 4.5%**.

---

### Fraud Type 2: ITC Inflation & Under/Over-Invoicing (Fake Bill Scam)
* **The Scam:** To claim huge illegal refunds (Input Tax Credit / ITC), fraudsters generate fake invoices for cheap items at absurd prices. For example, billing a simple ₹500 metal bolt at **₹12,00,000**!
* **How Day 07 Catches It:** 
  - The system checks `artifacts/historical_median_prices.parquet`.
  - It sees the real government benchmark price for this bolt is **₹504.96**.
  - The invoice price of **₹12,00,000** is **2,376 times higher** than normal!
  - **The System Alerts:** 
    > ⚠️ *"Unit price of ₹12,00,000 deviates significantly (2376x) from statutory median benchmark (₹504.96). Marked for UNRESOLVED MANUAL AUDIT."*
  - It blocks auto-approval to prevent the company from being audited for fake bill generation.

---

### Fraud Type 3: Bogus / Fake Vendor Detection (Circular Trading)
* **The Scam:** Fraudsters create "shell companies" (fake GSTINs) that pass bad invoices and vanish after claiming money.
* **How Day 07 Catches It:** 
  - The system checks `artifacts/supplier_priors.parquet` which tracks the historical filing track record of suppliers.
  - If a supplier like `07LJKKT0958C1ZC` enters the system, it flags that this vendor has a **29.4% history of tax errors and bogus filings**.
  - If it is a completely new vendor with no past history, the **Vendor Check Toggle** gives them a fair, neutral 5% baseline so legitimate new startups are not blocked.

---

## 3. The Machine Learning Models Used (Explained Simply)

| Step | Machine Learning Model | What it Does in Plain English |
| :--- | :--- | :--- |
| **Step 1: Reading & Matching** | **Contrastive MLP Neural Network (128-D CPU)** | Acts like an expert tax lawyer who has memorized all 13,000+ government HSN codes. It reads messy product descriptions and finds the matching government codes in **2.4 milliseconds**. |
| **Step 2: Risk Scoring** | **LightGBM Decision Trees + Platt Scaling** | Evaluates 6 clues (product similarity, chapter match, price deviation, vendor history, text noise, ambiguity) and calculates the exact percentage chance of an error (e.g. *"74% Misclassification Risk"*). |
| **Step 3: Explaining Why** | **Tree SHAP (Explainable AI)** | Looks inside the decision tree and explains which clue caused the alarm. Translates mathematical logs into plain English audit reasons. |
| **Step 4: Suggesting the Fix** | **Counterfactual Simulation Engine** | Tests alternative codes in milliseconds to find the single code that drops the audit risk below the safe 5% threshold ($P(\text{Error}) < 0.05$). |

---

## 4. The Artifacts (Files) Behind the Scenes

1. **`data/tariff_master.parquet`**: The official government database containing all 8-digit HSN codes, official chapters, tax rates (0%, 5%, 12%, 18%, 28%), and blocked ITC rules.
2. **`artifacts/historical_median_prices.parquet`**: The benchmark database of real market prices for every HSN code, used to catch price fraud.
3. **`artifacts/supplier_priors.parquet`**: The compliance track record database of 250 suppliers, catching repeat offenders and shell companies.
4. **`artifacts/misclassification_lgbm.joblib`**: The trained AI brain that detects invoice errors and fraud.
5. **`artifacts/platt_calibrator.joblib`**: The calibrator that converts raw AI scores into real-world error probabilities.

---

## 5. How This Helps the Customer (The 4 Big Benefits)

1. **Stops GST Fines & Interest:**  
   Under GST Law (Section 73 & 74), using the wrong HSN code or claiming illegal ITC results in an **18% to 24% annual interest penalty**, plus heavy fines. Day 07 stops bad invoices before they are uploaded.
2. **Saves 30 Minutes per Invoice:**  
   Instead of an accountant spending 30 minutes searching through tax books, the **⚡ Apply HSN** button fixes the code and aligns the vendor chapter in **1 second**.
3. **Complete Audit Defense File:**  
   If tax officers ever question an invoice, the system has a built-in **Side Screen Drawer** that proves the company checked the official tariff master, market prices, and vendor track records before filing.
                     ---

## 6. End-to-End Integration: Module 2, E-Invoice Copilot & Data Lakehouse

### How the Complete Loop Operates:
1. **The Problem in Raw Invoices:**
   - Invoices coming from vendor ERPs often have missing, dirty, or fraudulent HSN codes (e.g. declaring steel fasteners under chemical code `2801`).
2. **AI Copilot Diagnosis & Fix (Module 2 Brain):**
   - In the **E-Invoice / Ingestion Dashboard**, the user asks the Copilot bot: *"Audit and fix HSN for product screws"*.
   - The Copilot bot calls **Module 2's HSN Intelligence & Gatekeeper Sentinel**.
   - It identifies the chapter mismatch, retrieves the official statutory code (`73181110`), and suggests the minimal corrective counterfactual.
3. **Automated Statutory Tax Recalculation:**
   - Once applied, the engine automatically calculates:
     $$\text{Gross Taxable Value} = \text{Quantity} \times \text{Rate}$$
     $$\text{CGST (9\%)} + \text{SGST (9\%)} = \text{Tax Amount}$$
     $$\text{Recalculated Line Total} = \text{Taxable Value} + \text{Tax Amount}$$
   - The overall invoice total (`totinvval`) is rebalanced.
4. **Data Lakehouse Persistence (`invoices_master.parquet`):**
   - The cleansed, verified invoice is persisted into the **Data Lakehouse** (`data/processed_payload/invoices_master.parquet`).
   - Every modification is recorded in `audit_trail.parquet`, creating an unalterable defense record for GST authorities.

