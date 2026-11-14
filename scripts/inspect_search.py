import sys, os
sys.path.insert(0, os.path.abspath("."))
from src.search.hybrid_retrieval import HybridHSNEngine
import numpy as np

engine = HybridHSNEngine()
q = 'laptop'
q_tokens = q.lower().split()
bm25_h = np.array(engine.bm25_heading.get_scores(q_tokens))
bm25_s = np.array(engine.bm25_synonyms.get_scores(q_tokens))
bm25_c = np.array(engine.bm25_chapter.get_scores(q_tokens))
bm25_sc = np.array(engine.bm25_subclause.get_scores(q_tokens))
bm25_comp = 0.35 * bm25_h + 0.25 * bm25_s + 0.15 * bm25_c + 0.25 * bm25_sc

q_emb = engine.embedding_model.encode([q], convert_to_numpy=True, normalize_embeddings=True)[0]
cos = np.dot(engine.dense_embeddings, q_emb)

top_b = np.argsort(bm25_comp)[::-1][:40]
top_v = np.argsort(cos)[::-1][:40]

rrf = {}
for r, i in enumerate(top_b):
    rrf[i] = rrf.get(i, 0.0) + (1.0 / (60.0 + r + 1))
for r, i in enumerate(top_v):
    rrf[i] = rrf.get(i, 0.0) + (1.0 / (60.0 + r + 1))

cand_idxs = sorted(rrf.keys(), key=lambda i: rrf[i], reverse=True)[:15]

pairs = []
for i in cand_idxs:
    rec = engine.records[i]
    ctx = f"{rec.get('chapter_title', '')} - {rec.get('heading_4digit_desc', '')}: {rec.get('statutory_description', '')} | {rec.get('material_keywords', '')} {rec.get('article_keywords', '')}"
    pairs.append([q, ctx])

ce_scores = engine.cross_encoder.predict(pairs)
for i, ce in zip(cand_idxs, ce_scores):
    rec = engine.records[i]
    print(rec.get('hsn_code'), rec.get('chapter_code'), 'ce_score:', round(float(ce), 3), 'cos:', round(float(cos[i]), 3), 'bm25:', round(float(bm25_comp[i]), 3), rec.get('statutory_description')[:40])
