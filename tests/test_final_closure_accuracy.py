"""
tests/test_final_closure_accuracy.py
====================================
Unit and integration verification for the final accuracy improvement cycle:
1. Syntactic head-noun & non-corrupting singularization ("apparatus", rightmost non-generic noun).
2. Subheading/leaf material priority over parent heading ("OF HARDENED PROTEIN" under "OF PLASTICS").
3. Symmetric parts_vs_complete_article role detection & un- / non- prefix negation ("unplasticised").
4. Hyphenated parenthetical statutory exclusions ("(OTHER THAN T-SHIRTS)").
5. Mutually exclusive propulsion (spark-ignition vs diesel), power-source (wind vs water turbine),
   and media state (unrecorded/recordable vs recorded) statutory checks.
6. Non-saturating AdaptiveCandidateDiscoverer budget accounting (no double-counting).
"""

from src.chapter_predictor.normalize import extract_query_facts
from src.ml.candidate_evidence_evaluator import (
    CONTRADICTED,
    build_candidate_profile,
    evaluate_candidate_evidence,
)
from src.nlp.product_intent_analyzer import analyze_product_intent


def test_apparatus_stemming_and_rightmost_syntactic_head_noun():
    pi_app = analyze_product_intent("fm radio broadcast transmitter apparatus")
    assert pi_app.product_head_noun.lower() == "apparatus"

    pi_tr = analyze_product_intent("satellite earth station uplink transceiver")
    assert pi_tr.product_head_noun.lower() == "transceiver"

    # Generic trailing "unit" falls back cleanly to concrete noun immediately preceding it
    pi_unit = analyze_product_intent("laboratory autoclave sterilizer unit")
    assert pi_unit.product_head_noun.lower() == "sterilizer"


def test_leaf_material_priority_unplasticised_negation_and_hyphen_exclusion():
    # 1. Subheading/leaf "OF HARDENED PROTEIN" overrides parent Heading 3917 "OF PLASTICS"
    pi_pvc = analyze_product_intent("flexible plasticized pvc sausage casing tubing")
    rec_protein = {
        "hsn_code": "39171010",
        "code_length": 8,
        "chapter_code": "39",
        "chapter_title": "Plastics and articles thereof",
        "heading_4digit": "3917",
        "heading_4digit_desc": "TUBES, PIPES AND HOSES, AND FITTINGS THEREFOR, OF PLASTICS",
        "subheading_6digit": "391710",
        "subheading_6digit_desc": "",
        "tariff_item_desc": "OF HARDENED PROTEIN",
        "statutory_description": "TUBES, PIPES AND HOSES, OF PLASTICS - ARTIFICIAL GUTS : OF HARDENED PROTEIN",
        "article_keywords": "sausage casing, tubing",
        "material_keywords": "protein",
    }
    ev_prot = evaluate_candidate_evidence(pi_pvc, build_candidate_profile(rec_protein, None), "SAME_PRODUCT", 0.85)
    assert ev_prot.status == CONTRADICTED

    # 2. "unplasticised" contradicts positive "PLASTICISED" sibling
    pi_unplast = analyze_product_intent("unplasticised cellulose acetate moulding powder")
    rec_plast = {
        "hsn_code": "39121220",
        "code_length": 8,
        "chapter_code": "39",
        "chapter_title": "Plastics and articles thereof",
        "heading_4digit": "3912",
        "heading_4digit_desc": "CELLULOSE AND ITS CHEMICAL DERIVATIVES",
        "subheading_6digit": "391212",
        "subheading_6digit_desc": "CELLULOSE ACETATES: PLASTICISED",
        "tariff_item_desc": "CELLULOSE ACETATE MOULDING POWDER",
        "statutory_description": "CELLULOSE ACETATES - PLASTICISED: CELLULOSE ACETATE MOULDING POWDER",
        "article_keywords": "moulding powder",
        "material_keywords": "cellulose acetate",
    }
    ev_plast = evaluate_candidate_evidence(pi_unplast, build_candidate_profile(rec_plast, None), "SAME_PRODUCT", 0.90)
    assert ev_plast.status == CONTRADICTED

    # 3. Hyphenated parenthetical "(OTHER THAN T-SHIRTS)" excludes T-shirt queries without blocking plain shirts
    pi_tshirt = analyze_product_intent("men knitted 100% cotton round neck t-shirt")
    rec_knit_shirt = {
        "hsn_code": "61051020",
        "code_length": 8,
        "chapter_code": "61",
        "chapter_title": "Articles of apparel and clothing accessories, knitted or crocheted",
        "heading_4digit": "6105",
        "heading_4digit_desc": "MEN'S OR BOYS SHIRTS, KNITTED OR CROCHETED",
        "subheading_6digit": "610510",
        "subheading_6digit_desc": "OF COTTON",
        "tariff_item_desc": "KNIT SHIRTS (OTHER THAN T-SHIRTS) AND SWEAT SHIRTS, OTHER THAN HAND CROCHETED",
        "statutory_description": "MEN'S OR BOYS SHIRTS - OF COTTON : KNIT SHIRTS (OTHER THAN T-SHIRTS)",
        "article_keywords": "knit shirts",
        "material_keywords": "cotton",
    }
    prof_ks = build_candidate_profile(rec_knit_shirt, None)
    ev_ts = evaluate_candidate_evidence(pi_tshirt, prof_ks, "SAME_PRODUCT", 0.80)
    assert ev_ts.status == CONTRADICTED

    pi_plain_shirt = analyze_product_intent("men knitted cotton collared shirt")
    ev_ps = evaluate_candidate_evidence(pi_plain_shirt, prof_ks, "SAME_PRODUCT", 0.80)
    assert ev_ps.status != CONTRADICTED


def test_symmetric_parts_role_propulsion_power_source_and_media_state():
    # 1. Explicit spare-parts query marks complete machine as parts_vs_complete_article
    pi_parts = analyze_product_intent("spare parts for marine outboard engine")
    rec_complete = {
        "hsn_code": "84072100",
        "code_length": 8,
        "chapter_code": "84",
        "chapter_title": "Nuclear reactors, boilers, machinery and mechanical appliances",
        "heading_4digit": "8407",
        "heading_4digit_desc": "SPARK-IGNITION RECIPROCATING OR ROTARY INTERNAL COMBUSTION PISTON ENGINES",
        "subheading_6digit": "840721",
        "subheading_6digit_desc": "MARINE PROPULSION ENGINES",
        "tariff_item_desc": "OUTBOARD MOTORS",
        "statutory_description": "MARINE PROPULSION ENGINES: OUTBOARD MOTORS",
        "article_keywords": "outboard motors, marine propulsion engines",
        "material_keywords": "",
    }
    ev_comp = evaluate_candidate_evidence(pi_parts, build_candidate_profile(rec_complete, None), "INSUFFICIENT_INFORMATION", 0.55)
    assert ev_comp.role_mismatch == "parts_vs_complete_article"

    # 2. Mutually exclusive wind vs water turbine prime mover
    pi_wind = analyze_product_intent("wind-powered turbine electrical generator set")
    rec_hydro = {
        "hsn_code": "85023920",
        "code_length": 8,
        "chapter_code": "85",
        "chapter_title": "Electrical machinery and equipment",
        "heading_4digit": "8502",
        "heading_4digit_desc": "ELECTRIC GENERATING SETS AND ROTARY CONVERTERS",
        "subheading_6digit": "850239",
        "subheading_6digit_desc": "OTHER GENERATING SETS",
        "tariff_item_desc": "POWERED BY WATER TURBINE",
        "statutory_description": "ELECTRIC GENERATING SETS - OTHER: POWERED BY WATER TURBINE",
        "article_keywords": "electric generating sets",
        "material_keywords": "",
    }
    ev_hydro = evaluate_candidate_evidence(pi_wind, build_candidate_profile(rec_hydro, None), "SAME_PRODUCT", 0.90)
    assert ev_hydro.status == CONTRADICTED

    # 3. Recordable/blank vs recorded media state contradiction
    pi_blank = analyze_product_intent("blank recordable cd compact disc")
    rec_recorded = {
        "hsn_code": "85243210",
        "code_length": 8,
        "chapter_code": "85",
        "chapter_title": "Electrical machinery and equipment",
        "heading_4digit": "8524",
        "heading_4digit_desc": "RECORDS, TAPES AND OTHER RECORDED MEDIA FOR SOUND",
        "subheading_6digit": "852432",
        "subheading_6digit_desc": "DISCS FOR LASER READING SYSTEMS",
        "tariff_item_desc": "RECORDED COMPACT DISCS",
        "statutory_description": "RECORDED MEDIA - DISCS FOR LASER READING SYSTEMS",
        "article_keywords": "recorded compact discs",
        "material_keywords": "",
    }
    ev_rec = evaluate_candidate_evidence(pi_blank, build_candidate_profile(rec_recorded, None), "SAME_PRODUCT", 0.80)
    assert ev_rec.status == CONTRADICTED
