from backend.qa_service import ask_qa

cases = [
    ("What is the validity of the auth token?", 1, 0.05),
    ("What is the validity of the auth token?", 3, 0.05),
    ("How long will the Auth Token be active since the first successful login?", 3, 0.05),
    ("How long will the Auth Token be active since the first successful login?", 3, 0.60),
]
for q, k, t in cases:
    r = ask_qa(q, top_k=k, threshold=t)
    print("=" * 70, flush=True)
    print(f"Q: {q} | top_k={k} | threshold={t}", flush=True)
    print(f"  answer={r['answer']!r} score={r['score']} status={r['status']} chunk={r['chunk_id']} latency={r['latency_ms']}ms", flush=True)
    for c in r["retrieved_chunks"]:
        print(f"    chunk {c['chunk_id']}: bm25={c['bm25_score']} reader={c['reader_score']} preview={c['extracted_preview']!r}", flush=True)
