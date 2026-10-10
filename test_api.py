import urllib.request, json

if __name__ == "__main__":
    tests = ['live', 'chemicals', 'horse', '0101', 'bovine']
    for q in tests:
        url = f"http://127.0.0.1:8000/api/hsn-search?query={q}"
        data = json.loads(urllib.request.urlopen(url).read())
        print(f"Query [{q}]: {len(data['matches'])} results")
        if data['matches']:
            first = data['matches'][0]
            print(f"  -> First: [{first['hsn_code']}] {first['description']}")

