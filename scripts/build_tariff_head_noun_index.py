"""
scripts/build_tariff_head_noun_index.py
=======================================
Phase 2: Build the Tariff-Derived Head-Noun and State Index from the 19,396 tariff rows.
Optimized for high-speed indexing (< 3 seconds).
"""

import sys
import os
import re
import json
import time
from pathlib import Path
from collections import defaultdict
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent

# Closed set of 98 active chapters
VALID_CHAPTERS = {f"{c:02d}" for c in range(1, 100) if c != 77}

RAW_CHAPTERS = {
    "01", "02", "03", "04", "05", "06", "07", "08", "09", "10",
    "11", "12", "13", "14", "25", "26", "27", "31", "41", "47"
}

FINISHED_ARTICLE_CHAPTERS = {
    "42", "43", "49", "61", "62", "63", "64", "65", "66", "67",
    "69", "70", "71", "73", "82", "83", "84", "85", "86", "87",
    "88", "89", "90", "91", "92", "93", "94", "95", "96", "97"
}

RAW_KEYWORDS = {
    "ingot", "ingots", "billet", "billets", "bloom", "blooms", "slab", "slabs",
    "crude", "unworked", "raw", "ore", "ores", "concentrate", "concentrates",
    "waste", "scrap", "pig iron", "sponge iron", "primary form", "primary forms",
    "powder", "powders", "granule", "granules", "rough", "unroasted", "live"
}

SEMI_FINISHED_KEYWORDS = {
    "sheet", "sheets", "plate", "plates", "strip", "strips", "coil", "coils",
    "bar", "bars", "rod", "rods", "section", "sections", "wire", "wires",
    "profile", "profiles", "foil", "foils", "flat-rolled", "yarn", "yarns",
    "fabric", "fabrics", "leather", "dressed", "sawn", "semi-finished",
    "blank", "blanks", "film", "films", "hollow profile", "hollow profiles"
}

FINISHED_KEYWORDS = {
    "flange", "flanges", "fitting", "fittings", "elbow", "elbows", "coupling", "couplings",
    "bolt", "bolts", "nut", "nuts", "screw", "screws", "washer", "washers", "rivet", "rivets",
    "valve", "valves", "pump", "pumps", "motor", "motors", "engine", "engines",
    "container", "containers", "tank", "tanks", "drum", "drums", "can", "cans", "box", "boxes",
    "machine", "machines", "appliance", "appliances", "apparatus", "device", "devices",
    "instrument", "instruments", "table", "tables", "chair", "chairs", "furniture",
    "garment", "garments", "shirt", "shirts", "t-shirt", "t-shirts", "trousers", "jacket", "jackets",
    "shoe", "shoes", "boot", "boots", "footwear", "mug", "mugs", "cup", "cups",
    "toy", "toys", "game", "games", "vehicle", "vehicles", "car", "cars", "bicycle", "bicycles"
}


def fast_determine_state(term: str, chapter: str) -> str:
    """O(1) state determination using precomputed sets."""
    t_low = term.lower()
    if t_low in RAW_KEYWORDS:
        return "raw"
    if t_low in SEMI_FINISHED_KEYWORDS:
        return "semi-finished"
    if t_low in FINISHED_KEYWORDS:
        return "finished_article"
    
    # Chapter-level fallback
    if chapter in RAW_CHAPTERS:
        return "raw"
    if chapter in ("50", "51", "52", "53", "54", "55", "72"):
        return "semi-finished"
    if chapter in FINISHED_ARTICLE_CHAPTERS:
        return "finished_article"
    
    return "finished_article"


def build_head_noun_index():
    t0 = time.perf_counter()
    parquet_path = REPO_ROOT / "data" / "tariff_master.parquet"
    if not parquet_path.exists():
        print(f"Error: {parquet_path} not found")
        return

    df = pd.read_parquet(parquet_path)
    records = df[["hsn_code", "description"]].fillna("").values.tolist()
    print(f"Loaded {len(records)} tariff rows in {time.perf_counter() - t0:.2f}s", flush=True)

    head_nouns = defaultdict(lambda: {
        "singular": "",
        "plural": "",
        "state": "unknown",
        "candidate_chapters": set(),
        "candidate_headings": set()
    })
    chapter_head_noun_counts = defaultdict(set)

    stop_words = {
        "and", "or", "of", "in", "for", "with", "without", "other", "than", "whether",
        "not", "the", "a", "an", "by", "from", "to", "at", "as", "into", "on", "up"
    }

    multi_word_phrases = [
        ("blind flange", "blind flanges", "finished_article", {"73"}),
        ("pipe fitting", "pipe fittings", "finished_article", {"73", "39", "74", "76"}),
        ("line pipe", "line pipes", "finished_article", {"73"}),
        ("ball bearing", "ball bearings", "finished_article", {"84"}),
        ("roller bearing", "roller bearings", "finished_article", {"84"}),
        ("integrated circuit", "integrated circuits", "finished_article", {"85"}),
        ("printed circuit", "printed circuits", "finished_article", {"85"}),
        ("solar cell", "solar cells", "finished_article", {"85"}),
        ("lithium-ion battery", "lithium-ion batteries", "finished_article", {"85"}),
        ("friction material", "friction materials", "semi-finished", {"68", "87"}),
        ("flat-rolled product", "flat-rolled products", "semi-finished", {"72"}),
        ("semi-finished product", "semi-finished products", "semi-finished", {"72"}),
        ("t-shirt", "t-shirts", "finished_article", {"61"}),
        ("hand tool", "hand tools", "finished_article", {"82"}),
        ("fastener", "fasteners", "finished_article", {"73"})
    ]

    # Pre-register multi-word phrases
    for sing, plur, st, chs in multi_word_phrases:
        entry = head_nouns[sing]
        entry["singular"] = sing
        entry["plural"] = plur
        entry["state"] = st
        entry["candidate_chapters"].update(chs)
        for c in chs:
            chapter_head_noun_counts[c].add(sing)

    clause_regex = re.compile(r"[:;,\-\–\—\(\)\[\]\/\\]|\b(?:and|or|for example|therefor|of|with|without)\b")
    clean_word_regex = re.compile(r"^[a-z]+$")

    for idx, (hsn_raw, desc_raw) in enumerate(records):
        clean_hsn = re.sub(r"[^\d]", "", str(hsn_raw))
        if len(clean_hsn) < 2:
            continue
        chapter = clean_hsn[:2]
        heading = clean_hsn[:4] if len(clean_hsn) >= 4 else clean_hsn
        if chapter not in VALID_CHAPTERS:
            continue

        desc_lower = str(desc_raw).lower()

        # Multi-word match
        for sing, plur, st, _ in multi_word_phrases:
            if sing in desc_lower or plur in desc_lower:
                entry = head_nouns[sing]
                entry["candidate_chapters"].add(chapter)
                entry["candidate_headings"].add(heading)
                chapter_head_noun_counts[chapter].add(sing)

        # Single word extraction from clauses (Head noun is the rightmost content word of each noun phrase)
        clauses = clause_regex.split(desc_lower)
        for clause in clauses:
            words = [w.strip() for w in clause.split() if len(w.strip()) > 2 and w.strip() not in stop_words and clean_word_regex.match(w.strip())]
            if not words:
                continue
            
            # Rightmost word in the clause is the statutory head noun
            head_w = words[-1]
            # Normalize plural
            if head_w.endswith("ies") and len(head_w) > 4:
                sing, plur = head_w[:-3] + "y", head_w
            elif head_w.endswith("es") and len(head_w) > 3 and head_w[-3] in "shxz":
                sing, plur = head_w[:-2], head_w
            elif head_w.endswith("s") and not head_w.endswith("ss") and len(head_w) > 3:
                sing, plur = head_w[:-1], head_w
            else:
                sing, plur = head_w, head_w + "s"

            st = fast_determine_state(sing, chapter)
            entry = head_nouns[sing]
            entry["singular"] = sing
            entry["plural"] = plur
            entry["state"] = st
            entry["candidate_chapters"].add(chapter)
            entry["candidate_headings"].add(heading)
            chapter_head_noun_counts[chapter].add(sing)

    print(f"Indexed {len(head_nouns)} terms in {time.perf_counter() - t0:.2f}s", flush=True)

    # Serialize
    serialized_index = {}
    for term, data in sorted(head_nouns.items()):
        if len(data["candidate_headings"]) >= 1 or len(data["candidate_chapters"]) >= 1:
            serialized_index[term] = {
                "singular": data["singular"],
                "plural": data["plural"],
                "state": data["state"],
                "candidate_chapters": sorted(list(data["candidate_chapters"])),
                "candidate_headings": sorted(list(data["candidate_headings"]))
            }

    out_file = REPO_ROOT / "data" / "tariff_head_noun_index.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(serialized_index, f, indent=2)
    print(f"[OK] Saved tariff head noun index to {out_file.name} ({len(serialized_index)} terms).", flush=True)

    # Coverage Audit
    print("\n" + "="*60, flush=True)
    print("📋 CHAPTER COVERAGE AUDIT (98 CLOSED CHAPTERS)", flush=True)
    print("="*60, flush=True)
    zero_coverage = [c for c in sorted(VALID_CHAPTERS) if len(chapter_head_noun_counts.get(c, set())) == 0]
    low_coverage = [(c, len(chapter_head_noun_counts.get(c, set()))) for c in sorted(VALID_CHAPTERS) if 0 < len(chapter_head_noun_counts.get(c, set())) < 5]

    print(f"Total Active Chapters Audited: {len(VALID_CHAPTERS)} (01–99, excl 77)", flush=True)
    print(f"Chapters with Good Coverage (>= 5 head nouns): {len(VALID_CHAPTERS) - len(zero_coverage) - len(low_coverage)}", flush=True)
    print(f"Chapters with Low Coverage (< 5 head nouns):   {len(low_coverage)}", flush=True)
    print(f"Chapters with Zero Coverage:                   {len(zero_coverage)}", flush=True)
    print("="*60, flush=True)


if __name__ == "__main__":
    build_head_noun_index()
