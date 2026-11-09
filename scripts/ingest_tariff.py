"""
Universal Tariff Ingestion Pipeline: scripts/ingest_tariff.py
Parses and normalizes the official HSN & SAC Master Schedule from data/raw/HSN_SAC (1).xlsx
(both HSN_MSTR and SAC_MSTR sheets, reconstructing full hierarchical descriptions from
2-digit/4-digit/6-digit ancestors down to 8-digit HSN and 6-digit SAC codes, with standard_rate=None/null),
and persists to data/tariff_master.parquet and data/raw/tariff_master.parquet.
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set
import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
RAW_EXCEL_PATH = ROOT_DIR / "data" / "raw" / "Final_Copy_hsn_7304.xlsx"
OUTPUT_PARQUET_PATH = ROOT_DIR / "data" / "tariff_master.parquet"
RAW_OUTPUT_PARQUET_PATH = ROOT_DIR / "data" / "raw" / "tariff_master.parquet"

# Section 17(5) Blocked ITC rules
BLOCKED_17_5_CHAPTERS = {
    "8702": "Blocked: Section 17(5)(a) Passenger transport motor vehicles",
    "8703": "Blocked: Section 17(5)(a) Motor cars & passenger vehicles",
    "8711": "Blocked: Section 17(5)(a) Two-wheelers / motorcycles",
    "8903": "Blocked: Section 17(5)(b) Vessels and yachts",
    "8802": "Blocked: Section 17(5)(b) Aircraft for non-exempt purposes",
    "2106": "Blocked: Section 17(5)(b)(i) Food & beverages / catering",
    "2201": "Blocked: Section 17(5)(b)(i) Beverages / drinking water catering",
    "2202": "Blocked: Section 17(5)(b)(i) Aerated waters / non-alcoholic beverages",
}

CHAPTER_TITLES: Dict[str, str] = {
    "01": "Live animals",
    "02": "Meat and edible meat offal",
    "03": "Fish and crustaceans, molluscs and other aquatic invertebrates",
    "04": "Dairy produce, birds eggs, natural honey, edible products of animal origin",
    "05": "Products of animal origin not elsewhere specified or included",
    "06": "Live trees and other plants, bulbs, roots and cut flowers",
    "07": "Edible vegetables and certain roots and tubers",
    "08": "Edible fruit and nuts, apples, pears, peel of citrus fruit or melons",
    "09": "Coffee, tea, mate and spices",
    "10": "Cereals and grains, wheat, rice, barley, oats, maize, corn",
    "11": "Products of the milling industry, malt, starches, inulin, wheat gluten",
    "12": "Oil seeds and oleaginous fruits, grains, seeds, industrial or medicinal plants",
    "13": "Lac, gums, resins and other vegetable saps and extracts",
    "14": "Vegetable plaiting materials and products of vegetable origin",
    "15": "Animal or vegetable fats and oils and their cleavage products, edible fats, waxes",
    "16": "Preparations of meat, of fish or of crustaceans, molluscs or other aquatic invertebrates",
    "17": "Sugars and sugar confectionery",
    "18": "Cocoa and cocoa preparations",
    "19": "Preparations of cereals, flour, starch or milk, pastrycooks products",
    "20": "Preparations of vegetables, fruit, nuts or other parts of plants",
    "21": "Miscellaneous edible preparations, sauces, soups, extracts",
    "22": "Beverages, spirits and vinegar",
    "23": "Residues and waste from the food industries, prepared animal fodder",
    "24": "Tobacco and manufactured tobacco substitutes",
    "25": "Salt, sulphur, earths and stone, plastering materials, lime and cement",
    "26": "Ores, slag and ash, metallic minerals",
    "27": "Mineral fuels, mineral oils and products of their distillation, coal, petroleum",
    "28": "Inorganic chemicals, precious metal compounds, rare-earth metals, isotopes, mercury, chemical elements, acids, alkalis",
    "29": "Organic chemicals, hydrocarbons, alcohols, phenols, ethers, carboxylic acids",
    "30": "Pharmaceutical products, medicaments, vaccines, veterinary medicines",
    "31": "Fertilisers, nitrogenous, phosphatic, potassic, urea, NPK",
    "32": "Tanning or dyeing extracts, tannins, dyes, pigments, paints, varnishes, putty, inks",
    "33": "Essential oils and resinoids, perfumery, cosmetic or toilet preparations",
    "34": "Soap, organic surface-active agents, washing preparations, lubricating preparations",
    "35": "Albuminoidal substances, modified starches, glues, enzymes",
    "36": "Explosives, pyrotechnic products, matches, pyrophoric alloys",
    "37": "Photographic or cinematographic goods",
    "38": "Miscellaneous chemical products, catalysts, additives, solvents",
    "39": "Plastics and articles thereof, polymers, conduit pipes, HDPE, PVC, resins",
    "40": "Rubber and articles thereof, tyres, tubes, synthetic rubber",
    "41": "Raw hides and skins other than furskins and leather",
    "42": "Articles of leather, saddlery and harness, travel goods, handbags",
    "43": "Furskins and artificial fur, manufactures thereof",
    "44": "Wood and articles of wood, wood charcoal, timber, plywood",
    "45": "Cork and articles of cork",
    "46": "Manufactures of straw, esparto or other plaiting materials, basketware",
    "47": "Pulp of wood or other fibrous cellulosic material, waste and scrap paper",
    "48": "Paper and paperboard, articles of paper pulp, cardboard, paper products",
    "49": "Printed books, newspapers, pictures and other products of the printing industry",
    "50": "Silk, silk yarn, woven fabrics of silk",
    "51": "Wool, fine or coarse animal hair, horsehair yarn and fabric",
    "52": "Cotton, cotton yarn, combed, carded, cotton sewing thread, woven fabrics",
    "53": "Other vegetable textile fibres, paper yarn and woven fabrics of paper yarn, jute, flax",
    "54": "Man-made filaments, synthetic filament yarn, strip of man-made textile materials",
    "55": "Man-made staple fibres, synthetic staple fibres, polyester, viscose",
    "56": "Wadding, felt and nonwovens, special yarns, twine, cordage, ropes and cables",
    "57": "Carpets and other textile floor coverings",
    "58": "Special woven fabrics, tufted textile fabrics, lace, tapestries, trimmings, embroidery",
    "59": "Impregnated, coated, covered or laminated textile fabrics, industrial textiles",
    "60": "Knitted or crocheted fabrics",
    "61": "Articles of apparel and clothing accessories, knitted or crocheted, garments, hosiery",
    "62": "Articles of apparel and clothing accessories, not knitted or crocheted, woven garments",
    "63": "Other made up textile articles, sets, worn clothing, rags, blankets, curtains",
    "64": "Footwear, gaiters and the like, parts of such articles, shoes, boots, chappals",
    "65": "Headgear and parts thereof, hats, caps, helmets",
    "66": "Umbrellas, sun umbrellas, walking-sticks, seat-sticks, whips, riding-crops",
    "67": "Prepared feathers and down and articles made of feathers, artificial flowers, human hair",
    "68": "Articles of stone, plaster, cement, asbestos, mica or similar materials",
    "69": "Ceramic products, bricks, tiles, porcelain, sanitary ware",
    "70": "Glass and glassware, sheet glass, bottles, laboratory glass",
    "71": "Natural or cultured pearls, precious stones, precious metals, gold, silver, jewellery",
    "72": "Iron and steel, primary products, billets, bars, rods, wire, flat-rolled steel",
    "73": "Articles of iron or steel, pipes, tubes, tube fittings, flanges, hex nipples, elbows, tanks, screws, bolts, nuts, washers, fasteners",
    "74": "Copper and articles thereof, copper wire, tubes, bars",
    "75": "Nickel and articles thereof",
    "76": "Aluminium and articles thereof, sheets, plates, aluminium wire, foils",
    "78": "Lead and articles thereof",
    "79": "Zinc and articles thereof",
    "80": "Tin and articles thereof",
    "81": "Other base metals, cermets, articles thereof, titanium, tungsten",
    "82": "Tools, implements, cutlery, spoons and forks, base metal hand tools, blades",
    "83": "Miscellaneous articles of base metal, padlocks, keys, mountings, fittings",
    "84": "Nuclear reactors, boilers, machinery and mechanical appliances, valves, ball valves, check valves, pumps, engines, mechanical equipment",
    "85": "Electrical machinery and equipment, sound recorders, television apparatus, static converters, inverters, solar inverters, smps, transformers, insulated cables, conductors, wires",
    "86": "Railway or tramway locomotives, rolling-stock, track fixtures, signaling equipment",
    "87": "Vehicles other than railway or tramway rolling-stock, motor cars, commercial vehicles, motorcycles, tractors, parts",
    "88": "Aircraft, spacecraft, and parts thereof",
    "89": "Ships, boats and floating structures, vessels, tugs, barges",
    "90": "Optical, photographic, measuring, checking, precision, medical or surgical instruments",
    "91": "Clocks and watches and parts thereof",
    "92": "Musical instruments, parts and accessories",
    "93": "Arms and ammunition, parts and accessories thereof",
    "94": "Furniture, bedding, mattresses, lamps and lighting fittings, prefabricated buildings",
    "95": "Toys, games and sports requisites, parts and accessories thereof",
    "96": "Miscellaneous manufactured articles, pens, brushes, buttons, slide fasteners",
    "97": "Works of art, collectors pieces and antiques",
    "98": "Project imports, laboratory chemicals, passengers baggage",
    "99": "Services (SAC - Services Accounting Code), construction, IT, transport, financial, professional services"
}

HEADING_SYNONYMS: Dict[str, str] = {
    "7307": "tube or pipe fittings couplings elbows sleeves flanges flange nipples nipple hex nipple tee reducing bush socket weld union forged steel stainless steel SS 304 GI reducing bush",
    "7306": "other tubes pipes and hollow profiles welded erw pipe tube welded stainless steel erw pipe",
    "7304": "tubes pipes and hollow profiles seamless iron steel hydraulic seamless tube pipe ms seamless hydraulic tube",
    "8481": "taps cocks valves boiler shells pipes ball valve check valve non return needle valve industrial valve 2-piece ball valve cast iron non return check valve needle valve 6000 psi",
    "7318": "screws screw bolts bolt hex bolt hex head bolt nuts nut nylon nut coach screws screw hooks rivets cotters cotter-pins washers washer spring lock washer fasteners allen cap M10 M12",
    "3917": "tubes pipes and hoses and fittings upvc hdpe pvc pipe conduit solvent weld plastic coil pipe uPVC elbow solvent weld HDPE coil pipe",
    "8544": "insulated wire cable optical fibre cables copper aluminum conductor flexible power cable armoured cable wiring FR PVC insulated industrial wiring copper armoured aluminum cable",
    "8504": "electrical transformers static converters inverters solar inverter smps power supply rectifier dry type isolation transformer solar on grid inverter",
    "2805": "alkali or alkaline-earth metals rare-earth metals mercury elemental liquid quicksilver hydrargyrum metal",
    "2852": "mercury compounds inorganic organic chemically defined mercuric mercurous chloride",
    "2807": "sulfuric acid sulphuric acid oleum hydrogen sulfate",
    "1006": "rice parboiled basmati non basmati milled paddy husked semi-milled",
    "5205": "cotton yarn combed carded single multiple folded ring spun",
    "5206": "cotton yarn combed carded containing less than 85% by weight of cotton",
    "3901": "polymers of ethylene hdpe ldpe lldpe polyethylene granules pellets primary form",
    "0101": "live horses horse asses mules and hinnies pure-bred breeding animals",
    "0808": "apples apple pears and quinces fresh fruit",
}


def clean_text_description(text: object) -> str:
    """Cleans statutory text description: normalizes whitespace."""
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return ""
    text_str = str(text).strip()
    text_str = re.sub(r"[\x00-\x1f\x7f-\x9f\u200b-\u200d\ufeff]", " ", text_str)
    # Remove spreadsheet artifact like '+L14152'
    text_str = re.sub(r"\+L\d+", "", text_str)
    return re.sub(r"\s+", " ", text_str).strip()


def normalize_clean_description(text: str) -> str:
    """Removes punctuation and normalizes characters for n-gram feature hashing."""
    cleaned = re.sub(r"[^a-zA-Z0-9\s]", " ", text.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def normalize_hsn_sac_code(raw_code: object) -> str:
    """Normalizes HSN/SAC code string into 2, 4, 6, or 8 digits."""
    if raw_code is None or (isinstance(raw_code, float) and pd.isna(raw_code)):
        return ""
    digits = re.sub(r"\D", "", str(raw_code).strip())
    if not digits:
        return ""
    if len(digits) == 3:
        digits = digits.zfill(4)
    elif len(digits) == 5:
        digits = digits.zfill(6)
    elif len(digits) == 7:
        digits = digits.zfill(8)
    return digits


def parse_hsn_sac_master_excel(excel_path: Path = RAW_EXCEL_PATH) -> List[Dict]:
    """
    Parses official HSN & SAC Master from data/raw/Final_Copy_hsn_7304.xlsx
    (or dual-sheet HSN_MSTR / SAC_MSTR if present).
    Reconstructs full hierarchical context descriptions for 6-digit and 8-digit codes
    from their 4-digit and 6-digit parent rows so every leaf item is self-contained.
    """
    if not excel_path.exists():
        fallback = ROOT_DIR / "data" / "raw" / "HSN_SAC (1).xlsx"
        if fallback.exists():
            excel_path = fallback
        else:
            raise FileNotFoundError(f"Tariff Excel file not found at {excel_path}")

    xl = pd.ExcelFile(excel_path)
    sheet_names = xl.sheet_names
    raw_rows: List[Tuple[str, str, str]] = []

    if "HSN_MSTR" in sheet_names and "SAC_MSTR" in sheet_names:
        df_hsn = xl.parse("HSN_MSTR", dtype=str)
        df_sac = xl.parse("SAC_MSTR", dtype=str)

        for _, row in df_hsn.iterrows():
            c = normalize_hsn_sac_code(row.iloc[0])
            d = clean_text_description(row.iloc[1])
            if c and d and len(c) in (2, 4, 6, 8):
                raw_rows.append((c, d, "HSN"))

        for _, row in df_sac.iterrows():
            c = normalize_hsn_sac_code(row.iloc[0])
            d = clean_text_description(row.iloc[1])
            if c and d and len(c) in (2, 4, 6, 8):
                raw_rows.append((c, d, "SAC"))
    else:
        # Single-sheet structure (e.g. Final_Copy_hsn_7304.xlsx)
        df_master = xl.parse(sheet_names[0], dtype=str)
        code_col_idx = 0
        desc_col_idx = 1
        for idx, col in enumerate(df_master.columns):
            c_low = str(col).lower()
            if "desc" in c_low:
                desc_col_idx = idx
            elif "code" in c_low or "hsn" in c_low:
                code_col_idx = idx

        for _, row in df_master.iterrows():
            c = normalize_hsn_sac_code(row.iloc[code_col_idx])
            d = clean_text_description(row.iloc[desc_col_idx])
            if c and d and len(c) in (2, 4, 6, 8):
                code_type = "SAC" if c.startswith("99") else "HSN"
                raw_rows.append((c, d, code_type))

    # First pass: build lookup of 2-digit, 4-digit, 5-digit group, and 6-digit parent descriptions
    desc_4d: Dict[str, str] = {}
    desc_5d: Dict[str, str] = {}
    desc_6d: Dict[str, str] = {}
    has_children_6d: Set[str] = set()

    for c, d, _ in raw_rows:
        if len(c) == 4 and c not in desc_4d:
            desc_4d[c] = d.rstrip(" :.-")
        elif len(c) == 6 and c not in desc_6d:
            desc_6d[c] = d.rstrip(" :.-")
        elif len(c) == 8:
            has_children_6d.add(c[:6])
            # Extract intermediate 5-digit group title from 8-digit rows that contain " - <GROUP TITLE> :"
            g5 = c[:5]
            if g5 not in desc_5d and " - " in d:
                after_dash = d.split(" - ", 1)[1]
                if ":" in after_dash:
                    grp_title = after_dash.split(":", 1)[0].strip(" :.-")
                    if len(grp_title) > 4:
                        desc_5d[g5] = grp_title

    # Second pass: assemble enriched records for all HSNs and SACs from HSN_SAC (1).xlsx
    expanded_rows: List[Dict] = []
    for c, d, code_type in raw_rows:
        h4 = c[:4] if len(c) >= 4 else c.zfill(4)
        g5 = c[:5] if len(c) >= 6 else ""
        s6 = c[:6] if len(c) >= 6 else ""
        p4 = desc_4d.get(h4, "")
        p5 = desc_5d.get(g5, "") if g5 else ""
        p6 = desc_6d.get(s6, "") if s6 else ""

        if len(c) == 8:
            # Build hierarchical description: [4-digit Heading] - [5-digit Group] : -- [6-digit Subheading] : --- [8-digit Leaf]
            d_low = d.lower()
            parts: List[str] = []
            if p4 and p4.lower()[:25] not in d_low:
                parts.append(p4)
            if p5 and p5.lower()[:20] not in d_low and (not p6 or p5.lower()[:20] not in p6.lower()):
                parts.append(p5)
            if p6 and p6.lower() not in d_low and (not p4 or p6.lower() != p4.lower()):
                parts.append(f"-- {p6}")
            parts.append(d)
            if len(parts) == 1:
                full_desc = parts[0]
            elif len(parts) == 2:
                full_desc = f"{parts[0]} - {parts[1]}"
            else:
                full_desc = f"{parts[0]} - {' : '.join(parts[1:-1])} : --- {parts[-1]}"
        elif len(c) == 6:
            if p4 and p4.lower()[:25] not in d.lower():
                full_desc = f"{p4} - {d}"
            else:
                full_desc = d
        else:
            full_desc = d

        expanded_rows.append({
            "hsn_code": c,
            "description": full_desc,
            "raw_leaf_description": d,
            "code_type": code_type,
            "standard_rate": None,
        })

    return expanded_rows


def ingest_universal_tariff(
    excel_path: Path = RAW_EXCEL_PATH,
    out_path: Path = OUTPUT_PARQUET_PATH,
    raw_out_path: Path = RAW_OUTPUT_PARQUET_PATH,
) -> pd.DataFrame:
    """Ingests the official HSN & SAC Master Schedule from HSN_SAC (1).xlsx and serializes to parquet."""
    print("=" * 70)
    print("   OFFICIAL HSN & SAC MASTER SCHEDULE INGESTION (HSN_SAC (1).xlsx)   ")
    print("=" * 70)

    print(f"[*] Reading and parsing HSN_MSTR and SAC_MSTR from {excel_path}...")
    expanded_rows = parse_hsn_sac_master_excel(excel_path)
    print(f"[*] Extracted {len(expanded_rows):,} hierarchical HSN/SAC entries from {excel_path.name}")

    records: List[Dict] = []
    seen_keys: Set[str] = set()

    for item in expanded_rows:
        hsn_code = str(item["hsn_code"]).strip()
        desc = clean_text_description(item["description"])
        if not hsn_code or not desc:
            continue

        chapter = hsn_code[:2].zfill(2)
        heading = hsn_code[:4] if len(hsn_code) >= 4 else hsn_code.zfill(4)

        ch_title = CHAPTER_TITLES.get(chapter, "")
        heading_syn = HEADING_SYNONYMS.get(heading, "")

        search_components = [
            f"Chapter {chapter} - {ch_title}",
            f"Heading {heading} - {heading_syn}" if heading_syn else f"Heading {heading}",
            f"{hsn_code} {desc}",
        ]
        search_text = " | ".join(search_components)

        is_blocked = 1 if heading in BLOCKED_17_5_CHAPTERS else 0
        blocked_reason = BLOCKED_17_5_CHAPTERS.get(heading, "Eligible: General ITC")

        key = hsn_code
        if key in seen_keys:
            continue
        seen_keys.add(key)

        clean_desc = normalize_clean_description(f"{desc} {heading_syn}")

        records.append({
            "hsn_code": hsn_code,
            "heading": heading,
            "hsn_4digit": heading,
            "chapter": chapter,
            "description": desc,
            "hsn_description": desc,
            "search_text": search_text,
            "clean_description": clean_desc,
            "standard_rate": None,
            "is_blocked_17_5": int(is_blocked),
            "blocked_17_5_reason": blocked_reason,
            "effective_date": "2025-09-22",
        })

    df = pd.DataFrame(records)
    df["standard_rate"] = pd.Series([None] * len(df), dtype="float64")
    df = df.drop_duplicates(subset=["hsn_code", "description"]).reset_index(drop=True)
    df = df.sort_values(by=["chapter", "heading", "hsn_code"]).reset_index(drop=True)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, engine="pyarrow", index=False)

    raw_out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(raw_out_path, engine="pyarrow", index=False)

    print(f"[OK] Ingestion complete. Serialized {len(df):,} official HSN/SAC records to {out_path} and {raw_out_path}")
    print(f"     Chapters: {df['chapter'].nunique()} | 4-digit Headings: {df['heading'].nunique()} | Unique HSN/SACs: {df['hsn_code'].nunique()}")
    return df


if __name__ == "__main__":
    ingest_universal_tariff()
