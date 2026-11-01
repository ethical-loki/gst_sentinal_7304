import sqlite3
from pathlib import Path

db = Path("Questions_answering_bot/data/index.db")
conn = sqlite3.connect(db)
cur = conn.cursor()
cur.execute("SELECT chunk_id, section, substr(content, 1, 100) FROM passages WHERE section LIKE '%Frequently%'")
for r in cur.fetchall():
    print(r)
conn.close()
