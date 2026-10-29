import re
import sqlite3
from typing import List, NamedTuple, Optional
from config import INDEX_DB_PATH, TOP_K

STOP_WORDS = {
    "a", "about", "above", "across", "after", "afterwards", "again", "against", "all",
    "almost", "alone", "along", "already", "also", "although", "always", "am", "among",
    "amongst", "amount", "an", "and", "another", "any", "anyhow", "anyone", "anything",
    "anyway", "anywhere", "are", "around", "as", "at", "be", "became", "because", "become",
    "becomes", "becoming", "been", "before", "beforehand", "behind", "being", "below",
    "beside", "besides", "between", "beyond", "both", "but", "by", "can", "cannot", "could",
    "did", "do", "does", "doing", "done", "down", "due", "during", "each", "either", "else",
    "elsewhere", "enough", "etc", "even", "ever", "every", "everyone", "everything",
    "everywhere", "few", "for", "from", "further", "get", "give", "go", "had", "has",
    "have", "having", "he", "hence", "her", "here", "hereafter", "hereby", "herein",
    "hereupon", "hers", "herself", "him", "himself", "his", "how", "however", "i", "if",
    "in", "into", "is", "it", "its", "itself", "just", "me", "might", "more", "moreover",
    "most", "mostly", "much", "must", "my", "myself", "neither", "no", "nobody", "none",
    "noone", "nor", "not", "nothing", "now", "nowhere", "of", "off", "often", "on", "once",
    "only", "onto", "or", "other", "others", "otherwise", "our", "ours", "ourselves", "out",
    "over", "own", "per", "perhaps", "please", "rather", "same", "she", "should", "so",
    "some", "somehow", "someone", "something", "sometime", "sometimes", "somewhere", "still",
    "such", "than", "that", "the", "their", "theirs", "them", "themselves", "then", "thence",
    "there", "thereafter", "thereby", "therefore", "therein", "thereupon", "these", "they",
    "this", "those", "though", "through", "throughout", "thru", "thus", "to", "together",
    "too", "under", "until", "up", "upon", "us", "very", "via", "was", "we", "well", "were",
    "what", "whatever", "when", "whence", "whenever", "where", "whereafter", "whereas",
    "whereby", "wherein", "whereupon", "wherever", "whether", "which", "while", "whither",
    "who", "whoever", "whole", "whom", "whose", "why", "will", "with", "within", "without",
    "would", "yet", "you", "your", "yours", "yourself", "yourselves", "tell"
}


class SearchResult(NamedTuple):
    chunk_id: int
    section: str
    content: str
    rank: float

    @property
    def bm25_score(self) -> float:
        return round(self.rank, 4)

    @property
    def snippet(self) -> str:
        s = self.content.strip().replace("\n", " ")
        return s[:160] + "..." if len(s) > 160 else s


def clean_query(query: str) -> List[str]:
    """Extracts informative query terms, filtering punctuation and stop words."""
    words = re.findall(r"\b[a-zA-Z0-9_-]{2,}\b", query.lower())
    filtered = [w for w in words if w not in STOP_WORDS]
    return filtered if filtered else words


def search(query: str, k: int = TOP_K) -> List[SearchResult]:
    """
    Tiered BM25 search over SQLite FTS5 index:
    1. Attempts strict conjunction (AND) across all substantive query terms.
    2. Falls back to disjunction (OR) with term coverage and BM25 threshold filtering.
    3. Prevents spurious single-stopword matches from returning irrelevant passages.
    """
    terms = clean_query(query)
    if not terms or not INDEX_DB_PATH.exists():
        return []

    conn = sqlite3.connect(INDEX_DB_PATH)
    cursor = conn.cursor()
    try:
        # Tier 1: Strict AND query
        and_query = " AND ".join([f'"{t}"*' for t in terms])
        try:
            cursor.execute(
                """
                SELECT chunk_id, section, content, bm25(passages) AS rank
                FROM passages
                WHERE passages MATCH ?
                ORDER BY rank ASC
                LIMIT ?;
                """,
                (and_query, k),
            )
            rows = cursor.fetchall()
            if rows:
                return [SearchResult(chunk_id=r[0], section=r[1], content=r[2], rank=r[3]) for r in rows]
        except sqlite3.OperationalError:
            pass

        # Tier 2: Disjunction (OR) with coverage verification
        or_query = " OR ".join([f'"{t}"*' for t in terms])
        cursor.execute(
            """
            SELECT chunk_id, section, content, bm25(passages) AS rank
            FROM passages
            WHERE passages MATCH ?
            ORDER BY rank ASC
            LIMIT ?;
            """,
            (or_query, max(k * 3, 10)),
        )
        candidates = cursor.fetchall()
        if not candidates:
            return []

        filtered = []
        for r in candidates:
            chunk_id, section, content, rank = r
            # Discard near-zero BM25 ranks (spurious single noise matches)
            if rank > -0.05:
                continue

            content_lower = content.lower()
            matches = sum(1 for t in terms if t in content_lower)

            # Keyword coverage rule: For >= 3 keywords, reject if < 50% match
            if len(terms) >= 3 and (matches / len(terms)) < 0.50:
                continue

            if matches > 0:
                filtered.append((matches, r))

        # Sort by most query term hits first, then best (most negative) BM25 rank
        filtered.sort(key=lambda x: (-x[0], x[1][3]))
        return [SearchResult(chunk_id=r[0], section=r[1], content=r[2], rank=r[3]) for _, r in filtered[:k]]

    except Exception:
        return []
    finally:
        conn.close()