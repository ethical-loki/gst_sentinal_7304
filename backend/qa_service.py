"""
Module: backend/qa_service.py
Description: Production QA Bot integration service for GST Sentinel.
             Connects Multi-Domain RAG Chunk Retrieval and Google Flan-T5
             Seq2Seq Generative Reader with domain-isolated knowledge,
             strict extraction, and aligned developer API payloads.
"""

import sys
import time
import json
import re
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

# Root paths
BASE_DIR = Path(__file__).resolve().parent.parent
QA_BOT_DIR = BASE_DIR / "Questions_answering_bot"
QA_SRC_DIR = QA_BOT_DIR / "src"

# Ensure QA Bot src is on sys.path
if str(QA_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(QA_SRC_DIR))

_qa_engine_instance = None


def get_qa_engine():
    """Lazy-load the QAEngine instance so server startup remains instant."""
    global _qa_engine_instance
    if _qa_engine_instance is None:
        from qa_engine import QAEngine
        print("[INFO] Initializing Multi-Domain GST Sentinel QA Engine (Qwen2.5-Instruct)...")
        _qa_engine_instance = QAEngine()
        print("[OK] GST Sentinel Multi-Domain QA Engine (Qwen2.5) ready.")
    return _qa_engine_instance


get_qa_bot = get_qa_engine


DOMAIN_METADATA = {
    "e_invoice": {
        "label": "E-Invoice System",
        "description": "IRN Generation, 24-hr Cancellation, B2B/B2C Rules, Schema Validations",
        "file": "data/e_invoice_context.txt",
    },
    "eway_bill": {
        "label": "E-Way Bill System",
        "description": "Part A/B Slips, Distance Validity, Vehicle Updates, Transporter Rules",
        "file": "data/eway_bill_context.txt",
    },
    "ims": {
        "label": "Invoice Management System (IMS)",
        "description": "Recipient Actions (Accept/Reject/Pending), GSTR-2B Flow, Cut-off Timelines",
        "file": "data/ims_context.txt",
    },
}


def get_sample_questions(domain: Optional[str] = None) -> List[Dict[str, str]]:
    """Returns curated realistic statutory GST questions grouped by domain."""
    d = (domain or "e_invoice").lower()

    if "ims" in d:
        return [
            {
                "category": "IMS Actions",
                "question": "What are the three actions a recipient can take on a record in IMS?",
                "tag": "Three Actions"
            },
            {
                "category": "IMS Definition",
                "question": "What is Invoice Management System (IMS)?",
                "tag": "What is IMS"
            },
            {
                "category": "IMS Launch Date",
                "question": "When will IMS be made available to taxpayers?",
                "tag": "IMS Launch Date"
            },
            {
                "category": "GSTR-2B Flow",
                "question": "When is GSTR-2B generated based on actions taken in IMS?",
                "tag": "GSTR-2B Cut-off"
            },
            {
                "category": "Pending Restrictions",
                "question": "Are there any records where pending action is not allowed in IMS?",
                "tag": "Pending Rules"
            }
        ]
    elif "eway" in d or "ewb" in d:
        return [
            {
                "category": "Validity by Distance",
                "question": "What is the validity period of an e-way bill for regular cargo?",
                "tag": "EWB Validity"
            },
            {
                "category": "Part-A vs Part-B",
                "question": "What happens if only Transporter ID is provided in e-way bill request?",
                "tag": "Part-A Slip"
            },
            {
                "category": "Distance Rules",
                "question": "What is the allowed tolerance for PIN-to-PIN distance in e-way bill?",
                "tag": "PIN Distance Rule"
            },
            {
                "category": "Cancellation Limit",
                "question": "Within what time frame can an e-way bill be cancelled?",
                "tag": "EWB Cancellation"
            },
            {
                "category": "Vehicle Updates",
                "question": "What vehicle details are required in Part-B for road transportation?",
                "tag": "Vehicle Part-B"
            }
        ]
    else:  # e_invoice
        return [
            {
                "category": "Cancellation Timeline",
                "question": "Can a cancelled e-invoice be regenerated, and how long after generation can an IRN be cancelled?",
                "tag": "IRN Cancellation"
            },
            {
                "category": "Minimum Requirements",
                "question": "What is the minimum an e-invoice request needs to satisfy before an IRN can be generated?",
                "tag": "IRN Requirements"
            },
            {
                "category": "Auth Token Validity",
                "question": "How long is the auth token valid for?",
                "tag": "Token Validity"
            },
            {
                "category": "B2C Eligibility",
                "question": "Are B2C invoices allowed for IRN generation?",
                "tag": "B2C Exclusion"
            },
            {
                "category": "E-Way Bill Blocking",
                "question": "Can an IRN be cancelled if an active E-way bill exists for the same?",
                "tag": "E-Way Bill Clash"
            }
        ]


def extract_developer_payloads(domain: str, section_name: str, question: str) -> List[Dict[str, Any]]:
    """
    Extracts relevant statutory API request/response JSON developer payloads
    aligned with the chosen domain and query topic.
    """
    d = (domain or "e_invoice").lower()
    q_lower = (question + " " + section_name).lower()

    # 1. IMS Domain Payloads
    if "ims" in d:
        return [
            {
                "title": "IMS Inward Action Request (Taxpayer Action on Inward Invoices)",
                "type": "API Request",
                "endpoint": "POST /v1.0/ims/action",
                "json_text": json.dumps({
                    "recipient_gstin": "29AABCU9603R1ZM",
                    "action_period": "10-2024",
                    "records": [
                        {
                            "supplier_gstin": "27AAAPL1234C1ZV",
                            "doc_type": "INV",
                            "doc_num": "INV/2024/0981",
                            "doc_date": "2024-10-10",
                            "taxable_value": 250000.0,
                            "igst": 45000.0,
                            "cgst": 0.0,
                            "sgst": 0.0,
                            "action": "Accept",
                            "itc_eligibility": "Eligible"
                        }
                    ],
                    "remarks": "Invoices accepted for GSTR-2B compilation"
                }, indent=2)
            },
            {
                "title": "IMS Inward Action Response (Success)",
                "type": "API Response",
                "endpoint": "RESPONSE 200 OK",
                "json_text": json.dumps({
                    "status": 1,
                    "ack_no": "IMS-ACK-2024-889102",
                    "timestamp": "2024-10-14 11:32:00",
                    "summary": {
                        "total_records": 1,
                        "accepted": 1,
                        "rejected": 0,
                        "pending": 0
                    },
                    "message": "IMS record action updated successfully. Eligible ITC auto-drafted into GSTR-2B."
                }, indent=2)
            }
        ]

    # 2. E-Way Bill Domain Payloads
    if "eway" in d or "ewb" in d:
        return [
            {
                "title": "E-Way Bill Generation Request (Part-A & Part-B)",
                "type": "API Request",
                "endpoint": "POST /v1.03/ewayapi/genewaybill",
                "json_text": json.dumps({
                    "supplyType": "O",
                    "subSupplyType": "1",
                    "docType": "INV",
                    "docNo": "INV-2024-0012",
                    "docDate": "15/10/2024",
                    "fromGstin": "29AABCU9603R1ZM",
                    "fromTrdName": "Sentinel Logistics Corp",
                    "toGstin": "27AAAPL1234C1ZV",
                    "totalValue": 125000.0,
                    "cgstValue": 11250.0,
                    "sgstValue": 11250.0,
                    "igstValue": 0.0,
                    "transporterId": "29AAACT9876Q1Z2",
                    "transDocNo": "LR-9921",
                    "transMode": "1",
                    "distance": 185,
                    "vehicleNo": "KA01AB1234",
                    "vehicleType": "R"
                }, indent=2)
            },
            {
                "title": "E-Way Bill Generation Response (Success)",
                "type": "API Response",
                "endpoint": "RESPONSE 200 OK",
                "json_text": json.dumps({
                    "status": "1",
                    "ewayBillNo": 121008892143,
                    "ewayBillDate": "15/10/2024 14:22:00",
                    "validUpto": "16/10/2024 23:59:00",
                    "distance": 185,
                    "validityDays": 1,
                    "alert": "E-Way Bill valid for 1 day for regular cargo (up to 200 km)."
                }, indent=2)
            }
        ]

    # 3. E-Invoice Domain Payloads
    if "cancel" in q_lower:
        return [
            {
                "title": "Cancel IRN Request (Within 24 Hours)",
                "type": "API Request",
                "endpoint": "POST /api/Cancel",
                "json_text": json.dumps({
                    "Irn": "a5c12dca80e743321740b001fd70953e8738d109865d28ba4013750f2046f229",
                    "CnlRsn": "1",
                    "CnlRem": "Duplicate invoice entered by error"
                }, indent=2)
            },
            {
                "title": "Cancel IRN Response (Success)",
                "type": "API Response",
                "endpoint": "RESPONSE 200 OK",
                "json_text": json.dumps({
                    "status": "1",
                    "data": {
                        "Irn": "a5c12dca80e743321740b001fd70953e8738d109865d28ba4013750f2046f229",
                        "CancelDate": "2024-10-15 16:30:00"
                    },
                    "InfoDtls": "IRN cancelled successfully within stipulated 24-hour window."
                }, indent=2)
            }
        ]

    return [
        {
            "title": "Generate IRN Request (Payload Structure)",
            "type": "API Request",
            "endpoint": "POST /api/Invoice",
            "json_text": json.dumps({
                "Version": "1.1",
                "TranDtls": {
                    "TaxSch": "GST",
                    "SupTyp": "B2B",
                    "RegRev": "N"
                },
                "DocDtls": {
                    "Typ": "INV",
                    "No": "DOC/2024/001",
                    "Dt": "15/10/2024"
                },
                "SellerDtls": {
                    "Gstin": "29AABCU9603R1ZM",
                    "LglNm": "Sentinel Tech Pvt Ltd"
                },
                "BuyerDtls": {
                    "Gstin": "27AAAPL1234C1ZV",
                    "LglNm": "Apollo Enterprises"
                },
                "ValDtls": {
                    "TotInvVal": 118000.0,
                    "AssVal": 100000.0,
                    "IgstVal": 18000.0
                }
            }, indent=2)
        },
        {
            "title": "Generate IRN Response (Success)",
            "type": "API Response",
            "endpoint": "RESPONSE 200 OK",
            "json_text": json.dumps({
                "Status": "1",
                "Data": {
                    "AckNo": 122010045678,
                    "AckDt": "2024-10-15 10:14:00",
                    "Irn": "37f48b1d9c0201994e1d3e120894e772f8a810902893acbd894109b821948ef2",
                    "SignedInvoice": "[signed-jwt-token]",
                    "SignedQRCode": "[signed-qr-code]"
                }
            }, indent=2)
        }
    ]


def get_system_status() -> Dict[str, Any]:
    """Returns runtime telemetry for the multi-domain QA subsystem."""
    engine = get_qa_engine()
    import torch

    total_chunks = sum(len(store.chunks) for store in engine.retriever.stores.values()) if engine else 0
    has_gemini = engine.generator.gemini_client.is_available() if (engine and hasattr(engine.generator, "gemini_client")) else False

    return {
        "status": "ready",
        "offline_mode": not has_gemini,
        "llm_mode": "Google Gemini Flash (Cloud LLM)" if has_gemini else "Smart Local Synthesizer + Qwen2.5 (100% Free Offline)",
        "device": "cloud" if has_gemini else ("cuda" if torch.cuda.is_available() else "cpu"),
        "model_name": "gemini-1.5-flash" if has_gemini else (engine.generator.model_name if engine else "qwen2.5-0.5b-instruct"),
        "architecture": "Google Gemini 1.5 Flash (Cloud LLM RAG)" if has_gemini else "Multi-Domain Grounded Synthesizer + Qwen2.5-Instruct LLM (Free Local RAG)",
        "domains": DOMAIN_METADATA,
        "total_chunks": total_chunks,
        "hyperparameters": {
            "num_beams": 4,
            "min_length": 3,
            "max_new_tokens": 120,
            "score_threshold": 0.04
        }
    }


def ask_qa(
    question: str,
    domain: Optional[str] = "e_invoice",
    top_k: Optional[int] = None,
    threshold: Optional[float] = None
) -> Dict[str, Any]:
    """
    Executes domain-isolated QA retrieval and Flan-T5 generation pipeline.
    """
    from config import TOP_K, FALLBACK_RESPONSE

    t0 = time.perf_counter()
    cleaned = question.strip() if question else ""
    effective_k = int(top_k) if top_k and top_k > 0 else TOP_K

    engine = get_qa_engine()
    model_raw = engine.generator.model_name
    model_name = "Qwen2.5-0.5B-Instruct" if ("qwen" in model_raw.lower()) else model_raw
    device_name = str(engine.generator.device)
    norm_domain = engine.retriever.normalize_domain(domain)
    domain_meta = DOMAIN_METADATA.get(norm_domain, DOMAIN_METADATA["e_invoice"])

    if not cleaned:
        lat = round((time.perf_counter() - t0) * 1000, 2)
        payload = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "query": "",
            "domain": norm_domain,
            "domain_label": domain_meta["label"],
            "answer": FALLBACK_RESPONSE,
            "score": 0.0,
            "confidence_pct": "0.0%",
            "status": "empty_input",
            "latency_ms": lat,
            "model": model_name,
            "device": device_name
        }
        return {
            "question": "",
            "domain": norm_domain,
            "domain_label": domain_meta["label"],
            "answer": FALLBACK_RESPONSE,
            "score": 0.0,
            "confidence_pct": "0.0%",
            "chunk_id": None,
            "status": "empty_input",
            "reason": "Please enter a valid statutory question.",
            "latency_ms": lat,
            "payload": payload,
            "developer_payloads": [],
            "content": None,
            "retrieved_chunks": []
        }

    # Execute Domain-Isolated QA Engine
    raw_res = engine.answer_question(cleaned, domain=norm_domain, top_k=effective_k)
    lat = round((time.perf_counter() - t0) * 1000, 2)

    answer = raw_res["answer"]
    score_val = raw_res["score"]
    pct = f"{round(score_val * 100, 2)}%"
    raw_chunks = engine.retriever.retrieve(cleaned, domain=norm_domain, top_k=effective_k)

    chunks_data = []
    best_chunk = raw_chunks[0] if raw_chunks else None

    for idx, c in enumerate(raw_chunks):
        is_winner = (idx == 0 and answer != FALLBACK_RESPONSE)
        chunks_data.append({
            "chunk_id": c["chunk_id"],
            "section": c.get("section", "General"),
            "domain": c.get("domain", norm_domain),
            "bm25_score": c.get("score", 0.0),
            "snippet": (c["text"][:160] + "...") if len(c["text"]) > 160 else c["text"],
            "reader_score": c.get("score", 0.0),
            "extracted_preview": answer if is_winner else None,
            "full_content": c["text"],
            "is_selected_answer": is_winner
        })

    # Extract associated developer API payloads
    section_name = best_chunk.get("section", "General") if best_chunk else "General"
    dev_payloads = extract_developer_payloads(norm_domain, section_name, cleaned)

    # Highlight offsets
    highlight_start = None
    highlight_end = None
    if best_chunk and answer and answer != FALLBACK_RESPONSE:
        pos = best_chunk["text"].lower().find(answer.lower()[:30])
        if pos != -1:
            highlight_start = pos
            highlight_end = pos + min(len(answer), len(best_chunk["text"]) - pos)

    is_fallback = (answer == FALLBACK_RESPONSE or raw_res["status"] == "no_relevant_context")

    # Domain guidance hint for cross-domain queries
    if is_fallback and cleaned:
        q_low = cleaned.lower()
        if ("ims" in q_low or "invoice management" in q_low or "pending" in q_low) and norm_domain != "ims":
            answer = f"{FALLBACK_RESPONSE} (Note: This statutory query pertains to the Invoice Management System. Please switch to the 'Invoice Management (IMS)' tab above.)"
        elif ("e-way" in q_low or "eway" in q_low or "transporter" in q_low or "vehicle" in q_low) and norm_domain != "eway_bill":
            answer = f"{FALLBACK_RESPONSE} (Note: This statutory query pertains to the E-Way Bill System. Please switch to the 'E-Way Bill System' tab above.)"
        elif ("e-invoice" in q_low or "einvoice" in q_low or "irn" in q_low or "qr code" in q_low) and norm_domain != "e_invoice":
            answer = f"{FALLBACK_RESPONSE} (Note: This statutory query pertains to the E-Invoice System. Please switch to the 'E-Invoice System' tab above.)"

    payload = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "query": cleaned,
        "domain": norm_domain,
        "domain_label": domain_meta["label"],
        "answer": answer,
        "score": score_val,
        "confidence_pct": pct,
        "chunk_id": best_chunk["chunk_id"] if best_chunk else None,
        "section": section_name,
        "span": {
            "highlight_start": highlight_start,
            "highlight_end": highlight_end,
            "length_chars": len(answer)
        },
        "developer_payloads_available": len(dev_payloads),
        "status": "fallback" if is_fallback else "success",
        "reason": "Statutory verbatim answer extracted from domain context." if not is_fallback else FALLBACK_RESPONSE,
        "latency_ms": lat,
        "model": model_name,
        "device": device_name,
        "retrieval": {
            "domain": norm_domain,
            "top_k": effective_k,
            "chunks_found": len(raw_chunks)
        }
    }

    return {
        "question": cleaned,
        "domain": norm_domain,
        "domain_label": domain_meta["label"],
        "answer": answer,
        "score": score_val,
        "confidence_pct": pct,
        "chunk_id": best_chunk["chunk_id"] if best_chunk else None,
        "status": "fallback" if is_fallback else "success",
        "reason": answer if is_fallback else "Success",
        "latency_ms": lat,
        "payload": payload,
        "developer_payloads": dev_payloads,
        "content": {
            "chunk_id": best_chunk["chunk_id"] if best_chunk else None,
            "section": section_name,
            "text": best_chunk["text"] if best_chunk else "",
            "highlight_start": highlight_start,
            "highlight_end": highlight_end,
        } if best_chunk else None,
        "retrieved_chunks": chunks_data
    }
