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


def test_polymer_specificity_media_whether_recorded_and_with_engine_clause():
    # 1. Specific Ch 39 polymer query contradicts disjoint leaf/subheading polymer
    pi_nylon = analyze_product_intent("recycled nylon polyamide plastic scrap and parings")
    rec_pu = {
        "hsn_code": "39159063",
        "code_length": 8,
        "chapter_code": "39",
        "chapter_title": "Plastics and articles thereof",
        "heading_4digit": "3915",
        "heading_4digit_desc": "WASTE, PARINGS AND SCRAP, OF PLASTICS",
        "subheading_6digit": "391590",
        "subheading_6digit_desc": "OF OTHER PLASTICS",
        "tariff_item_desc": "OF POLYURETHANES",
        "statutory_description": "WASTE, PARINGS AND SCRAP, OF PLASTICS - OF OTHER PLASTICS : OF POLYURETHANES",
        "article_keywords": "plastic scrap",
        "material_keywords": "polyurethane",
    }
    ev_pu = evaluate_candidate_evidence(pi_nylon, build_candidate_profile(rec_pu, None), "SAME_PRODUCT", 0.90)
    assert ev_pu.status == CONTRADICTED

    # 2. "WHETHER OR NOT RECORDED" under Heading 8523 must NOT be contradicted for blank media queries
    pi_smart = analyze_product_intent("blank magnetic stripe plastic smart card")
    rec_card = {
        "hsn_code": "85232920",
        "code_length": 8,
        "chapter_code": "85",
        "chapter_title": "Electrical machinery and equipment",
        "heading_4digit": "8523",
        "heading_4digit_desc": "DISCS, TAPES, SOLID-STATE NON-VOLATILE MEDIA, SMART CARDS, WHETHER OR NOT RECORDED",
        "subheading_6digit": "852329",
        "subheading_6digit_desc": "OTHER",
        "tariff_item_desc": "STORAGE DEVICES, SMART CARDS AND OTHER MEDIA, WHETHER OR NOT RECORDED",
        "statutory_description": "SMART CARDS, WHETHER OR NOT RECORDED",
        "article_keywords": "smart cards",
        "material_keywords": "plastics",
    }
    ev_card = evaluate_candidate_evidence(pi_smart, build_candidate_profile(rec_card, None), "RELATED_PRODUCT", 0.30)
    assert ev_card.status != CONTRADICTED

    # 3. Complete vehicle with secondary "WITH ... PISTON ENGINE" subheading does not claim standalone engine identity
    pi_eng = analyze_product_intent("petrol spark-ignition motorcycle engine 150cc")
    rec_moto = {
        "hsn_code": "87112019",
        "code_length": 8,
        "chapter_code": "87",
        "chapter_title": "Vehicles other than railway or tramway rolling-stock",
        "heading_4digit": "8711",
        "heading_4digit_desc": "MOTORCYCLES (INCLUDING MOPEDS) AND CYCLES FITTED WITH AN AUXILIARY MOTOR",
        "subheading_6digit": "871120",
        "subheading_6digit_desc": "WITH RECIPROCATING INTERNAL COMBUSTION PISTON ENGINE OF A CYLINDER CAPACITY EXCEEDING 50 CC",
        "tariff_item_desc": "OTHER",
        "statutory_description": "MOTORCYCLES WITH RECIPROCATING INTERNAL COMBUSTION PISTON ENGINE: OTHER",
        "article_keywords": "motorcycles",
        "material_keywords": "",
    }
    ev_moto = evaluate_candidate_evidence(pi_eng, build_candidate_profile(rec_moto, None), "SAME_PRODUCT", 0.80)
    assert ev_moto.primary_article_matched is False


def test_parts_heading_alignment_and_cross_sub6_residual_preservation():
    from src.ml.ambiguity_resolver import analyze_sibling_distinctions
    from src.ml.product_tariff_reranker import RerankedTariffCandidate
    from src.ml.relevance_classifier import ClassifiedTariffCandidate, RelationLabel

    # 1. Pure-parts heading (8409 PARTS SUITABLE FOR...) satisfies parts-role alignment when query asks for parts
    pi_part = analyze_product_intent("diesel engine piston assembly spare part")
    rec_piston_assy = {
        "hsn_code": "84099914",
        "code_length": 8,
        "chapter_code": "84",
        "chapter_title": "Nuclear reactors, boilers, machinery and mechanical appliances; parts thereof",
        "heading_4digit": "8409",
        "heading_4digit_desc": "PARTS SUITABLE FOR USE SOLELY OR PRINCIPALLY WITH THE ENGINES OF HEADING 8407 OR 8408",
        "subheading_6digit": "840999",
        "subheading_6digit_desc": "OTHER",
        "tariff_item_desc": "PISTON ASSEMBLIES",
        "statutory_description": "PARTS OF ENGINES: PISTON ASSEMBLIES",
        "article_keywords": "piston assemblies",
        "material_keywords": "",
    }
    ev_assy = evaluate_candidate_evidence(pi_part, build_candidate_profile(rec_piston_assy, None), "RELATED_PRODUCT", 0.40)
    assert ev_assy.primary_article_matched is True
    assert ev_assy.role_mismatch == ""
    assert ev_assy.status != "INSUFFICIENT_EVIDENCE"

    # 2. Cross-subheading residual "OTHER" leaf (e.g. 84219900 parts of filters vs 84219100 parts of centrifuges)
    # must NOT be superseded as a weak same-subheading residual or trigger single-sub6 clear_ev over competing sub6.
    c_9100 = ClassifiedTariffCandidate(
        candidate=RerankedTariffCandidate(
            hsn_code="84219100",
            description="CENTRIFUGES, INCLUDING CENTRIFUGAL DRYERS",
            chapter_code="84",
            chapter_title="Machinery",
            heading_4digit_desc="CENTRIFUGES; FILTERING OR PURIFYING MACHINERY AND APPARATUS",
            subheading_6digit_desc="OF CENTRIFUGES, INCLUDING CENTRIFUGAL DRYERS",
            tariff_item_desc="OF CENTRIFUGES, INCLUDING CENTRIFUGAL DRYERS",
            relevance_score=0.77,
            raw_logit=1.22,
        ),
        relation=RelationLabel.SAME_PRODUCT,
        confidence=0.77,
    )
    c_9900 = ClassifiedTariffCandidate(
        candidate=RerankedTariffCandidate(
            hsn_code="84219900",
            description="OTHER",
            chapter_code="84",
            chapter_title="Machinery",
            heading_4digit_desc="CENTRIFUGES; FILTERING OR PURIFYING MACHINERY AND APPARATUS",
            subheading_6digit_desc="OTHER",
            tariff_item_desc="OTHER",
            relevance_score=0.77,
            raw_logit=1.23,
        ),
        relation=RelationLabel.SAME_PRODUCT,
        confidence=0.77,
    )
    c_9990 = ClassifiedTariffCandidate(
        candidate=RerankedTariffCandidate(
            hsn_code="84219990",
            description="OTHER",
            chapter_code="84",
            chapter_title="Machinery",
            heading_4digit_desc="CENTRIFUGES; FILTERING OR PURIFYING MACHINERY AND APPARATUS",
            subheading_6digit_desc="OTHER",
            tariff_item_desc="OTHER",
            relevance_score=0.78,
            raw_logit=1.24,
        ),
        relation=RelationLabel.SAME_PRODUCT,
        confidence=0.78,
    )
    analysis = analyze_sibling_distinctions(
        [c_9100, c_9900, c_9990],
        "replacement parts for industrial centrifuge filter",
        evidence_by_hsn={
            "84219100": {"status": "SUPPORTED"},
            "84219900": {"status": "POSSIBLY_SUPPORTED"},
            "84219990": {"status": "POSSIBLY_SUPPORTED"},
        },
    )
    assert analysis["winner_has_clear_evidence"] is False
    assert "84219900" not in analysis["statutorily_superseded_hsns"]
    assert "84219990" not in analysis["statutorily_superseded_hsns"]

    # 3. Statutory "- PARTS: OTHER" hierarchy rows (e.g. 84219900) recognize parts role cleanly
    pi_filter_part = analyze_product_intent("replacement parts for industrial centrifuge filter")
    rec_filter_part = {
        "hsn_code": "84219900",
        "code_length": 8,
        "chapter_code": "84",
        "chapter_title": "Nuclear reactors, boilers, machinery and mechanical appliances; parts thereof",
        "heading_4digit": "8421",
        "heading_4digit_desc": "CENTRIFUGES, INCLUDING CENTRIFUGAL DRYERS; FILTERING OR PURIFYING MACHINERY AND APPARATUS",
        "subheading_6digit": "842199",
        "subheading_6digit_desc": "OTHER",
        "tariff_item_desc": "OTHER",
        "statutory_description": "CENTRIFUGES, INCLUDING CENTRIFUGAL DRYERS; FILTERING OR PURIFYING MACHINERY AND APPARATUS - PARTS: OTHER",
        "article_keywords": "centrifuges filtering machinery - parts: other",
        "material_keywords": "",
    }
    ev_filter_part = evaluate_candidate_evidence(pi_filter_part, build_candidate_profile(rec_filter_part, None), "SAME_PRODUCT", 0.77)
    assert ev_filter_part.role_mismatch == ""
    assert ev_filter_part.primary_article_matched is True


def test_hierarchical_multi_level_decision_and_statutory_exclusions():
    from src.ml.stage3_statutory_verifier import build_stage3_final_decision

    # 1. Trailing specification noun ("150 kg capacity") must not hijack product_head_noun
    pi_scale = analyze_product_intent("electronic platform weighing scale 150 kg capacity")
    assert pi_scale.product_head_noun.lower() == "scale"

    # 2. Hyphenated material ("MAN-MADE FIBRES") contradicts cotton queries
    pi_cotton = analyze_product_intent("knitted cotton headband clothing accessory")
    rec_manmade = {
        "hsn_code": "61178040",
        "code_length": 8,
        "chapter_code": "61",
        "chapter_title": "Articles of apparel and clothing accessories, knitted or crocheted",
        "heading_4digit": "6117",
        "heading_4digit_desc": "OTHER MADE UP CLOTHING ACCESSORIES, KNITTED OR CROCHETED",
        "subheading_6digit": "611780",
        "subheading_6digit_desc": "OTHER ACCESSORIES",
        "tariff_item_desc": "OF MAN-MADE FIBRES",
        "statutory_description": "OTHER ACCESSORIES : OF MAN-MADE FIBRES",
        "article_keywords": "headband accessory",
        "material_keywords": "",
    }
    ev_manmade = evaluate_candidate_evidence(pi_cotton, build_candidate_profile(rec_manmade, None), "SAME_PRODUCT", 0.90)
    assert ev_manmade.status == CONTRADICTED

    # 3. Heading participle exclusion ("AND NOT REINFORCED, LAMINATED, SUPPORTED") contradicts laminated sheets
    pi_lam = analyze_product_intent("multi-layer laminated plastic sheet for industrial use")
    rec_3920 = {
        "hsn_code": "39209942",
        "code_length": 8,
        "chapter_code": "39",
        "chapter_title": "Plastics and articles thereof",
        "heading_4digit": "3920",
        "heading_4digit_desc": "OTHER PLATES, SHEETS, FILM, FOIL AND STRIP, OF PLASTICS, NON-CELLULAR AND NOT REINFORCED, LAMINATED, SUPPORTED OR SIMILARLY COMBINED WITH OTHER MATERIALS",
        "subheading_6digit": "392099",
        "subheading_6digit_desc": "OF OTHER PLASTICS",
        "tariff_item_desc": "FLEXIBLE, PLAIN",
        "statutory_description": "OTHER PLATES, SHEETS, OF PLASTICS: FLEXIBLE, PLAIN",
        "article_keywords": "plastic sheet",
        "material_keywords": "plastics",
    }
    assert evaluate_candidate_evidence(pi_lam, build_candidate_profile(rec_3920, None), "SAME_PRODUCT", 0.80).status == CONTRADICTED

    # 4. Heading exclusion with trailing period ("OTHER THAN VACUUM CLEANERS OF HEADING 8508.")
    pi_vac = analyze_product_intent("electric canister vacuum cleaner for home")
    rec_8509 = {
        "hsn_code": "85091000",
        "code_length": 8,
        "chapter_code": "85",
        "chapter_title": "Electrical machinery",
        "heading_4digit": "8509",
        "heading_4digit_desc": "ELECTRO-MECHANICAL DOMESTIC APPLIANCES, WITH SELF CONTAINED ELECTRIC MOTOR, OTHER THAN VACUUM CLEANERS OF HEADING 8508.",
        "subheading_6digit": "",
        "subheading_6digit_desc": "",
        "tariff_item_desc": "VACUUM CLEANERS, INCLUDING DRY AND WET VACUUM CLEANERS",
        "statutory_description": "ELECTRO-MECHANICAL DOMESTIC APPLIANCES VACUUM CLEANERS",
        "article_keywords": "vacuum cleaner",
        "material_keywords": "",
    }
    assert evaluate_candidate_evidence(pi_vac, build_candidate_profile(rec_8509, None), "SAME_PRODUCT", 0.85).status == CONTRADICTED

    # 5. Epoxide spaced hyphen & PET / acetatc typo polymer contradictions
    pi_poly = analyze_product_intent("recycled nylon polyamide plastic scrap and parings")
    rec_pet = {
        "hsn_code": "39159042",
        "code_length": 8,
        "chapter_code": "39",
        "chapter_title": "Plastics and articles thereof",
        "heading_4digit": "3915",
        "heading_4digit_desc": "WASTE, PARINGS AND SCRAP, OF PLASTICS",
        "subheading_6digit": "391590",
        "subheading_6digit_desc": "OF OTHER PLASTICS",
        "tariff_item_desc": "OF PET BOTTLES",
        "statutory_description": "WASTE, PARINGS AND SCRAP: OF PET BOTTLES",
        "article_keywords": "plastic scrap",
        "material_keywords": "pet",
    }
    assert evaluate_candidate_evidence(pi_poly, build_candidate_profile(rec_pet, None), "SAME_PRODUCT", 0.85).status == CONTRADICTED

    # 6. Multi-level Stage 3 hierarchical outputs maintain strict prefix consistency
    s3_sub6 = build_stage3_final_decision(
        original_description="retail fuel dispensing pump for petrol station",
        prediction_mode="CHAPTER_ONLY_CLARIFY",
        final_hsn=None,
        final_chapter="84",
        final_heading="8413",
        final_subheading="841311",
        prediction_level="SUBHEADING_6DIGIT",
        hsn_confidence=0.18,
        clarification_reason="Subheading 841311 supported.",
        product_intent=analyze_product_intent("retail fuel dispensing pump for petrol station"),
        qualifying_leaves=[],
        evidence_by_hsn={},
        raw_records_by_id={},
        dist_analysis={},
        questions=[{"attribute": "pump_type", "question": "Hand pump or metered dispenser?", "options": ["Hand", "Dispenser"]}],
        contradicted_reasons=[],
    )
    assert s3_sub6["prediction_level"] == "SUBHEADING_6DIGIT"
    assert s3_sub6["predicted_hsn"] == "841311"
    assert s3_sub6["final_subheading"] == "841311"
    assert s3_sub6["final_heading"] == "8413"
    assert s3_sub6["final_chapter"] == "84"
    assert s3_sub6["final_hsn"] is None
    assert s3_sub6["verified_gst_rate"] is None
    assert s3_sub6["decision_outcome"] == "CUSTOMER_CLARIFICATION_REQUIRED"

    # 7. Spec-qualified prime-mover head noun vs secondary-with-feature guard
    pi_car = analyze_product_intent("petrol passenger sedan car 1200cc engine")
    assert pi_car.product_head_noun.lower() == "car"

    pi_eng = analyze_product_intent("motorcycle engine 150cc")
    assert pi_eng.product_head_noun.lower() == "engine"
    rec_8711 = {
        "hsn_code": "87112019",
        "code_length": 8,
        "chapter_code": "87",
        "chapter_title": "Vehicles other than railway or tramway rolling-stock",
        "heading_4digit": "8711",
        "heading_4digit_desc": "MOTORCYCLES (INCLUDING MOPEDS) AND CYCLES FITTED WITH AN AUXILIARY MOTOR, WITH OR WITHOUT SIDE-CARS; SIDE-CARS",
        "subheading_6digit": "871120",
        "subheading_6digit_desc": "WITH RECIPROCATING INTERNAL COMBUSTION PISTON ENGINE OF A CYLINDER CAPACITY EXCEEDING 50 CC BUT NOT EXCEEDING 250 CC",
        "tariff_item_desc": "MOTORCYCLES",
        "statutory_description": "MOTORCYCLES WITH RECIPROCATING INTERNAL COMBUSTION PISTON ENGINE",
        "article_keywords": "motorcycle",
        "material_keywords": "",
    }
    ev_8711 = evaluate_candidate_evidence(pi_eng, build_candidate_profile(rec_8711, None), "SAME_PRODUCT", 0.85)
    assert "guard=secondary_with_feature" in ev_8711.trace_summary

    pi_fastener = analyze_product_intent("galvanized mild steel fastener bolt")
    rec_7318 = {
        "hsn_code": "73181190",
        "code_length": 8,
        "chapter_code": "73",
        "chapter_title": "Articles of iron or steel",
        "heading_4digit": "7318",
        "heading_4digit_desc": "SCREWS, BOLTS, NUTS, COACH SCREWS, SCREW HOOKS, RIVETS, COTTERS, COTTER-PINS, WASHERS AND SIMILAR ARTICLES, OF IRON OR STEEL",
        "subheading_6digit": "731811",
        "subheading_6digit_desc": "COACH SCREWS",
        "tariff_item_desc": "OTHER",
        "statutory_description": "SCREWS, BOLTS, NUTS - COACH SCREWS: OTHER",
        "article_keywords": "screws, bolts",
        "material_keywords": "iron or steel",
    }
    ev_7318 = evaluate_candidate_evidence(pi_fastener, build_candidate_profile(rec_7318, None), "INSUFFICIENT_INFORMATION", 0.70)
    assert "guard=secondary_with_feature" not in ev_7318.trace_summary

