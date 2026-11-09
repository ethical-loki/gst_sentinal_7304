import urllib.request
import json

def test(p):
    req = urllib.request.Request(
        'http://127.0.0.1:8000/api/v1/hsn-rag/step1-context-aggregator',
        data=json.dumps({'product': p}).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )
    with urllib.request.urlopen(req) as resp:
        res = json.loads(resp.read().decode('utf-8'))
        facts = res.get('query_facts', {})
        pred = res.get('chapter_prediction', {})
        print(f"Product: {p}")
        print(f"  Cleaned:               {pred.get('normalized')}")
        print(f"  Article Noun:          {facts.get('article_noun')}")
        print(f"  Constituent Material:  {facts.get('constituent_material')}")
        print(f"  Commodity Form:        {facts.get('commodity_form')}")
        print(f"  Chapter:               {pred.get('chapter')} - {pred.get('chapter_title')}")
        print(f"  Status:                {pred.get('status')} (Confidence: {pred.get('confidence')})")
        print(f"  Catalogue Version:     {res.get('catalogue_version')}")
        print(f"  Active Chapters Count: {pred.get('total_active_chapters')}")
        print(f"  Supporting Tariff Lines ({len(pred.get('evidence', []))}):")
        for ev in pred.get('evidence', [])[:2]:
            print(f"    * HSN {ev.get('hsn_code')}: {ev.get('description')} (Score: {ev.get('score')})")
        print("-" * 65)

test('Harry Potter Gryffindor Crest Heat-Changing Ceramic Mug')
test('Seamless Stainless Steel Line Pipe for Oil & Gas')
test('xyz unbranded assorted lot 500 pcs miscellaneous')

