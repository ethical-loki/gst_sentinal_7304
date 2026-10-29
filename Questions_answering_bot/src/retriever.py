import re
import sqlite3
from typing import List, NamedTuple
from config import INDEX_DB_PATH, TOP_K

STOP_WORDS = {
    "what", "when", "where", "which", "who", "whom", "whose", "why", "how",
    "a", "an", "the", "and", "or", "but", "if", "then", "else", "for", "to",
    "from", "in", "on", "at", "by", "with", "about", "as", "into", "like",
    "through", "after", "over", "between", "out", "against", "during", "without",
    "before", "under", "around", "among", "is", "am", "are", "was", "were",
    "be", "been", "being", "have", "has", "had", "do", "does", "did", "can",
    "could", "shall", "should", "will", "would", "may", "might", "must",
    "frame", "much", "many", "tell", "please"
}

class SearchResult(NamedTuple):
    chunk_id: int
    content: str
    rank: float

def clean_query(query: str) -> List[str]:
    """Strips punctuation, question marks, and conversational stop words."""
    words = re.findall(r"\b[a-zA-Z0-9_]{2,}\b", query.lower())
    filtered = [w for w in words if w not in STOP_WORDS]
    return filtered if filtered else words

def search(query: str, k: int = TOP_K) -> List[SearchResult]:
    terms = clean_query(query)
    if not terms:
        return []

    # Use OR with prefix wildcards (e.g. "irn"* OR "cancel"*)
    fts_query = " OR ".join([f'"{t}"*' for t in terms])

    if not INDEX_DB_PATH.exists():
        return []

    conn = sqlite3.connect(INDEX_DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT chunk_id, content, bm25(passages) AS rank
            FROM passages
            WHERE passages MATCH ?
            ORDER BY rank ASC
            LIMIT ?;
            """,
            (fts_query, k),
        )
        rows = cursor.fetchall()
        return [SearchResult(chunk_id=r[0], content=r[1], rank=r[2]) for r in rows]
    except sqlite3.OperationalError:
        try:
            simple_query = " OR ".join(terms)
            cursor.execute(
                """
                SELECT chunk_id, content, bm25(passages) AS rank
                FROM passages
                WHERE passages MATCH ?
                ORDER BY rank ASC
                LIMIT ?;
                """,
                (simple_query, k),
            )
            rows = cursor.fetchall()
            return [SearchResult(chunk_id=r[0], content=r[1], rank=r[2]) for r in rows]
        except Exception:
            return []
    finally:
        conn.close()