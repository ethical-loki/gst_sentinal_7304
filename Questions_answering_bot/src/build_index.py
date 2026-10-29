"""
Builds the SQLite FTS5 search index from data/content.txt.

Pipeline:
1. Extract embedded JSON samples (request/response examples, schemas) into a
   separate `json_samples` table and leave a short marker in the prose, so
   answers and passages stay readable and payloads can be shown separately.
2. Replace long encoded blobs (base64 / JWT fragments) with "[encoded-data]".
3. Split the prose into sections (a heading line followed by "Overview", or a
   "Frequently Asked Questions: <topic>" line).
4. Chunk each section into overlapping word windows (CHUNK_SIZE / CHUNK_OVERLAP).
"""
import json
import re
import sqlite3
import textwrap
from typing import Dict, Generator, List, Optional, Tuple

from config import CONTENT_PATH, INDEX_DB_PATH, CHUNK_SIZE, CHUNK_OVERLAP

MARKER_FMT = "[JSON sample #{}]"
MARKER_RE = re.compile(r"\[JSON sample #(\d+)\]")
QUOTED_STRING_RE = re.compile(r'"([^"]{120,})"')
ENCODED_TOKEN_RE = re.compile(r"[A-Za-z0-9+/=_\-]{40,}")
REPEATED_ENCODED_RE = re.compile(r"(?:\[encoded-data\][\s.]*){2,}")
FAQ_HEADING_RE = re.compile(r"^Frequently Asked Questions\s*:\s*\S", re.IGNORECASE)
MAX_JSON_BLOCK_CHARS = 60000


# ---------------------------------------------------------------------------
# JSON sample extraction
# ---------------------------------------------------------------------------

def _match_brace(text: str, start: int) -> Optional[int]:
    """Returns the index of the brace closing the one at `start`, or None."""
    depth = 0
    limit = min(len(text), start + MAX_JSON_BLOCK_CHARS)
    for i in range(start, limit):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
    return None


def _label_before(text: str, pos: int) -> str:
    """Builds a human-readable label from the prose lines preceding a JSON block."""
    window = text[max(0, pos - 300):pos]
    lines = [
        " ".join(l.split()) for l in window.splitlines()
        if l.strip() and l.strip() not in ("{", "}") and not l.strip().startswith('"')
    ]
    if not lines:
        return "JSON sample"
    if len(lines) >= 2 and len(lines[-1]) < 40:
        label = f"{lines[-2]} — {lines[-1]}"
    else:
        label = lines[-1]
    return label[-110:]


def _shorten_encoded(match: "re.Match") -> str:
    value = match.group(1)
    if value.count(" ") / max(len(value), 1) > 0.05:
        return match.group(0)  # ordinary long text, keep it
    preview = "".join(value.split())[:32]
    return f'"{preview}… [{len(value)} chars truncated]"'


def _format_json(block: str) -> Tuple[str, bool]:
    shortened = QUOTED_STRING_RE.sub(_shorten_encoded, block)
    try:
        return json.dumps(json.loads(shortened), indent=2, ensure_ascii=False), True
    except ValueError:
        lines = [l.rstrip() for l in shortened.splitlines()]
        return textwrap.dedent("\n".join(lines)).strip(), False


def extract_json_samples(text: str) -> Tuple[str, List[Dict]]:
    """Moves every balanced {...} block out of the prose and returns (prose, samples)."""
    samples: List[Dict] = []
    out: List[str] = []
    last = 0
    i = 0
    while True:
        i = text.find("{", i)
        if i == -1:
            break
        end = _match_brace(text, i)
        if end is None:
            i += 1
            continue
        block = text[i:end + 1]
        if ":" not in block or len(block) < 15:
            i = end + 1
            continue
        sample_id = len(samples) + 1
        formatted, valid = _format_json(block)
        samples.append({
            "sample_id": sample_id,
            "label": _label_before(text, i),
            "json_text": formatted,
            "valid_json": valid,
            "section": "",
        })
        out.append(text[last:i])
        out.append(f"\n{MARKER_FMT.format(sample_id)}\n")
        last = end + 1
        i = end + 1
    out.append(text[last:])
    return "".join(out), samples


def clean_prose(text: str) -> str:
    text = ENCODED_TOKEN_RE.sub("[encoded-data]", text)
    return REPEATED_ENCODED_RE.sub("[encoded-data] ", text)


# ---------------------------------------------------------------------------
# Sectioning & chunking
# ---------------------------------------------------------------------------

def split_sections(text: str) -> List[Tuple[str, str]]:
    lines = text.splitlines()
    next_nonempty: List[str] = [""] * len(lines)
    upcoming = ""
    for idx in range(len(lines) - 1, -1, -1):
        next_nonempty[idx] = upcoming
        if lines[idx].strip():
            upcoming = lines[idx].strip()

    sections: List[Tuple[str, str]] = []
    current = "General"
    buf: List[str] = []
    for idx, raw in enumerate(lines):
        line = raw.strip()
        is_heading = bool(line) and len(line) <= 80 and not MARKER_RE.fullmatch(line) and (
            next_nonempty[idx].lower() == "overview" or FAQ_HEADING_RE.match(line)
        )
        if is_heading:
            if any(b.strip() for b in buf):
                sections.append((current, "\n".join(buf)))
            current = line.rstrip(":").strip()
            buf = [line]
            continue
        buf.append(raw)
    if any(b.strip() for b in buf):
        sections.append((current, "\n".join(buf)))
    return sections


def chunk_words(words: List[str], size: int, overlap: int) -> Generator[List[str], None, None]:
    step = size - overlap
    if step <= 0:
        raise ValueError("CHUNK_SIZE must be greater than CHUNK_OVERLAP.")
    if not words:
        return
    start = 0
    while True:
        yield words[start:start + size]
        if start + size >= len(words):
            break
        start += step


# ---------------------------------------------------------------------------
# Index build
# ---------------------------------------------------------------------------

def build_fts_index() -> int:
    if not CONTENT_PATH.exists():
        raise FileNotFoundError(f"Content file not found at: {CONTENT_PATH}")

    raw = CONTENT_PATH.read_text(encoding="utf-8", errors="replace")
    prose, samples = extract_json_samples(raw)
    prose = clean_prose(prose)
    sections = split_sections(prose)

    sample_by_id = {s["sample_id"]: s for s in samples}
    rows: List[Tuple[int, str, str]] = []
    chunk_id = 0
    for title, body in sections:
        for m in MARKER_RE.finditer(body):
            sample = sample_by_id.get(int(m.group(1)))
            if sample:
                sample["section"] = title
        for words in chunk_words(body.split(), CHUNK_SIZE, CHUNK_OVERLAP):
            rows.append((chunk_id, title, " ".join(words)))
            chunk_id += 1

    INDEX_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if INDEX_DB_PATH.exists():
        INDEX_DB_PATH.unlink()

    conn = sqlite3.connect(INDEX_DB_PATH)
    try:
        conn.execute("CREATE VIRTUAL TABLE passages USING fts5(chunk_id UNINDEXED, section UNINDEXED, content);")
        conn.execute(
            "CREATE TABLE json_samples (sample_id INTEGER PRIMARY KEY, section TEXT, label TEXT, "
            "json_text TEXT, valid_json INTEGER);"
        )
        conn.executemany("INSERT INTO passages (chunk_id, section, content) VALUES (?, ?, ?);", rows)
        conn.executemany(
            "INSERT INTO json_samples (sample_id, section, label, json_text, valid_json) VALUES (?, ?, ?, ?, ?);",
            [(s["sample_id"], s["section"], s["label"], s["json_text"], int(s["valid_json"])) for s in samples],
        )
        conn.commit()
    finally:
        conn.close()

    largest = max((len(s["json_text"]) for s in samples), default=0)
    print(f"Reading from: {CONTENT_PATH}")
    print(f"Chunking with CHUNK_SIZE={CHUNK_SIZE} words, CHUNK_OVERLAP={CHUNK_OVERLAP} words")
    print(f"[OK] Sections detected: {len(sections)}")
    print(f"[OK] JSON samples extracted: {len(samples)} (largest formatted sample: {largest} chars)")
    print(f"[OK] Total chunks stored: {len(rows)}")
    print(f"[OK] Index built at: {INDEX_DB_PATH}")
    return len(rows)


if __name__ == "__main__":
    build_fts_index()