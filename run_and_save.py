import urllib.request
import json

queries = ['water bottle', 'stain less steel water bottle', 'aunty', 'laptop']
lines = []
for q in queries:
    req = urllib.request.Request(
        'http://127.0.0.1:8001/api/v1/hsn-rag/step1-context-aggregator',
        data=json.dumps({'product': q}).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )
    with urllib.request.urlopen(req) as resp:
        res = json.loads(resp.read().decode('utf-8'))
        cp = res.get('chapter_prediction', {})
        dis = res.get('disambiguation', {})
        ie = res.get('intent_extraction', {})
        lines.append(f"=== QUERY: {q} ===")
        lines.append(f"Status: {cp.get('status')} | Chapter: {cp.get('chapter')} ({cp.get('chapter_title')})")
        lines.append(f"Banner: {dis.get('banner_type')}")
        if dis.get('clarification_question'):
            lines.append(f"Question: {dis.get('clarification_question')}")
        if dis.get('direct_match'):
            lines.append(f"Direct Match: {dis['direct_match']['hsn_code']} - {dis['direct_match']['label']}")
        opts = dis.get('disambiguation_options', [])
        lines.append(f"Disambiguation options count: {len(opts)}")
        for o in opts[:3]:
            lines.append(f"  -> Ch {o.get('chapter_code')}: HSN {o.get('hsn_code')} ({o.get('label')})")
        if ie:
            lines.append(f"Intent reading_confidence: {ie.get('reading_confidence')}")
            lines.append(f"Intent grounded_terms: {ie.get('grounded_search_terms')}")
            lines.append(f"Intent unstated_attributes: {ie.get('unstated_attributes')}")
        lines.append("")

with open("results.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

