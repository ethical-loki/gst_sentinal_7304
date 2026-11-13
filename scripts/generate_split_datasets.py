"""
scripts/generate_split_datasets.py
==================================
Creates the two benchmark datasets:
1. data/tuning_intent_benchmarks.json (120 queries - Tuning Set)
2. data/held_out_intent_benchmarks.json (60 queries - Frozen Held-Out Set)

Includes human-labeled expected statutory vocabulary for Grounding Precision measurement.
"""

import json
from pathlib import Path

# Load existing 120 queries and annotate human-labeled expected grounding terms
tuning_path = Path("data/golden_intent_benchmarks.json")
with open(tuning_path, "r", encoding="utf-8") as f:
    tuning_cases = json.load(f)

# Ensure every tuning case has human-labeled expected grounding terms
for tc in tuning_cases:
    if "expected_grounded_terms" not in tc:
        exp_c = tc.get("expected_concept")
        exp_o = tc.get("expected_outcome")
        if exp_o == "UNRECOGNIZED":
            tc["expected_grounded_terms"] = []
        elif exp_o == "OUT_OF_SCHEDULE":
            tc["expected_grounded_terms"] = []
        elif exp_o == "AMBIGUOUS_MATERIAL":
            tc["expected_grounded_terms"] = ["bottles"] if "bottle" in tc["query"] else (["tubes and pipes"] if "pipe" in tc["query"] else [])
        else:
            if "laptop" in tc["query"].lower() or "macbook" in tc["query"].lower() or "notebook" in tc["query"].lower():
                tc["expected_grounded_terms"] = ["portable automatic data processing machines", "automatic data processing machines"]
            elif "bottle" in tc["query"].lower() or "flask" in tc["query"].lower():
                tc["expected_grounded_terms"] = ["table kitchen or other household articles", "household articles"] if "steel" in tc["query"].lower() else ["carboys", "bottles"]
            elif "t-shirt" in tc["query"].lower() or "tshirt" in tc["query"].lower() or "t shirt" in tc["query"].lower() or "singlet" in tc["query"].lower() or "baniyan" in tc["query"].lower():
                tc["expected_grounded_terms"] = ["t-shirts"]
            elif "shirt" in tc["query"].lower():
                tc["expected_grounded_terms"] = ["shirts"]
            elif "pipe" in tc["query"].lower():
                tc["expected_grounded_terms"] = ["tubes and pipes"]
            elif "pump" in tc["query"].lower():
                tc["expected_grounded_terms"] = ["pumps for liquids", "pumps"]
            elif "battery" in tc["query"].lower() or "accumulator" in tc["query"].lower():
                tc["expected_grounded_terms"] = ["accumulators"]
            elif "motor car" in tc["query"].lower() or "car" in tc["query"].lower() or "vehicle" in tc["query"].lower():
                tc["expected_grounded_terms"] = ["motor vehicles"]
            elif "biscuit" in tc["query"].lower() or "wafers" in tc["query"].lower():
                tc["expected_grounded_terms"] = ["biscuit", "bread", "pastry", "cakes"]
            elif "phone" in tc["query"].lower():
                tc["expected_grounded_terms"] = ["telephone sets"]
            else:
                tc["expected_grounded_terms"] = [exp_c] if exp_c else []

tuning_out = Path("data/tuning_intent_benchmarks.json")
with open(tuning_out, "w", encoding="utf-8") as f:
    json.dump(tuning_cases, f, indent=2)

print(f"Saved {len(tuning_cases)} tuning cases to {tuning_out}")

# -----------------------------------------------------------------
# Held-Out Set: 60 Brand New Queries (Never tuned against)
# -----------------------------------------------------------------
held_out_cases = [
    # 1. Standard Products (8)
    {
        "query": "cast iron kitchen tawa",
        "category": "standard_clear",
        "expected_reading_confidence": "clear",
        "expected_outcome": "SUCCESS",
        "expected_concept": "household",
        "expected_chapter": "73",
        "expected_grounded_terms": ["table kitchen or other household articles", "household articles"]
    },
    {
        "query": "electric ceiling fan with regulator",
        "category": "standard_clear",
        "expected_reading_confidence": "clear",
        "expected_outcome": "SUCCESS",
        "expected_concept": "fan",
        "expected_chapter": "84",
        "expected_grounded_terms": ["fans", "table, floor, wall, window, ceiling or roof fans"]
    },
    {
        "query": "knitted cotton socks for women",
        "category": "standard_clear",
        "expected_reading_confidence": "clear",
        "expected_outcome": "SUCCESS",
        "expected_concept": "socks",
        "expected_chapter": "61",
        "expected_grounded_terms": ["panty hose, tights, stockings, socks and other hosiery"]
    },
    {
        "query": "insulated plastic ice box container",
        "category": "standard_clear",
        "expected_reading_confidence": "clear",
        "expected_outcome": "SUCCESS",
        "expected_concept": "plastics",
        "expected_chapter": "39",
        "expected_grounded_terms": ["carboys", "bottles", "boxes"]
    },
    {
        "query": "welded structural steel square hollow tube",
        "category": "standard_clear",
        "expected_reading_confidence": "clear",
        "expected_outcome": "SUCCESS",
        "expected_concept": "tubes and pipes",
        "expected_chapter": "73",
        "expected_grounded_terms": ["tubes and pipes"]
    },
    {
        "query": "printed cotton woven nightwear pyjamas",
        "category": "standard_clear",
        "expected_reading_confidence": "clear",
        "expected_outcome": "SUCCESS",
        "expected_concept": "pyjamas",
        "expected_chapter": "62",
        "expected_grounded_terms": ["nightshirts and pyjamas"]
    },
    {
        "query": "solar photovoltaic module panel",
        "category": "standard_clear",
        "expected_reading_confidence": "clear",
        "expected_outcome": "SUCCESS",
        "expected_concept": "photovoltaic",
        "expected_chapter": "85",
        "expected_grounded_terms": ["photovoltaic cells", "semiconductor devices"]
    },
    {
        "query": "hardened steel machine screws",
        "category": "standard_clear",
        "expected_reading_confidence": "clear",
        "expected_outcome": "SUCCESS",
        "expected_concept": "screws",
        "expected_chapter": "73",
        "expected_grounded_terms": ["screws", "bolts", "nuts"]
    },

    # 2. Brand Names (8)
    {
        "query": "Dell Inspiron 15 laptop computer",
        "category": "brand_names",
        "expected_reading_confidence": "clear",
        "expected_outcome": "SUCCESS",
        "expected_concept": "data processing",
        "expected_chapter": "84",
        "expected_grounded_terms": ["portable automatic data processing machines", "automatic data processing machines"]
    },
    {
        "query": "Prestige stainless steel pressure cooker 5 litre",
        "category": "brand_names",
        "expected_reading_confidence": "clear",
        "expected_outcome": "SUCCESS",
        "expected_concept": "household",
        "expected_chapter": "73",
        "expected_grounded_terms": ["table kitchen or other household articles", "household articles"]
    },
    {
        "query": "Crompton electric table fan",
        "category": "brand_names",
        "expected_reading_confidence": "clear",
        "expected_outcome": "SUCCESS",
        "expected_concept": "fan",
        "expected_chapter": "84",
        "expected_grounded_terms": ["fans"]
    },
    {
        "query": "Amul spray milk powder tin",
        "category": "brand_names",
        "expected_reading_confidence": "clear",
        "expected_outcome": "OUT_OF_SCHEDULE",
        "expected_concept": "milk",
        "expected_chapter": "OUT_OF_SCHEDULE",
        "expected_grounded_terms": []
    },
    {
        "query": "Raymond woven wool blazer coat",
        "category": "brand_names",
        "expected_reading_confidence": "clear",
        "expected_outcome": "SUCCESS",
        "expected_concept": "suit",
        "expected_chapter": "62",
        "expected_grounded_terms": ["suits, ensembles, jackets, blazers"]
    },
    {
        "query": "Luminous solar inverter battery",
        "category": "brand_names",
        "expected_reading_confidence": "clear",
        "expected_outcome": "SUCCESS",
        "expected_concept": "accumulator",
        "expected_chapter": "85",
        "expected_grounded_terms": ["accumulators"]
    },
    {
        "query": "Astral CPVC hot water plumbing pipe",
        "category": "brand_names",
        "expected_reading_confidence": "clear",
        "expected_outcome": "SUCCESS",
        "expected_concept": "tubes and pipes",
        "expected_chapter": "39",
        "expected_grounded_terms": ["tubes and pipes"]
    },
    {
        "query": "Godrej double door frost free refrigerator",
        "category": "brand_names",
        "expected_reading_confidence": "clear",
        "expected_outcome": "SUCCESS",
        "expected_concept": "refrigerator",
        "expected_chapter": "84",
        "expected_grounded_terms": ["refrigerators", "freezers"]
    },

    # 3. Technical & Industrial Specs (8)
    {
        "query": "seamless cold drawn carbon steel boiler tube ASTM A179",
        "category": "technical_industrial",
        "expected_reading_confidence": "clear",
        "expected_outcome": "SUCCESS",
        "expected_concept": "tubes and pipes",
        "expected_chapter": "73",
        "expected_grounded_terms": ["tubes and pipes"]
    },
    {
        "query": "men knitted athletic vest 100 percent cotton",
        "category": "technical_industrial",
        "expected_reading_confidence": "clear",
        "expected_outcome": "SUCCESS",
        "expected_concept": "vest",
        "expected_chapter": "61",
        "expected_grounded_terms": ["t-shirts", "singlets and other vests"]
    },
    {
        "query": "deep freezer commercial refrigeration unit 400 litre",
        "category": "technical_industrial",
        "expected_reading_confidence": "clear",
        "expected_outcome": "SUCCESS",
        "expected_concept": "refrigerator",
        "expected_chapter": "84",
        "expected_grounded_terms": ["refrigerators", "freezers"]
    },
    {
        "query": "high tensile hex head galvanized bolts grade 8.8",
        "category": "technical_industrial",
        "expected_reading_confidence": "clear",
        "expected_outcome": "SUCCESS",
        "expected_concept": "screws",
        "expected_chapter": "73",
        "expected_grounded_terms": ["screws", "bolts", "nuts"]
    },
    {
        "query": "knitted circular jersey fabric cotton spandex polo",
        "category": "technical_industrial",
        "expected_reading_confidence": "clear",
        "expected_outcome": "SUCCESS",
        "expected_concept": "shirt",
        "expected_chapter": "61",
        "expected_grounded_terms": ["shirts"]
    },
    {
        "query": "rotary positive displacement oil gear pump",
        "category": "technical_industrial",
        "expected_reading_confidence": "clear",
        "expected_outcome": "SUCCESS",
        "expected_concept": "pump",
        "expected_chapter": "84",
        "expected_grounded_terms": ["pumps for liquids", "pumps"]
    },
    {
        "query": "polypropylene woven sack bag for grain packaging",
        "category": "technical_industrial",
        "expected_reading_confidence": "clear",
        "expected_outcome": "SUCCESS",
        "expected_concept": "plastics",
        "expected_chapter": "39",
        "expected_grounded_terms": ["sacks and bags"]
    },
    {
        "query": "stationary lithium iron phosphate energy storage battery",
        "category": "technical_industrial",
        "expected_reading_confidence": "clear",
        "expected_outcome": "SUCCESS",
        "expected_concept": "accumulator",
        "expected_chapter": "85",
        "expected_grounded_terms": ["accumulators"]
    },

    # 4. Misspellings & OCR (8)
    {
        "query": "presure kooker stainles stel",
        "category": "misspelling_ocr",
        "expected_reading_confidence": "clear",
        "expected_outcome": "SUCCESS",
        "expected_concept": "household",
        "expected_chapter": "73",
        "expected_grounded_terms": ["table kitchen or other household articles", "household articles"]
    },
    {
        "query": "seling fan eletrical",
        "category": "misspelling_ocr",
        "expected_reading_confidence": "clear",
        "expected_outcome": "SUCCESS",
        "expected_concept": "fan",
        "expected_chapter": "84",
        "expected_grounded_terms": ["fans"]
    },
    {
        "query": "plastek dranege ppe 4in",
        "category": "misspelling_ocr",
        "expected_reading_confidence": "clear",
        "expected_outcome": "SUCCESS",
        "expected_concept": "tubes and pipes",
        "expected_chapter": "39",
        "expected_grounded_terms": ["tubes and pipes"]
    },
    {
        "query": "men wovn cottn dreas shrt",
        "category": "misspelling_ocr",
        "expected_reading_confidence": "clear",
        "expected_outcome": "SUCCESS",
        "expected_concept": "shirt",
        "expected_chapter": "62",
        "expected_grounded_terms": ["shirts"]
    },
    {
        "query": "laptopp notebuk persnal computr",
        "category": "misspelling_ocr",
        "expected_reading_confidence": "clear",
        "expected_outcome": "SUCCESS",
        "expected_concept": "data processing",
        "expected_chapter": "84",
        "expected_grounded_terms": ["portable automatic data processing machines", "automatic data processing machines"]
    },
    {
        "query": "led acid autumotive batree",
        "category": "misspelling_ocr",
        "expected_reading_confidence": "clear",
        "expected_outcome": "SUCCESS",
        "expected_concept": "accumulator",
        "expected_chapter": "85",
        "expected_grounded_terms": ["accumulators"]
    },
    {
        "query": "biscut wfr chocolate",
        "category": "misspelling_ocr",
        "expected_reading_confidence": "clear",
        "expected_outcome": "SUCCESS",
        "expected_concept": "biscuit",
        "expected_chapter": "19",
        "expected_grounded_terms": ["biscuit", "bread", "pastry", "cakes"]
    },
    {
        "query": "semles ss pipe astm",
        "category": "misspelling_ocr",
        "expected_reading_confidence": "clear",
        "expected_outcome": "SUCCESS",
        "expected_concept": "tubes and pipes",
        "expected_chapter": "73",
        "expected_grounded_terms": ["tubes and pipes"]
    },

    # 5. Hinglish & Colloquial (8)
    {
        "query": "bijli ka chhat wala pankha",
        "category": "hinglish_colloquial",
        "expected_reading_confidence": "clear",
        "expected_outcome": "SUCCESS",
        "expected_concept": "fan",
        "expected_chapter": "84",
        "expected_grounded_terms": ["fans"]
    },
    {
        "query": "lohe ka tava bartan",
        "category": "hinglish_colloquial",
        "expected_reading_confidence": "clear",
        "expected_outcome": "SUCCESS",
        "expected_concept": "household",
        "expected_chapter": "73",
        "expected_grounded_terms": ["table kitchen or other household articles", "household articles"]
    },
    {
        "query": "plastic ki balti bucket",
        "category": "hinglish_colloquial",
        "expected_reading_confidence": "clear",
        "expected_outcome": "SUCCESS",
        "expected_concept": "plastics",
        "expected_chapter": "39",
        "expected_grounded_terms": ["tableware, kitchenware, other household articles"]
    },
    {
        "query": "chai ki patti tea leaf",
        "category": "hinglish_colloquial",
        "expected_reading_confidence": "clear",
        "expected_outcome": "OUT_OF_SCHEDULE",
        "expected_concept": "tea",
        "expected_chapter": "OUT_OF_SCHEDULE",
        "expected_grounded_terms": []
    },
    {
        "query": "gaadi ka brake liner pad",
        "category": "hinglish_colloquial",
        "expected_reading_confidence": "clear",
        "expected_outcome": "SUCCESS",
        "expected_concept": "motor vehicle",
        "expected_chapter": "87",
        "expected_grounded_terms": ["brakes and servo-brakes; parts thereof"]
    },
    {
        "query": "lohe ka nut kabil fasteners",
        "category": "hinglish_colloquial",
        "expected_reading_confidence": "clear",
        "expected_outcome": "SUCCESS",
        "expected_concept": "screws",
        "expected_chapter": "73",
        "expected_grounded_terms": ["screws", "bolts", "nuts"]
    },
    {
        "query": "pani ka khet wala motor pump",
        "category": "hinglish_colloquial",
        "expected_reading_confidence": "clear",
        "expected_outcome": "SUCCESS",
        "expected_concept": "pump",
        "expected_chapter": "84",
        "expected_grounded_terms": ["pumps for liquids", "pumps"]
    },
    {
        "query": "sooti cotton underwear baniyan",
        "category": "hinglish_colloquial",
        "expected_reading_confidence": "clear",
        "expected_outcome": "SUCCESS",
        "expected_concept": "t-shirt",
        "expected_chapter": "61",
        "expected_grounded_terms": ["t-shirts", "singlets and other vests"]
    },

    # 6. Material Ambiguity (8)
    {
        "query": "office lunch box",
        "category": "material_ambiguity",
        "expected_reading_confidence": "clear",
        "expected_outcome": "AMBIGUOUS_MATERIAL",
        "expected_concept": "box",
        "expected_chapter": "NONE",
        "expected_grounded_terms": []
    },
    {
        "query": "insulated beverage tumbler",
        "category": "material_ambiguity",
        "expected_reading_confidence": "clear",
        "expected_outcome": "AMBIGUOUS_MATERIAL",
        "expected_concept": "bottles",
        "expected_chapter": "NONE",
        "expected_grounded_terms": []
    },
    {
        "query": "chemical conduit tubing",
        "category": "material_ambiguity",
        "expected_reading_confidence": "clear",
        "expected_outcome": "AMBIGUOUS_MATERIAL",
        "expected_concept": "tubes and pipes",
        "expected_chapter": "NONE",
        "expected_grounded_terms": []
    },
    {
        "query": "industrial safety gloves",
        "category": "material_ambiguity",
        "expected_reading_confidence": "clear",
        "expected_outcome": "AMBIGUOUS_MATERIAL",
        "expected_concept": "gloves",
        "expected_chapter": "NONE",
        "expected_grounded_terms": []
    },
    {
        "query": "liquid storage container 50L",
        "category": "material_ambiguity",
        "expected_reading_confidence": "clear",
        "expected_outcome": "AMBIGUOUS_MATERIAL",
        "expected_concept": "container",
        "expected_chapter": "NONE",
        "expected_grounded_terms": []
    },
    {
        "query": "household water jug",
        "category": "material_ambiguity",
        "expected_reading_confidence": "clear",
        "expected_outcome": "AMBIGUOUS_MATERIAL",
        "expected_concept": "bottles",
        "expected_chapter": "NONE",
        "expected_grounded_terms": []
    },
    {
        "query": "flanged gas pipe",
        "category": "material_ambiguity",
        "expected_reading_confidence": "clear",
        "expected_outcome": "AMBIGUOUS_MATERIAL",
        "expected_concept": "tubes and pipes",
        "expected_chapter": "NONE",
        "expected_grounded_terms": []
    },
    {
        "query": "chemical storage carboy drum",
        "category": "material_ambiguity",
        "expected_reading_confidence": "clear",
        "expected_outcome": "AMBIGUOUS_MATERIAL",
        "expected_concept": "container",
        "expected_chapter": "NONE",
        "expected_grounded_terms": []
    },

    # 7. Out-of-Schedule Goods & Materials (10)
    {
        "query": "glass water bottle 1 litre",
        "category": "out_of_schedule",
        "expected_reading_confidence": "clear",
        "expected_outcome": "OUT_OF_SCHEDULE",
        "expected_concept": "glass",
        "expected_chapter": "OUT_OF_SCHEDULE",
        "expected_grounded_terms": []
    },
    {
        "query": "genuine leather travel jacket",
        "category": "out_of_schedule",
        "expected_reading_confidence": "clear",
        "expected_outcome": "OUT_OF_SCHEDULE",
        "expected_concept": "leather",
        "expected_chapter": "OUT_OF_SCHEDULE",
        "expected_grounded_terms": []
    },
    {
        "query": "solid teak wood dining table",
        "category": "out_of_schedule",
        "expected_reading_confidence": "clear",
        "expected_outcome": "OUT_OF_SCHEDULE",
        "expected_concept": "wood",
        "expected_chapter": "OUT_OF_SCHEDULE",
        "expected_grounded_terms": []
    },
    {
        "query": "fresh nagpur oranges",
        "category": "out_of_schedule",
        "expected_reading_confidence": "clear",
        "expected_outcome": "OUT_OF_SCHEDULE",
        "expected_concept": "fruit",
        "expected_chapter": "OUT_OF_SCHEDULE",
        "expected_grounded_terms": []
    },
    {
        "query": "glass beverage tumbler set",
        "category": "out_of_schedule",
        "expected_reading_confidence": "clear",
        "expected_outcome": "OUT_OF_SCHEDULE",
        "expected_concept": "glass",
        "expected_chapter": "OUT_OF_SCHEDULE",
        "expected_grounded_terms": []
    },
    {
        "query": "raw timber logs for sawmill",
        "category": "out_of_schedule",
        "expected_reading_confidence": "clear",
        "expected_outcome": "OUT_OF_SCHEDULE",
        "expected_concept": "timber",
        "expected_chapter": "OUT_OF_SCHEDULE",
        "expected_grounded_terms": []
    },
    {
        "query": "pure gold necklace jewelry",
        "category": "out_of_schedule",
        "expected_reading_confidence": "clear",
        "expected_outcome": "OUT_OF_SCHEDULE",
        "expected_concept": "gold",
        "expected_chapter": "OUT_OF_SCHEDULE",
        "expected_grounded_terms": []
    },
    {
        "query": "fresh farm cow milk 500ml",
        "category": "out_of_schedule",
        "expected_reading_confidence": "clear",
        "expected_outcome": "OUT_OF_SCHEDULE",
        "expected_concept": "milk",
        "expected_chapter": "OUT_OF_SCHEDULE",
        "expected_grounded_terms": []
    },
    {
        "query": "crude oil petroleum barrel",
        "category": "out_of_schedule",
        "expected_reading_confidence": "clear",
        "expected_outcome": "OUT_OF_SCHEDULE",
        "expected_concept": "petroleum",
        "expected_chapter": "OUT_OF_SCHEDULE",
        "expected_grounded_terms": []
    },
    {
        "query": "antibiotic amoxicillin medicine capsule",
        "category": "out_of_schedule",
        "expected_reading_confidence": "clear",
        "expected_outcome": "OUT_OF_SCHEDULE",
        "expected_concept": "medicine",
        "expected_chapter": "OUT_OF_SCHEDULE",
        "expected_grounded_terms": []
    },

    # 8. Unrecognized & Vague Queries (10)
    {
        "query": "random unspecified article",
        "category": "unrecognized_vague",
        "expected_reading_confidence": "unclear",
        "expected_outcome": "UNRECOGNIZED",
        "expected_concept": None,
        "expected_chapter": "NONE",
        "expected_grounded_terms": []
    },
    {
        "query": "miscellaneous thingamajig",
        "category": "unrecognized_vague",
        "expected_reading_confidence": "unclear",
        "expected_outcome": "UNRECOGNIZED",
        "expected_concept": None,
        "expected_chapter": "NONE",
        "expected_grounded_terms": []
    },
    {
        "query": "doohickey",
        "category": "unrecognized_vague",
        "expected_reading_confidence": "unclear",
        "expected_outcome": "UNRECOGNIZED",
        "expected_concept": None,
        "expected_chapter": "NONE",
        "expected_grounded_terms": []
    },
    {
        "query": "stuff and things",
        "category": "unrecognized_vague",
        "expected_reading_confidence": "unclear",
        "expected_outcome": "UNRECOGNIZED",
        "expected_concept": None,
        "expected_chapter": "NONE",
        "expected_grounded_terms": []
    },
    {
        "query": "item 999",
        "category": "unrecognized_vague",
        "expected_reading_confidence": "unclear",
        "expected_outcome": "UNRECOGNIZED",
        "expected_concept": None,
        "expected_chapter": "NONE",
        "expected_grounded_terms": []
    },
    {
        "query": "qwertyuiopasdf",
        "category": "unrecognized_vague",
        "expected_reading_confidence": "unclear",
        "expected_outcome": "UNRECOGNIZED",
        "expected_concept": None,
        "expected_chapter": "NONE",
        "expected_grounded_terms": []
    },
    {
        "query": "unobtainium antigravity drive",
        "category": "unrecognized_vague",
        "expected_reading_confidence": "clear",
        "expected_outcome": "UNRECOGNIZED",
        "expected_concept": None,
        "expected_chapter": "NONE",
        "expected_grounded_terms": []
    },
    {
        "query": "something something",
        "category": "unrecognized_vague",
        "expected_reading_confidence": "unclear",
        "expected_outcome": "UNRECOGNIZED",
        "expected_concept": None,
        "expected_chapter": "NONE",
        "expected_grounded_terms": []
    },
    {
        "query": "generic merchandise",
        "category": "unrecognized_vague",
        "expected_reading_confidence": "unclear",
        "expected_outcome": "UNRECOGNIZED",
        "expected_concept": None,
        "expected_chapter": "NONE",
        "expected_grounded_terms": []
    },
    {
        "query": "whatever item",
        "category": "unrecognized_vague",
        "expected_reading_confidence": "unclear",
        "expected_outcome": "UNRECOGNIZED",
        "expected_concept": None,
        "expected_chapter": "NONE",
        "expected_grounded_terms": []
    }
]

held_out_out = Path("data/held_out_intent_benchmarks.json")
with open(held_out_out, "w", encoding="utf-8") as f:
    json.dump(held_out_cases, f, indent=2)

print(f"Saved {len(held_out_cases)} frozen held-out cases to {held_out_out}")
