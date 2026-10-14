import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Template_Converters"))

from price_anomaly_detector import PriceAnomalyDetector

test_invoice = {
    "itemdtls": [
        # Normal item
        {"prdnm": "COTTON-YARN", "hsncd": "520522", "uqc": "KGS", "unitrate": 280.0, "qty": 100, "assamt": 28000.0},
        # Extreme Over-invoicing / Decimal shift typo: Cotton yarn @ Rs 5,000/kg instead of ~280
        {"prdnm": "COTTON-YARN", "hsncd": "520522", "uqc": "KGS", "unitrate": 5000.0, "qty": 100, "assamt": 500000.0},
        # Extreme Under-invoicing: TMT Steel Rod @ Rs 10/ton instead of Rs 55,000
        {"prdnm": "STEEL-ROD", "hsncd": "720839", "uqc": "TON", "unitrate": 10.0, "qty": 50, "assamt": 500.0},
        # Decimal shift typo: LED driver @ Rs 2,600 instead of ~260 (10x)
        {"prdnm": "LED-DRIVER", "hsncd": "850440", "uqc": "NOS", "unitrate": 2600.0, "qty": 20, "assamt": 52000.0},
        # Normal Solar cable @ Rs 75/mtr
        {"prdnm": "SOLAR-CABLE", "hsncd": "854449", "uqc": "MTR", "unitrate": 75.0, "qty": 500, "assamt": 37500.0}
    ]
}

report = PriceAnomalyDetector.scan_invoice_payload(test_invoice)
print(f"Overall Status: {report['status']}")
print(f"Total Anomalies Flagged: {report['anomaly_count']} / {report['items_scanned']}")
print(f"Over-invoicing: {report['over_invoicing_count']}, Under-invoicing: {report['under_invoicing_count']}, Typos: {report['typo_count']}")
print(f"Max Risk Score: {report['max_risk_score']}/100\n")

for f in report['findings']:
    flag = "🚨 ANOMALY" if f['is_anomaly'] else "✅ OK"
    print(f"[{flag}] Item #{f['item_index']} '{f['prdnm']}': UnitRate ₹{f['unitrate']:,.2f}/{f['uqc']} (Benchmark: ₹{f['benchmark_min']}-₹{f['benchmark_max']})")
    if f['is_anomaly']:
        print(f"   -> Type: {f['anomaly_type']} | Severity: {f['severity']} | Risk Score: {f['risk_score']}")
        print(f"   -> Reason: {f['reason']}")
        if f['suggested_rate']:
            print(f"   -> Suggested Correct Rate: ₹{f['suggested_rate']:,.2f}")
        print(f"   -> Statutory Risk: {f['statutory_risk']}\n")
