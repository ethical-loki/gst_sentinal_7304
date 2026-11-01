import sys, os
sys.path.insert(0, os.getcwd())
import numpy as np
import re
from src.nlp.hsn_intelligence import get_hsn_intelligence_engine

eng = get_hsn_intelligence_engine()
matcher = eng._matcher

def stem_word(w: str) -> str:
    w = w.lower().strip()
    if len(w) <= 3:
        return w
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith("es") and len(w) > 4 and w[-3] in "shxz":
        return w[:-2]
    if w.endswith("s") and not w.endswith("ss") and len(w) > 3:
        return w[:-1]
    return w

def stem_set(words) -> set:
    return {stem_word(w) for w in words if len(w) >= 2}

raw_q = "industrial servo motor ac"
q_matrix, _ = matcher.vectorize_batch([raw_q])
sim_matrix = matcher.compute_similarity_matrix(q_matrix)
dense_scores = sim_matrix[0]

q_tokens = set(re.findall(r"\b[a-z0-9]{2,}\b", raw_q.lower()))
lex_scores = np.zeros(matcher.catalog_size, dtype=np.float32)
if q_tokens:
    q_len = len(q_tokens)
    for c_idx, c_words in enumerate(matcher.catalog_word_sets):
        if c_words:
            overlap = len(q_tokens & c_words)
            if overlap > 0:
                lex_scores[c_idx] = overlap / q_len

combined_scores = 0.65 * dense_scores + 0.35 * lex_scores
top_indices = np.argsort(-combined_scores)[:35].tolist()
top_sims = [float(dense_scores[idx]) for idx in top_indices]
candidates = [matcher.catalog_records[idx] for idx in top_indices]

# Cross-encoder joint scoring
ce = matcher._get_cross_encoder()
clean_query = "industrial servo motor ac"
head_noun = "motor"

pairs = [
    [clean_query, str(c.get("hierarchical_text") or c.get("clean_description", c.get("description", "")))]
    for c in candidates
]
ce_logits = ce.predict(pairs)
head_pairs = [
    [head_noun, str(c.get("hierarchical_text") or c.get("clean_description", c.get("description", "")))]
    for c in candidates
]
head_logits = ce.predict(head_pairs)
# Note: how should head_logits interact with ce_logits?
# Full query ce_logits is the primary joint token interaction.
ce_probs_pure = 1.0 / (1.0 + np.exp(-(np.array(ce_logits, dtype=np.float32) + 4.5) / 1.8))
ce_logits_max = np.maximum(np.array(ce_logits, dtype=np.float32), np.array(head_logits, dtype=np.float32))
ce_probs_max = 1.0 / (1.0 + np.exp(-(ce_logits_max + 4.5) / 1.8))

bi_sims = np.array(top_sims, dtype=np.float32)
cal_bi = np.clip((bi_sims - 0.30) / (0.70 - 0.30), 0.10, 0.98)

raw_combined = 0.50 * cal_bi + 0.50 * ce_probs_pure

q_words_3 = set(re.findall(r"\b[a-z]{3,}\b", clean_query.lower()))
stemmed_q = stem_set(q_words_3)

print("With pure ce_probs (without head_logits hijacking):")
for idx in range(len(candidates)):
    c = candidates[idx]
    code = str(c.get("hsn_code"))
    if code.startswith("85015"):
        raw_dist = c.get("distinctive_tokens", "")
        if isinstance(raw_dist, (list, set)):
            dist_tokens = set(str(t).lower() for t in raw_dist)
        else:
            dist_tokens = set(str(raw_dist).lower().split())
        shares = bool(stem_set(dist_tokens) & stemmed_q)
        print(f"Code: {code} raw_combined={raw_combined[idx]:.4f} ce_pure={ce_probs_pure[idx]:.4f} ce_max={ce_probs_max[idx]:.4f} bi={cal_bi[idx]:.4f} shares={shares}")

