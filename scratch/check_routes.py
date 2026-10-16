with open('backend/main.py', 'r', encoding='utf-8') as f:
    main_code = f.read()

endpoints = [
    '/api/ingestion/chat',
    '/api/ingestion/endpoints',
    '/api/ingestion/generate',
    '/api/ingestion/persist',
    '/api/ingestion/process',
    '/api/ingestion/raw-files',
    '/api/ingestion/sample',
    '/api/ingestion/stats',
    '/api/converter/sample',
    '/api/converter/generate',
    '/api/converter/process',
    '/api/converter/chat',
    '/api/converter/endpoints'
]

for ep in endpoints:
    print(f"{ep}: {'FOUND' if ep in main_code else 'MISSING ❌'}")
