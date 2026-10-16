import os
import random
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

OUTPUT_PATH = "data/raw/operator_queries_corpus.parquet"
TARGET_PER_INTENT = 300

INTENTS = ["why_flagged", "check_hsn", "exposure_query", "vendor_status", "transit_status"]

SAMPLE_INVOICES = [f"INV-2026-B2B{i:02d}" for i in range(1, 40)]
SAMPLE_HSNS = ["84818030", "73072100", "996331", "87032100", "84713010", "39269099"]
SAMPLE_GSTINS = [
    "29ABCDE1234F1Z5", "27AABCU9603R1ZM", "24AABCB2212M1ZT",
    "06AAACT2910G1ZS", "33AABCT1330H1ZV"
]
SAMPLE_AMOUNTS = ["₹45,000", "₹1,20,000", "₹5,000", "₹18,500", "₹50,000"]

TEMPLATES = {
    "why_flagged": [
        "Why was invoice {inv} put on hold by the risk gate?",
        "Explain the statutory rule failure on {inv}",
        "Show me why {inv} has been marked with high risk",
        "What triggered the red tier flag on invoice {inv}?",
        "Why did the agent reject line item in {inv}?"
    ],
    "check_hsn": [
        "Check statutory rate and chapter for HSN {hsn}",
        "Is HSN code {hsn} eligible for full input tax credit?",
        "Verify if tariff code {hsn} matches industrial valves",
        "What is the applicable standard slab for {hsn}?",
        "Can we bill freight charges under code {hsn}?"
    ],
    "exposure_query": [
        "What is the total tax exposure for {inv}?",
        "Calculate Section 50 interest on disputed amount {amt}",
        "How much penalty is applicable under Section 122 for {inv}?",
        "Show me rupee exposure breakdown for amount {amt}",
        "What is the net revenue risk on invoice {inv}?"
    ],
    "vendor_status": [
        "Check compliance health profile for vendor {gstin}",
        "Did supplier {gstin} violate Rule 86B cash limit?",
        "Is vendor {gstin} blocked under Rule 138E non-filing?",
        "Show filing regularity and trust tier for {gstin}",
        "Verify MSME Section 43B payment due days for {gstin}"
    ],
    "transit_status": [
        "Check E-Way Bill validity and transit distance for {inv}",
        "Has vehicle on invoice {inv} encountered transit overrun?",
        "Are there any vehicle collision alerts for shipment {inv}?",
        "Show distance and route status for {inv}",
        "Verify if transit window has expired for {inv}"
    ]
}

def annotate_query(text, entities):
    tokens = text.split()
    ner_tags = ["O"] * len(tokens)
    
    for tag_type, val in entities.items():
        val_tokens = val.split()
        val_len = len(val_tokens)
        
        for i in range(len(tokens) - val_len + 1):
            window = [tokens[i + k].strip("?,.!;:\"'") for k in range(val_len)]
            target = [v.strip("?,.!;:\"'") for v in val_tokens]
            
            if window == target:
                ner_tags[i] = f"B-{tag_type}"
                for k in range(1, val_len):
                    ner_tags[i + k] = f"I-{tag_type}"
                break
                
    return tokens, ner_tags

def main():
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    random.seed(42)

    rows = []
    global_id = 1

    for intent in INTENTS:
        templates = TEMPLATES[intent]
        for _ in range(TARGET_PER_INTENT):
            tmpl = random.choice(templates)
            
            inv = random.choice(SAMPLE_INVOICES)
            hsn = random.choice(SAMPLE_HSNS)
            gstin = random.choice(SAMPLE_GSTINS)
            amt = random.choice(SAMPLE_AMOUNTS)
            
            entities = {}
            if "{inv}" in tmpl:
                entities["INVOICE_NO"] = inv
            if "{hsn}" in tmpl:
                entities["HSN_CODE"] = hsn
            if "{gstin}" in tmpl:
                entities["GSTIN"] = gstin
            if "{amt}" in tmpl:
                entities["AMOUNT"] = amt
                
            query_text = tmpl.format(inv=inv, hsn=hsn, gstin=gstin, amt=amt)
            tokens, ner_tags = annotate_query(query_text, entities)
            
            rows.append({
                "query_id": f"QRY-{global_id:05d}",
                "query_text": query_text,
                "intent": intent,
                "tokens": tokens,
                "ner_tags": ner_tags,
                "has_entities": bool(entities)
            })
            global_id += 1

    random.shuffle(rows)
    df = pd.DataFrame(rows)

    schema = pa.schema([
        ("query_id", pa.string()),
        ("query_text", pa.string()),
        ("intent", pa.string()),
        ("tokens", pa.list_(pa.string())),
        ("ner_tags", pa.list_(pa.string())),
        ("has_entities", pa.bool_())
    ])

    table = pa.Table.from_pandas(df, schema=schema)
    pq.write_table(table, OUTPUT_PATH, compression="snappy")

    print(f"successfully built {len(df)} operator query records in {OUTPUT_PATH}")
    print("intent breakdown:")
    print(df["intent"].value_counts())

if __name__ == "__main__":
    main()