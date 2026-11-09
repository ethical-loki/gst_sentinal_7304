"""
scripts/build_article_form_vocabulary.py
=========================================
Builds a curated vocabulary dataset from statutory tariff taxonomy
and 98 official chapter titles.

Zero hardcoding of product names in prediction code;
all taxonomical commodities, forms, and candidate chapters reside in data/article_form_vocabulary.json.

Output: data/article_form_vocabulary.json
"""

import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Set, Any
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("vocab_builder")

ROOT_DIR = Path(__file__).resolve().parent.parent
RAW_EXCEL = ROOT_DIR / "data" / "raw" / "Final_Copy_hsn_7304.xlsx"
CHAPTER_TITLES_FILE = ROOT_DIR / "src" / "chapter_predictor" / "chapter_titles.json"
OUT_FILE = ROOT_DIR / "data" / "article_form_vocabulary.json"

VALID_98_CHAPTERS = {f"{i:02d}" for i in range(1, 100) if i != 77}

CURATED_TAXONOMY: List[Dict[str, Any]] = [
    # FASTENERS & HARDWARE
    {"term": "screws", "type": "article", "family": "fasteners", "form_stage": "finished_article", "chapters": ["73", "74", "76"]},
    {"term": "screw", "type": "article", "family": "fasteners", "form_stage": "finished_article", "chapters": ["73", "74", "76"]},
    {"term": "bolts", "type": "article", "family": "fasteners", "form_stage": "finished_article", "chapters": ["73", "74", "76"]},
    {"term": "bolt", "type": "article", "family": "fasteners", "form_stage": "finished_article", "chapters": ["73", "74", "76"]},
    {"term": "nuts", "type": "article", "family": "fasteners", "form_stage": "finished_article", "chapters": ["73", "74", "76"]},
    {"term": "nut", "type": "article", "family": "fasteners", "form_stage": "finished_article", "chapters": ["73", "74", "76"]},
    {"term": "rivets", "type": "article", "family": "fasteners", "form_stage": "finished_article", "chapters": ["73", "74", "76", "83"]},
    {"term": "washers", "type": "article", "family": "fasteners", "form_stage": "finished_article", "chapters": ["73", "74", "76"]},
    {"term": "washer", "type": "article", "family": "fasteners", "form_stage": "finished_article", "chapters": ["73", "74", "76"]},
    {"term": "nails", "type": "article", "family": "fasteners", "form_stage": "finished_article", "chapters": ["73", "74", "76"]},
    {"term": "cotters", "type": "article", "family": "fasteners", "form_stage": "finished_article", "chapters": ["73"]},
    {"term": "pins", "type": "article", "family": "fasteners", "form_stage": "finished_article", "chapters": ["73", "96"]},

    # FITTINGS & FLANGES
    {"term": "blind flange", "type": "article", "family": "fittings", "form_stage": "finished_article", "chapters": ["73", "74", "76"]},
    {"term": "flanges", "type": "article", "family": "fittings", "form_stage": "finished_article", "chapters": ["73", "74", "76", "39"]},
    {"term": "flange", "type": "article", "family": "fittings", "form_stage": "finished_article", "chapters": ["73", "74", "76", "39"]},
    {"term": "pipe fitting", "type": "article", "family": "fittings", "form_stage": "finished_article", "chapters": ["73", "74", "76", "39"]},
    {"term": "pipe fittings", "type": "article", "family": "fittings", "form_stage": "finished_article", "chapters": ["73", "74", "76", "39"]},
    {"term": "elbows", "type": "article", "family": "fittings", "form_stage": "finished_article", "chapters": ["73", "74", "76", "39"]},
    {"term": "bends", "type": "article", "family": "fittings", "form_stage": "finished_article", "chapters": ["73", "74", "76", "39"]},
    {"term": "sleeves", "type": "article", "family": "fittings", "form_stage": "finished_article", "chapters": ["73", "74", "76", "39"]},
    {"term": "couplings", "type": "article", "family": "fittings", "form_stage": "finished_article", "chapters": ["73", "74", "76", "39", "84"]},
    {"term": "valves", "type": "article", "family": "fittings", "form_stage": "finished_article", "chapters": ["84"]},
    {"term": "valve", "type": "article", "family": "fittings", "form_stage": "finished_article", "chapters": ["84"]},

    # PIPES & TUBES
    {"term": "pipes", "type": "article", "family": "pipes_and_tubes", "form_stage": "worked", "chapters": ["73", "74", "76", "39", "68", "69"]},
    {"term": "pipe", "type": "article", "family": "pipes_and_tubes", "form_stage": "worked", "chapters": ["73", "74", "76", "39", "68", "69"]},
    {"term": "tubes", "type": "article", "family": "pipes_and_tubes", "form_stage": "worked", "chapters": ["73", "74", "76", "39", "70", "85"]},
    {"term": "tube", "type": "article", "family": "pipes_and_tubes", "form_stage": "worked", "chapters": ["73", "74", "76", "39", "70", "85"]},
    {"term": "hollow profiles", "type": "article", "family": "pipes_and_tubes", "form_stage": "worked", "chapters": ["73", "74", "76", "39"]},
    {"term": "line pipe", "type": "article", "family": "pipes_and_tubes", "form_stage": "worked", "chapters": ["73"]},
    {"term": "casing", "type": "article", "family": "pipes_and_tubes", "form_stage": "worked", "chapters": ["73", "84"]},
    {"term": "tubing", "type": "article", "family": "pipes_and_tubes", "form_stage": "worked", "chapters": ["73", "74", "76", "39"]},

    # CONTAINERS & PACKAGING
    {"term": "bottles", "type": "article", "family": "containers", "form_stage": "finished_article", "chapters": ["39", "70"]},
    {"term": "bottle", "type": "article", "family": "containers", "form_stage": "finished_article", "chapters": ["39", "70"]},
    {"term": "jars", "type": "article", "family": "containers", "form_stage": "finished_article", "chapters": ["39", "69", "70"]},
    {"term": "jar", "type": "article", "family": "containers", "form_stage": "finished_article", "chapters": ["39", "69", "70"]},
    {"term": "mugs", "type": "article", "family": "containers", "form_stage": "finished_article", "chapters": ["69", "70", "73", "39"]},
    {"term": "mug", "type": "article", "family": "containers", "form_stage": "finished_article", "chapters": ["69", "70", "73", "39"]},
    {"term": "cups", "type": "article", "family": "containers", "form_stage": "finished_article", "chapters": ["69", "70", "73", "39", "48"]},
    {"term": "cup", "type": "article", "family": "containers", "form_stage": "finished_article", "chapters": ["69", "70", "73", "39", "48"]},
    {"term": "drums", "type": "article", "family": "containers", "form_stage": "finished_article", "chapters": ["73", "76", "39", "44"]},
    {"term": "cans", "type": "article", "family": "containers", "form_stage": "finished_article", "chapters": ["73", "76"]},
    {"term": "can", "type": "article", "family": "containers", "form_stage": "finished_article", "chapters": ["73", "76"]},
    {"term": "boxes", "type": "article", "family": "containers", "form_stage": "finished_article", "chapters": ["39", "44", "48", "73"]},
    {"term": "box", "type": "article", "family": "containers", "form_stage": "finished_article", "chapters": ["39", "44", "48", "73"]},
    {"term": "bags", "type": "article", "family": "containers", "form_stage": "finished_article", "chapters": ["39", "42", "48", "63"]},
    {"term": "bag", "type": "article", "family": "containers", "form_stage": "finished_article", "chapters": ["39", "42", "48", "63"]},
    {"term": "carboys", "type": "article", "family": "containers", "form_stage": "finished_article", "chapters": ["39", "70"]},
    {"term": "flasks", "type": "article", "family": "containers", "form_stage": "finished_article", "chapters": ["70", "96"]},

    # RAW & SEMI-FINISHED METALS / FORMS
    {"term": "ingots", "type": "form", "family": "raw_metals_and_minerals", "form_stage": "raw", "chapters": ["72", "74", "76", "78", "79", "80"]},
    {"term": "ingot", "type": "form", "family": "raw_metals_and_minerals", "form_stage": "raw", "chapters": ["72", "74", "76", "78", "79", "80"]},
    {"term": "billets", "type": "form", "family": "raw_metals_and_minerals", "form_stage": "raw", "chapters": ["72", "74", "76"]},
    {"term": "billet", "type": "form", "family": "raw_metals_and_minerals", "form_stage": "raw", "chapters": ["72", "74", "76"]},
    {"term": "blooms", "type": "form", "family": "raw_metals_and_minerals", "form_stage": "raw", "chapters": ["72"]},
    {"term": "slabs", "type": "form", "family": "raw_metals_and_minerals", "form_stage": "raw", "chapters": ["72", "68"]},
    {"term": "coils", "type": "form", "family": "raw_metals_and_minerals", "form_stage": "raw", "chapters": ["72", "74", "76"]},
    {"term": "coil", "type": "form", "family": "raw_metals_and_minerals", "form_stage": "raw", "chapters": ["72", "74", "76"]},
    {"term": "bars", "type": "form", "family": "raw_metals_and_minerals", "form_stage": "worked", "chapters": ["72", "74", "76"]},
    {"term": "bar", "type": "form", "family": "raw_metals_and_minerals", "form_stage": "worked", "chapters": ["72", "74", "76"]},
    {"term": "rods", "type": "form", "family": "raw_metals_and_minerals", "form_stage": "worked", "chapters": ["72", "74", "76", "39", "70"]},
    {"term": "rod", "type": "form", "family": "raw_metals_and_minerals", "form_stage": "worked", "chapters": ["72", "74", "76", "39", "70"]},
    {"term": "wire", "type": "form", "family": "raw_metals_and_minerals", "form_stage": "worked", "chapters": ["72", "74", "76", "85"]},
    {"term": "sheets", "type": "form", "family": "sheets_and_plates", "form_stage": "worked", "chapters": ["72", "74", "76", "39", "40", "48", "70"]},
    {"term": "sheet", "type": "form", "family": "sheets_and_plates", "form_stage": "worked", "chapters": ["72", "74", "76", "39", "40", "48", "70"]},
    {"term": "plates", "type": "form", "family": "sheets_and_plates", "form_stage": "worked", "chapters": ["72", "74", "76", "39", "70", "69"]},
    {"term": "plate", "type": "form", "family": "sheets_and_plates", "form_stage": "worked", "chapters": ["72", "74", "76", "39", "70", "69"]},
    {"term": "strip", "type": "form", "family": "sheets_and_plates", "form_stage": "worked", "chapters": ["72", "74", "76", "39", "40"]},
    {"term": "foil", "type": "form", "family": "sheets_and_plates", "form_stage": "worked", "chapters": ["74", "76"]},
    {"term": "scrap", "type": "form", "family": "raw_metals_and_minerals", "form_stage": "raw", "chapters": ["72", "74", "76", "39", "40", "47"]},
    {"term": "waste", "type": "form", "family": "raw_metals_and_minerals", "form_stage": "raw", "chapters": ["72", "74", "76", "39", "40", "47", "52"]},

    # TEXTILES, YARNS, FABRICS & GARMENTS
    {"term": "yarn", "type": "article", "family": "yarns_and_fabrics", "form_stage": "worked", "chapters": ["50", "51", "52", "53", "54", "55"]},
    {"term": "thread", "type": "article", "family": "yarns_and_fabrics", "form_stage": "worked", "chapters": ["52", "54", "55"]},
    {"term": "fabric", "type": "article", "family": "yarns_and_fabrics", "form_stage": "worked", "chapters": ["50", "51", "52", "54", "55", "59", "60"]},
    {"term": "t-shirt", "type": "article", "family": "garments_and_apparel", "form_stage": "finished_article", "chapters": ["61"]},
    {"term": "t-shirts", "type": "article", "family": "garments_and_apparel", "form_stage": "finished_article", "chapters": ["61"]},
    {"term": "shirt", "type": "article", "family": "garments_and_apparel", "form_stage": "finished_article", "chapters": ["61", "62"]},
    {"term": "shirts", "type": "article", "family": "garments_and_apparel", "form_stage": "finished_article", "chapters": ["61", "62"]},
    {"term": "overcoat", "type": "article", "family": "garments_and_apparel", "form_stage": "finished_article", "chapters": ["61", "62"]},
    {"term": "overcoats", "type": "article", "family": "garments_and_apparel", "form_stage": "finished_article", "chapters": ["61", "62"]},
    {"term": "trousers", "type": "article", "family": "garments_and_apparel", "form_stage": "finished_article", "chapters": ["61", "62"]},
    {"term": "jacket", "type": "article", "family": "garments_and_apparel", "form_stage": "finished_article", "chapters": ["61", "62", "42"]},
    {"term": "jackets", "type": "article", "family": "garments_and_apparel", "form_stage": "finished_article", "chapters": ["61", "62", "42"]},
    {"term": "suit", "type": "article", "family": "garments_and_apparel", "form_stage": "finished_article", "chapters": ["61", "62"]},
    {"term": "dress", "type": "article", "family": "garments_and_apparel", "form_stage": "finished_article", "chapters": ["61", "62"]},
    {"term": "shoes", "type": "article", "family": "garments_and_apparel", "form_stage": "finished_article", "chapters": ["64"]},
    {"term": "footwear", "type": "article", "family": "garments_and_apparel", "form_stage": "finished_article", "chapters": ["64"]},

    # FURNITURE
    {"term": "cabinet", "type": "article", "family": "furniture", "form_stage": "finished_article", "chapters": ["94"]},
    {"term": "cabinets", "type": "article", "family": "furniture", "form_stage": "finished_article", "chapters": ["94"]},
    {"term": "almirah", "type": "article", "family": "furniture", "form_stage": "finished_article", "chapters": ["94"]},
    {"term": "chair", "type": "article", "family": "furniture", "form_stage": "finished_article", "chapters": ["94"]},
    {"term": "chairs", "type": "article", "family": "furniture", "form_stage": "finished_article", "chapters": ["94"]},
    {"term": "table", "type": "article", "family": "furniture", "form_stage": "finished_article", "chapters": ["94"]},
    {"term": "furniture", "type": "article", "family": "furniture", "form_stage": "finished_article", "chapters": ["94"]},

    # PAPER & STATIONERY
    {"term": "notebook", "type": "article", "family": "paper_articles", "form_stage": "finished_article", "chapters": ["48"]},
    {"term": "notebooks", "type": "article", "family": "paper_articles", "form_stage": "finished_article", "chapters": ["48"]},
    {"term": "diary", "type": "article", "family": "paper_articles", "form_stage": "finished_article", "chapters": ["48"]},
    {"term": "exercise book", "type": "article", "family": "paper_articles", "form_stage": "finished_article", "chapters": ["48"]},

    # AGRICULTURAL PRODUCE & FOODSTUFFS
    {"term": "coffee beans", "type": "article", "family": "coffee_and_tea", "form_stage": "raw", "chapters": ["09"]},
    {"term": "coffee", "type": "article", "family": "coffee_and_tea", "form_stage": "raw", "chapters": ["09", "21"]},
    {"term": "tea", "type": "article", "family": "coffee_and_tea", "form_stage": "raw", "chapters": ["09"]},
    {"term": "tea leaves", "type": "article", "family": "coffee_and_tea", "form_stage": "raw", "chapters": ["09"]},
    {"term": "wheat grains", "type": "article", "family": "cereals", "form_stage": "raw", "chapters": ["10"]},
    {"term": "wheat", "type": "article", "family": "cereals", "form_stage": "raw", "chapters": ["10", "11"]},
    {"term": "wheat flour", "type": "article", "family": "cereals", "form_stage": "worked", "chapters": ["11"]},
    {"term": "rice", "type": "article", "family": "cereals", "form_stage": "raw", "chapters": ["10", "11"]},
    {"term": "corn", "type": "article", "family": "cereals", "form_stage": "raw", "chapters": ["10"]},
    {"term": "maize", "type": "article", "family": "cereals", "form_stage": "raw", "chapters": ["10"]},
    {"term": "oats", "type": "article", "family": "cereals", "form_stage": "worked", "chapters": ["11"]},
    {"term": "apples", "type": "article", "family": "fruits", "form_stage": "raw", "chapters": ["08"]},
    {"term": "apple", "type": "article", "family": "fruits", "form_stage": "raw", "chapters": ["08"]},
    {"term": "onion", "type": "article", "family": "vegetables", "form_stage": "raw", "chapters": ["07"]},
    {"term": "onions", "type": "article", "family": "vegetables", "form_stage": "raw", "chapters": ["07"]},
    {"term": "potatoes", "type": "article", "family": "vegetables", "form_stage": "raw", "chapters": ["07"]},
    {"term": "potato", "type": "article", "family": "vegetables", "form_stage": "raw", "chapters": ["07"]},
    {"term": "french fries", "type": "article", "family": "food_preparations", "form_stage": "finished_article", "chapters": ["20"]},
    {"term": "french fry", "type": "article", "family": "food_preparations", "form_stage": "finished_article", "chapters": ["20"]},
    {"term": "honey", "type": "article", "family": "dairy_and_animal", "form_stage": "raw", "chapters": ["04"]},
    {"term": "cheese", "type": "article", "family": "dairy_and_animal", "form_stage": "finished_article", "chapters": ["04"]},
    {"term": "soyabean", "type": "article", "family": "oil_seeds", "form_stage": "raw", "chapters": ["12"]},
    {"term": "soyabeans", "type": "article", "family": "oil_seeds", "form_stage": "raw", "chapters": ["12"]},
    {"term": "prawns", "type": "article", "family": "seafood", "form_stage": "raw", "chapters": ["03", "16"]},
    {"term": "fish", "type": "article", "family": "seafood", "form_stage": "raw", "chapters": ["03", "16"]},

    # BEVERAGES & MINERAL FUELS
    {"term": "beer", "type": "article", "family": "beverages", "form_stage": "finished_article", "chapters": ["22"]},
    {"term": "drinking water", "type": "article", "family": "beverages", "form_stage": "finished_article", "chapters": ["22"]},
    {"term": "mineral water", "type": "article", "family": "beverages", "form_stage": "finished_article", "chapters": ["22"]},
    {"term": "water", "type": "article", "family": "beverages", "form_stage": "finished_article", "chapters": ["22"]},
    {"term": "petrol", "type": "article", "family": "mineral_fuels", "form_stage": "finished_article", "chapters": ["27"]},
    {"term": "gasoline", "type": "article", "family": "mineral_fuels", "form_stage": "finished_article", "chapters": ["27"]},
    {"term": "lubricant", "type": "article", "family": "mineral_fuels", "form_stage": "finished_article", "chapters": ["27"]},
    {"term": "lubricating oil", "type": "article", "family": "mineral_fuels", "form_stage": "finished_article", "chapters": ["27"]},
    {"term": "grease", "type": "article", "family": "mineral_fuels", "form_stage": "finished_article", "chapters": ["27"]},

    # CHEMICALS & PHARMACEUTICALS
    {"term": "paracetamol", "type": "article", "family": "pharmaceuticals", "form_stage": "finished_article", "chapters": ["30"]},
    {"term": "amoxicillin", "type": "article", "family": "pharmaceuticals", "form_stage": "finished_article", "chapters": ["30"]},
    {"term": "vaccine", "type": "article", "family": "pharmaceuticals", "form_stage": "finished_article", "chapters": ["30"]},
    {"term": "ethanol", "type": "article", "family": "chemicals", "form_stage": "finished_article", "chapters": ["22", "29"]},
    {"term": "ethyl alcohol", "type": "article", "family": "chemicals", "form_stage": "finished_article", "chapters": ["22", "29"]},
    {"term": "methanol", "type": "article", "family": "chemicals", "form_stage": "finished_article", "chapters": ["29"]},
    {"term": "acetic acid", "type": "article", "family": "chemicals", "form_stage": "finished_article", "chapters": ["29"]},
    {"term": "paint", "type": "article", "family": "paints", "form_stage": "finished_article", "chapters": ["32"]},
    {"term": "perfume", "type": "article", "family": "cosmetics", "form_stage": "finished_article", "chapters": ["33"]},
    {"term": "lipstick", "type": "article", "family": "cosmetics", "form_stage": "finished_article", "chapters": ["33"]},
    {"term": "detergent", "type": "article", "family": "soaps", "form_stage": "finished_article", "chapters": ["34"]},
    {"term": "washing powder", "type": "article", "family": "soaps", "form_stage": "finished_article", "chapters": ["34"]},
    {"term": "matches", "type": "article", "family": "explosives", "form_stage": "finished_article", "chapters": ["36"]},
    {"term": "activated carbon", "type": "article", "family": "chemical_products", "form_stage": "finished_article", "chapters": ["38"]},
    {"term": "insecticide", "type": "article", "family": "chemical_products", "form_stage": "finished_article", "chapters": ["38"]},
    {"term": "sanitizer", "type": "article", "family": "chemical_products", "form_stage": "finished_article", "chapters": ["38"]},
    {"term": "shellac", "type": "article", "family": "gums_and_resins", "form_stage": "raw", "chapters": ["13"]},
    {"term": "cane sticks", "type": "article", "family": "vegetable_materials", "form_stage": "raw", "chapters": ["14"]},

    # PRECIOUS STONES & METALS
    {"term": "diamond", "type": "article", "family": "precious_stones", "form_stage": "raw", "chapters": ["71"]},
    {"term": "diamonds", "type": "article", "family": "precious_stones", "form_stage": "raw", "chapters": ["71"]},
    {"term": "jewellery", "type": "article", "family": "precious_metals", "form_stage": "finished_article", "chapters": ["71"]},

    # INSTRUMENTS, APPLIANCES & MISC
    {"term": "cable", "type": "article", "family": "electrical", "form_stage": "finished_article", "chapters": ["85"]},
    {"term": "wire cable", "type": "article", "family": "electrical", "form_stage": "finished_article", "chapters": ["85"]},
    {"term": "computer", "type": "article", "family": "machinery", "form_stage": "finished_article", "chapters": ["84"]},
    {"term": "laptop", "type": "article", "family": "machinery", "form_stage": "finished_article", "chapters": ["84"]},
    {"term": "motherboard", "type": "article", "family": "machinery", "form_stage": "finished_article", "chapters": ["84"]},
    {"term": "refrigerator", "type": "article", "family": "machinery", "form_stage": "finished_article", "chapters": ["84"]},
    {"term": "multimeter", "type": "article", "family": "instruments", "form_stage": "finished_article", "chapters": ["90"]},
    {"term": "scalpel", "type": "article", "family": "instruments", "form_stage": "finished_article", "chapters": ["90"]},
    {"term": "toothbrush", "type": "article", "family": "miscellaneous", "form_stage": "finished_article", "chapters": ["96"]},
    {"term": "painting", "type": "article", "family": "art_and_antiques", "form_stage": "finished_article", "chapters": ["97"]},
    {"term": "artwork", "type": "article", "family": "art_and_antiques", "form_stage": "finished_article", "chapters": ["97"]},
    {"term": "clock", "type": "article", "family": "clocks", "form_stage": "finished_article", "chapters": ["91", "97"]},

    # ELECTRONICS & APPLIANCES
    {"term": "microprocessor", "type": "article", "family": "electronics_and_appliances", "form_stage": "finished_article", "chapters": ["85"]},
    {"term": "microprocessors", "type": "article", "family": "electronics_and_appliances", "form_stage": "finished_article", "chapters": ["85"]},
    {"term": "integrated circuit", "type": "article", "family": "electronics_and_appliances", "form_stage": "finished_article", "chapters": ["85"]},
    {"term": "integrated circuits", "type": "article", "family": "electronics_and_appliances", "form_stage": "finished_article", "chapters": ["85"]},
    {"term": "memories", "type": "article", "family": "electronics_and_appliances", "form_stage": "finished_article", "chapters": ["85"]},
    {"term": "semiconductor", "type": "article", "family": "electronics_and_appliances", "form_stage": "finished_article", "chapters": ["85"]},
    {"term": "diodes", "type": "article", "family": "electronics_and_appliances", "form_stage": "finished_article", "chapters": ["85"]},
    {"term": "transistors", "type": "article", "family": "electronics_and_appliances", "form_stage": "finished_article", "chapters": ["85"]},
    {"term": "transformers", "type": "article", "family": "electronics_and_appliances", "form_stage": "finished_article", "chapters": ["85"]},
    {"term": "batteries", "type": "article", "family": "electronics_and_appliances", "form_stage": "finished_article", "chapters": ["85"]},
    {"term": "accumulators", "type": "article", "family": "electronics_and_appliances", "form_stage": "finished_article", "chapters": ["85"]},
    {"term": "mobile phone", "type": "article", "family": "electronics_and_appliances", "form_stage": "finished_article", "chapters": ["85"]},
    {"term": "ball point pen", "type": "article", "family": "miscellaneous", "form_stage": "finished_article", "chapters": ["96"]},
    {"term": "pen", "type": "article", "family": "miscellaneous", "form_stage": "finished_article", "chapters": ["96"]},
    {"term": "cement", "type": "article", "family": "minerals", "form_stage": "raw", "chapters": ["25"]},

    # CONSTITUENT MATERIALS
    {"term": "ceramic", "type": "material", "family": "ceramics", "form_stage": "not_applicable", "chapters": ["69"]},
    {"term": "porcelain", "type": "material", "family": "ceramics", "form_stage": "not_applicable", "chapters": ["69"]},
    {"term": "glass", "type": "material", "family": "glass", "form_stage": "not_applicable", "chapters": ["70"]},
    {"term": "steel", "type": "material", "family": "metals", "form_stage": "not_applicable", "chapters": ["72", "73"]},
    {"term": "stainless steel", "type": "material", "family": "metals", "form_stage": "not_applicable", "chapters": ["72", "73"]},
    {"term": "iron", "type": "material", "family": "metals", "form_stage": "not_applicable", "chapters": ["72", "73"]},
    {"term": "copper", "type": "material", "family": "metals", "form_stage": "not_applicable", "chapters": ["74"]},
    {"term": "aluminium", "type": "material", "family": "metals", "form_stage": "not_applicable", "chapters": ["76"]},
    {"term": "cotton", "type": "material", "family": "textiles", "form_stage": "not_applicable", "chapters": ["52"]},
    {"term": "wool", "type": "material", "family": "textiles", "form_stage": "not_applicable", "chapters": ["51"]},
    {"term": "silk", "type": "material", "family": "textiles", "form_stage": "not_applicable", "chapters": ["50"]},
    {"term": "leather", "type": "material", "family": "leather", "form_stage": "not_applicable", "chapters": ["41", "42"]},
    {"term": "wood", "type": "material", "family": "wood", "form_stage": "not_applicable", "chapters": ["44"]},
    {"term": "paper", "type": "material", "family": "paper", "form_stage": "not_applicable", "chapters": ["48"]},
    {"term": "plastic", "type": "material", "family": "polymers", "form_stage": "not_applicable", "chapters": ["39"]},
    {"term": "rubber", "type": "material", "family": "polymers", "form_stage": "not_applicable", "chapters": ["40"]}
]


def build_vocabulary():
    logger.info("Building article and form vocabulary...")

    vocab_map: Dict[str, Dict[str, Any]] = {}
    for entry in CURATED_TAXONOMY:
        term = entry["term"].strip().lower()
        # Strictly enforce closed set of 98 chapters
        clean_chs = sorted(list({c.zfill(2) for c in entry["chapters"] if c.zfill(2) in VALID_98_CHAPTERS}))
        vocab_map[term] = {
            "term": term,
            "type": entry["type"],
            "family": entry["family"],
            "form_stage": entry["form_stage"],
            "candidate_chapters": clean_chs,
            "source": "curated_statutory"
        }

    # Save output to JSON
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    vocab_list = sorted(list(vocab_map.values()), key=lambda x: (x["type"], x["family"], x["term"]))
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(vocab_list, f, indent=2)

    logger.info(f"[SUCCESS] Article and form vocabulary saved to {OUT_FILE} ({len(vocab_list)} curated statutory terms).")


if __name__ == "__main__":
    build_vocabulary()
