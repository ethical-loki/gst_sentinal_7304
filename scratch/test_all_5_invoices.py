import sys, os
sys.path.insert(0, os.path.abspath("."))
import json
from backend.ingestion_service import process_ingestion_pipeline

# Full 5 invoices payload from user
user_full_payload = {
  "einvoices": [
    {
      "self_gstin": "29AAACR4849R1ZH",
      "system cd": "ERP_SAP",
      "branch cd": "BLR-HQ",
      "vertical cd": "DOMESTIC",
      "irnreq": "Y",
      "trandt1": {
        "trancatg": "B2B",
        "reversecharge": "N",
        "transactionmode": "REG",
        "igst_on_intra": "N"
      },
      "docdt1": {
        "document_type": "INV",
        "docno": "INV-2026-001",
        "docdt": "2026-10-31"
      },
      "supplierdt1": {
        "supplier_gstin": "29AAACR4849R1ZH",
        "supplier_lginm": "  ZENITH   ENTERPRISES PVT LTD  ",
        "supplier_trdnm": "ZENITH SOLUTIONS",
        "supplier_bno": "PLOT 45",
        "supplier_bnm": "ELECTRONIC CITY PHASE 1",
        "supplier flno": "2ND FLOOR",
        "supplier_loc": "BENGALURU",
        "supplier_dst": "BENGALURU",
        "supplier_pin": "560001",
        "supplier state": "29",
        "supplier_phone": "9876543210",
        "supplier_email": "billing@zenithsolutions.com",
        "supplier_state": "29"
      },
      "buyerdt1": {
        "buyer_gstin": "27TUHCN2957U5ZN",
        "buyer_lglnm": "  MAHARASHTRA   INDUSTRIAL DISTRIBUTORS  ",
        "buyer_trdnm": "MID LOGISTICS",
        "buyer_bno": "BUILDING B-12",
        "buyer_bnm": "BKC COMPLEX BANDRA",
        "buyer_flno": "4TH FLOOR",
        "buyer loc": "MUMBAI",
        "buyer_dst": "MUMBAI",
        "buyer pin": "400001",
        "buyer state": "27",
        "pos": "27",
        "buyer_phone": "9820012345",
        "buyer_email": "accounts@midistributors.in"
      },
      "itemdtls": [
        {
          "prdnm": "COTTON-SHIRTS",
          "prddesc": "Men Casual 100% Cotton Shirt",
          "isservc": "N",
          "hsncd": "62052000",
          "qty": "200.000",
          "ugc": "nos",
          "unit_rate": "800.00",
          "grossamt": "160000.00",
          "discount": "0.00",
          "othchrg": "0.00",
          "assamt": "160000.00",
          "taxability": "TAX",
          "cgstrt": "0.00",
          "cgstamt": "0.00",
          "sgstrt": "0.00",
          "sgstamt": "0.00",
          "igstrt": "5.00",
          "igstamt": "8000.00",
          "cessrt": "0.00",
          "cessamt": "0.00",
          "statecessrt": "0.00",
          "statecessamt": "0.00",
          "totitemval": "168000.00",
          "hsn": "62052000",
          "uqc": "NOS",
          "unit": "NOS",
          "unitprice": "800.00",
          "unitrate": "800.00",
          "gstrate": "5.00",
          "igstval": "8000.00",
          "cgstval": "0.00",
          "sgstval": "0.00",
          "hsn_code": "62052000",
          "quantity": "200.000",
          "unit_price": "800.00",
          "totamt": "160000.00",
          "assval": "160000.00"
        }
      ],
      "valdt1": {
        "ttlassval": "160000,00",
        "cgstval": "0.00",
        "sgstval": "0.00",
        "igstval": "8000.00",
        "cesval": "0.00",
        "stcesval": "0.00",
        "cesnonadval": "0.00",
        "discval": "0.00",
        "totinvval": "168000.00",
        "othchrg": "0.00",
        "assval": "160000.00"
      },
      "ewbdt1": {
        "ewayreq": "Y",
        "subsupplytype": "1",
        "distance_of_transport": "250",
        "transporter_id": "27TUHCN2957U5ZN",
        "transporter_name": "VRL LOGISTICS LTD",
        "mode_of_transport": "1",
        "transport_doc_no": "",
        "transporter_doc_date": "",
        "veh_type": "R",
        "veh_number": "KA01AB1238"
      }
    },
    {
      "self_gstin": "27TUHCN2957U5ZN",
      "system_cd": "TALLY_PRIME",
      "branch_cd": "MUM-01",
      "vertical_cd": "DOMESTIC",
      "irnreq": "Y",
      "trandt1": {
        "trancatg": "B2B",
        "reversecharge": "N",
        "transactionmode": "REG",
        "igstonintra": "N"
      },
      "docdt1": {
        "document_type": "INV",
        "docno": "INV-2026-002",
        "docdt": "2026-10-31"
      },
      "supplierdt1": {
        "supplier_gstin": "27TUHCN2957U5ZN",
        "supplier_lglnm": "MAHARASHTRA INDUSTRIAL DISTRIBUTORS",
        "supplier_trdnm": "MID SOLUTIONS",
        "supplier_bno": "PLOT 88",
        "supplier_bnm": "ANDHERI MIDC TECH ZONE",
        "supplier_flno": "SUITE 101",
        "supplier_loc": "MUMBAI",
        "supplier_dst": "MUMBAI",
        "supplier_pin": "400001",
        "supplier_state": "27",
        "supplier_phone": "9820012345",
        "supplier_email": "billing@midistributors.in"
      },
      "buyerdt1": {
        "buyer_gstin": "27AAACR4849R1ZL",
        "buyer_lglnm": "PUNE ENGINEERING WORKS PVT LTD",
        "buyer_trdnm": "PEW PUNE",
        "buyer_bno": "GAT 234",
        "buyer_bnm": "CHAKAN INDUSTRIAL AREA",
        "buyer_flno": "BLDG 3",
        "buyer_loc": "PUNE",
        "buyer_dst": "PUNE",
        "buyer_pin": "411001",
        "buyer_state": "27",
        "pos": "27",
        "buyer_phone": "9765432100",
        "buyer_email": "procurement@puneengg.com"
      },
      "itemdtls": [
        {
          "prdnm": "COTTON-YARN",
          "prddesc": "Carded Weaving Yarn 30s",
          "isservc": "N",
          "hsncd": "520522",
          "qty": "100.000",
          "uqc": "KGS",
          "unitrate": "280.00",
          "grossamt": "28000,00",
          "discount": "0.00",
          "othchrg": "0.00",
          "assamt": "28000.00",
          "taxability": "TAX",
          "cgstrt": "2.50",
          "cgstamt": "700,00",
          "sgstrt": "2.50",
          "sgstamt": "700,00",
          "igstrt": "0.00",
          "igstamt": "0.00",
          "cessrt": "0.00",
          "cessamt": "0.00",
          "statecessrt": "0.00",
          "statecessamt": "0.00",
          "totitemval": "29400.00"
        },
        {
          "prdnm": "LED-DRIVER",
          "prddesc": "Constant Current Electronic Driver 40W",
          "isservc": "N",
          "hsncd": "850440",
          "qty": "50.000",
          "uqc": "NOS",
          "unitrate": "260.00",
          "grossamt": "13000.00",
          "discount": "0.00",
          "othchrg": "0.00",
          "assamt": "13000.00",
          "taxability": "TAX",
          "cgstrt": "9.00",
          "cgstamt": "1170.00",
          "sgstrt": "9.00",
          "sgstamt": "1170.00",
          "igstrt": "0.00",
          "igstamt": "0.00",
          "cessrt": "0.00",
          "cessamt": "0.00",
          "statecessrt": "0.00",
          "statecessamt": "0.00",
          "totitemval": "15340.00"
        }
      ],
      "valdt1": {
        "ttlassval": "41000.00",
        "cgstval": "1870.00",
        "sgstval": "1870.00",
        "igstval": "0.00",
        "cesval": "0.00",
        "stcesval": "0.00",
        "cesnonadval": "0.00",
        "discval": "0.00",
        "totinvval": "44741.20",
        "othchrg": "0.00"
      },
      "ewbdt1": {
        "ewayreq": "Y",
        "subsupplytype": "1",
        "distance_of_transport": "160",
        "transporter_id": "27TUHCN2957U5ZN",
        "transporter_name": "INDIAN RAILWAYS FREIGHT",
        "mode_of_transport": "2",
        "transport_doc_no": "RR-998822",
        "transporter_doc_date": "10-09-2026",
        "veh_type": "",
        "veh_number": ""
      }
    },
    {
      "self_gstin": "33AAACR4849R1ZS",
      "system_cd": "ORACLE",
      "branch_cd": "CHE-01",
      "vertical_cd": "EXPORT",
      "irnreq": "Y",
      "trandt1": {
        "trancatg": "EXP",
        "reversecharge": "N",
        "transactionmode": "SHP",
        "igstonintra": "N"
      },
      "docdt1": {
        "document_type": "INV",
        "docno": "EXP-2026-003",
        "docdt": "2026-10-31"
      },
      "supplierdt1": {
        "supplier_gstin": "33AAACR4849R1ZS",
        "supplier_lglnm": "SOUTHERN TEXTILES EXPORTS LTD",
        "supplier_trdnm": "SOUTHERN TEX",
        "supplier_bno": "MILL GATE 5",
        "supplier_bnm": "AVANASHI ROAD TEXTILE PARK",
        "supplier_flno": "GROUND FLOOR",
        "supplier_loc": "COIMBATORE",
        "supplier_dst": "COIMBATORE",
        "supplier_pin": "641001",
        "supplier_state": "33",
        "supplier_phone": "9842211223",
        "supplier_email": "export@southerntex.in"
      },
      "buyerdt1": {
        "buyer_gstin": "URP",
        "buyer_lglnm": "PACIFIC APPAREL IMPORTERS LLC",
        "buyer_trdnm": "PACIFIC APPAREL",
        "buyer_bno": "SUITE 700",
        "buyer_bnm": "MADISON AVENUE",
        "buyer_flno": "7TH FLOOR",
        "buyer_loc": "NEW YORK",
        "buyer_dst": "NEW YORK",
        "buyer_pin": "999999",
        "buyer_state": "96",
        "pos": "96",
        "buyer_phone": "",
        "buyer_email": "customs@pacificapparel.us"
      },
      "itemdtls": [
        {
          "prdnm": "STEEL-ROD",
          "prddesc": "TMT High Tensile Steel Rods",
          "isservc": "N",
          "hsncd": "720839",
          "qty": "20.000",
          "uqc": "TON",
          "unitrate": "52000.00",
          "grossamt": "1040000,00",
          "discount": "0.00",
          "othchrg": "0.00",
          "assamt": "1040000.00",
          "taxability": "TAX",
          "cgstrt": "0.00",
          "cgstamt": "0.00",
          "sgstrt": "0.00",
          "sgstamt": "0.00",
          "igstrt": "18.00",
          "igstamt": "187200,00",
          "cessrt": "0.00",
          "cessamt": "0.00",
          "statecessrt": "0.00",
          "statecessamt": "0.00",
          "totitemval": "1227200,00"
        }
      ],
      "valdt1": {
        "ttlassval": "1040000.00",
        "cgstval": "0.00",
        "sgstval": "0.00",
        "igstval": "187200.00",
        "cesval": "0.00",
        "stcesval": "0.00",
        "cesnonadval": "0.00",
        "discval": "0.00",
        "totinvval": "1227200.00",
        "othchrg": "0.00"
      },
      "expdt1": {
        "expcat": "DIR",
        "wthpay": "Y",
        "shipbno": "SB-8877661",
        "shipbdt": "25/08/2026",
        "port": "INMAA1",
        "forcur": "USD",
        "cntcode": "US"
      },
      "shipdtl": {
        "ship_gstin": "33AAACR4849R1ZS",
        "ship_lglnm": "CHENNAI PORT CONTAINER TERMINAL",
        "ship_trdnm": "CPCL TERMINAL",
        "ship_bno": "TERMINAL GATE 2",
        "ship_bnm": "PORT ACCESS COMPLEX",
        "ship_flno": "DOCK 4",
        "ship_loc": "CHENNAI",
        "ship_dst": "CHENNAI",
        "ship_pin": "600001",
        "ship_state": "33",
        "ship_phone": "9444012345",
        "ship_email": "terminal@chennaiport.gov.in"
      },
      "ewbdt1": {
        "ewayreq": "Y",
        "subsupplytype": "1",
        "distance_of_transport": "490",
        "transporter_id": "33AAACR4849R1ZS",
        "transporter_name": "COASTAL ROAD CARRIERS",
        "mode_of_transport": "1",
        "transport_doc_no": "",
        "transporter_doc_date": "",
        "veh_type": "R",
        "veh_number": "TN - 37 - CZ 9988"
      }
    },
    {
      "self_gstin": "24AAACR4849R1ZR",
      "system_cd": "SAP_S4HANA",
      "branch_cd": "AHM-02",
      "vertical_cd": "SEZ",
      "irnreq": "Y",
      "trandt1": {
        "trancatg": "SEZWP",
        "reversecharge": "N",
        "transactionmode": "REG",
        "igstonintra": "N"
      },
      "docdt1": {
        "document_type": "INV",
        "docno": "SEZ-2026-004",
        "docdt": "2026-10-31"
      },
      "supplierdt1": {
        "supplier_gstin": "24AAACR4849R1ZR",
        "supplier_lglnm": "GUJARAT POLYMERS & PACKAGING LTD",
        "supplier_trdnm": "GPP SOLUTIONS",
        "supplier_bno": "SHED 12",
        "supplier_bnm": "VATVA INDUSTRIAL ESTATE",
        "supplier_flno": "GROUND FL",
        "supplier_loc": "AHMEDABAD",
        "supplier_dst": "AHMEDABAD",
        "supplier_pin": "380001",
        "supplier_state": "24",
        "supplier_phone": "9879012345",
        "supplier_email": "accounts@gujaratpolymers.com"
      },
      "buyerdt1": {
        "buyer_gstin": "24TUHCN2957U5ZT",
        "buyer_lglnm": "KANDLA FREE TRADE APPARELS SEZ UNIT",
        "buyer_trdnm": "KFTZ APPARELS",
        "buyer_bno": "PLOT 105",
        "buyer_bnm": "SPECIAL ECONOMIC ZONE PHASE II",
        "buyer_flno": "BLDG 4",
        "buyer_loc": "GANDHIDHAM",
        "buyer_dst": "KUTCH",
        "buyer_pin": "370201",
        "buyer_state": "24",
        "pos": "24",
        "buyer_phone": "9825012345",
        "buyer_email": "commercial@kftzapparels.in"
      },
      "itemdtls": [
        {
          "prdnm": "POLY-HANGER",
          "prddesc": "Plastic Garment Hanger Grade A",
          "isservc": "N",
          "hsncd": "39269069",
          "qty": "500.000",
          "uqc": "PCS",
          "unitrate": "20.00",
          "grossamt": "10000,00",
          "discount": "0.00",
          "othchrg": "0.00",
          "assamt": "10000,00",
          "taxability": "TAX",
          "cgstrt": "0.00",
          "cgstamt": "0.00",
          "sgstrt": "0.00",
          "sgstamt": "0.00",
          "igstrt": "18.00",
          "igstamt": "1800,00",
          "cessrt": "0.00",
          "cessamt": "0.00",
          "statecessrt": "0.00",
          "statecessamt": "0.00",
          "totitemval": "11800,00"
        }
      ],
      "valdt1": {
        "ttlassval": "10000.00",
        "cgstval": "0.00",
        "sgstval": "0.00",
        "igstval": "1800.00",
        "cesval": "0.00",
        "stcesval": "0.00",
        "cesnonadval": "0.00",
        "discval": "0.00",
        "totinvval": "11800.00",
        "othchrg": "0.00"
      },
      "ewbdt1": {
        "ewayreq": "Y",
        "subsupplytype": "1",
        "distance_of_transport": "310",
        "transporter_id": "24AAACR4849R1ZR",
        "transporter_name": "WESTERN LOGISTICS CO",
        "mode_of_transport": "1",
        "transport_doc_no": "",
        "transporter_doc_date": "",
        "veh_type": "R",
        "veh_number": "GJ 01 AB 4321"
      }
    },
    {
      "self_gstin": "19AAACR4849R1ZI",
      "system_cd": "SAP_ERP",
      "branch_cd": "KOL-01",
      "vertical_cd": "METALS",
      "irnreq": "Y",
      "trandt1": {
        "trancatg": "B2B",
        "reversecharge": "N",
        "transactionmode": "REG",
        "igstonintra": "N"
      },
      "docdt1": {
        "document_type": "INV",
        "docno": "INV-2026-005",
        "docdt": "2026-10-31"
      },
      "supplierdt1": {
        "supplier_gstin": "19AAACR4849R1ZI",
        "supplier_lglnm": "EASTERN METALS & ALLOYS CORPORATION",
        "supplier_trdnm": "EASTERN METALS",
        "supplier_bno": "TOWER 4",
        "supplier_bnm": "SALT LAKE SECTOR V",
        "supplier_flno": "8TH FLOOR",
        "supplier_loc": "KOLKATA",
        "supplier_dst": "KOLKATA",
        "supplier_pin": "700001",
        "supplier_state": "19",
        "supplier_phone": "9830012345",
        "supplier_email": "sales@easternmetals.co.in"
      },
      "buyerdt1": {
        "buyer_gstin": "07TUHCN2957U5ZP",
        "buyer_lglnm": "CAPITAL CABLE & CONDUCTORS LTD",
        "buyer_trdnm": "CAPITAL CABLES",
        "buyer_bno": "PLOT 56",
        "buyer_bnm": "OKHLA INDUSTRIAL AREA PHASE III",
        "buyer_flno": "GROUND FL",
        "buyer_loc": "NEW DELHI",
        "buyer_dst": "NEW DELHI",
        "buyer_pin": "110001",
        "buyer_state": "07",
        "pos": "07",
        "buyer_phone": "9811012345",
        "buyer_email": "accounts@capitalcables.in"
      },
      "itemdtls": [
        {
          "prdnm": "ALUM-INGOT",
          "prddesc": "Primary Aluminum Ingot 99.7%",
          "isservc": "N",
          "hsncd": "760110",
          "qty": "500.000",
          "uqc": "KGS",
          "unitrate": "210.00",
          "grossamt": "105000,00",
          "discount": "0.00",
          "othchrg": "0.00",
          "assamt": "105000.00",
          "taxability": "TAX",
          "cgstrt": "0.00",
          "cgstamt": "0.00",
          "sgstrt": "0.00",
          "sgstamt": "0.00",
          "igstrt": "18.00",
          "igstamt": "18900,00",
          "cessrt": "0.00",
          "cessamt": "0.00",
          "statecessrt": "0.00",
          "statecessamt": "0.00",
          "totitemval": "123900,00"
        }
      ],
      "valdt1": {
        "ttlassval": "105000.00",
        "cgstval": "0.00",
        "sgstval": "0.00",
        "igstval": "18900.00",
        "cesval": "0.00",
        "stcesval": "0.00",
        "cesnonadval": "0.00",
        "discval": "0.00",
        "totinvval": "123900.00",
        "othchrg": "0.00"
      },
      "ewbdt1": {
        "ewayreq": "Y",
        "subsupplytype": "1",
        "distance_of_transport": "1450",
        "transporter_id": "19AAACR4849R1ZI",
        "transporter_name": "NATIONAL FREIGHT CARRIERS",
        "mode_of_transport": "1",
        "transport_doc_no": "",
        "transporter_doc_date": "",
        "veh_type": "R",
        "veh_number": "22 BH 1234 AA"
      }
    }
  ]
}

res = process_ingestion_pipeline(user_full_payload, sync_to_disk=False, persist_to_lakehouse=False)
val_rep = res.get("validation_report", {})
print(f"Total Invoices: {val_rep.get('total_invoices')}")
print(f"Valid Invoices: {val_rep.get('valid_invoices')}")
print(f"Failed Invoices: {val_rep.get('failed_invoices')}")

for idx, r in enumerate(val_rep.get("results", [])):
    inv_num = r.get("invoice_number", f"#{idx+1}")
    errs = r.get("errors", [])
    corrs = r.get("corrections_applied", [])
    print(f"\nInvoice #{idx+1} ({inv_num}) - Status: {r.get('status')} | Corrections: {len(corrs)} | Errors: {len(errs)}")
    for e in errs:
        print(f"   [Error {e.get('error_code')}] {e.get('field')}: {e.get('message')}")

