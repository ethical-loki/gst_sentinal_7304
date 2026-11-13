# Master Tariff Dataset Quality Audit Report

**Source File**: `data/raw/Master_copy_hsn.xlsx`  
**Total Tariff Lines**: 4851  
**Total Active Chapters**: 9  

## 1. Executive Summary

- **Truncated Descriptions Identified**: 124 rows  
- **Duplicate Description Groups (Shared text across different codes)**: 228 groups affecting 1362 rows  
- **Missing Value Count**: 0  

## 2. Chapter & Heading Coverage

| Chapter | Chapter Title | Unique 4-Digit Headings | Total Tariff Lines |
| :--- | :--- | :--- | :--- |
| Ch 19 | Preparations of cereals, flour, starch or milk; pastrycooks products | 5 | 51 |
| Ch 39 | Plastics and articles thereof | 26 | 577 |
| Ch 61 | Articles of apparel and clothing accessories, knitted or crocheted | 17 | 290 |
| Ch 62 | Articles of apparel and clothing accessories, not knitted or crocheted | 17 | 434 |
| Ch 73 | Articles of iron or steel | 26 | 404 |
| Ch 84 | Nuclear reactors, boilers, machinery and mechanical appliances; parts thereof | 87 | 1526 |
| Ch 85 | Electrical machinery and equipment and parts thereof; sound recorders and reproducers, television image and sound recorders and reproducers, and parts and accessories of such articles | 49 | 1095 |
| Ch 87 | Vehicles other than railway or tramway rolling-stock, and parts and accessories thereof | 16 | 336 |
| Ch 94 | Furniture; bedding, mattresses, mattress supports, cushions and similar stuffed furnishing; lamps and lighting fittings, not elsewhere specified or included; illuminated signs, illuminated name-plates and the like; prefabricated building | 6 | 138 |

## 3. Duplicate Description Collision Analysis

When two distinct 8-digit tariff items share the exact same statutory description, the decision engine must disambiguate them using keyword attributes rather than confusing the user with identical cards.

| Colliding Codes | Shared Statutory Description | Disambiguation Strategy |
| :--- | :--- | :--- |
| `1901, 19011010, 19011090, 19012000` | MALT EXTRACT; FOOD PREPARATIONS OF FLOUR, GROATS, MEAL, STARCH OR... | Disambiguate via `Article Keywords` & 8-digit leaf spec |
| `19021100, 19021900` | PASTA, WHETHER OR NOT COOKED OR STUFFED (WITH MEAT OR OTHER SUBST... | Disambiguate via `Article Keywords` & 8-digit leaf spec |
| `1903, 19030000` | TAPIOCA AND SUBSTITUTES THEREFOR PREPARED FROM STARCH, IN THE FOR... | Disambiguate via `Article Keywords` & 8-digit leaf spec |
| `19041010, 19041020, 19041030, 19041090` | PREPARED FOODS OBTAINED BY THE SWELLING OR ROASTING OF CEREALS OR... | Disambiguate via `Article Keywords` & 8-digit leaf spec |
| `19053211, 19059051` | COATED WITH CHOCOLATE OR CONTAINING CHOCOLATE | Disambiguate via `Article Keywords` & 8-digit leaf spec |
| `390140, 39014000` | ETHYLENE-ALPHA-OLEFIN COPOLYMERS, HAVING A SPECIFIC GRAVITY OF LE... | Disambiguate via `Article Keywords` & 8-digit leaf spec |
| `390421, 39042100, 391211` | NON-PLASTICISED | Disambiguate via `Article Keywords` & 8-digit leaf spec |
| `390422, 39042200, 391212` | PLASTICISED | Disambiguate via `Article Keywords` & 8-digit leaf spec |
| `39051210, 39051220, 39051290` | POLYMERS OF VINYL ACETATE OR OF OTHER VINYL ESTERS, IN PRIMARY FO... | Disambiguate via `Article Keywords` & 8-digit leaf spec |
| `39051910, 39051920` | POLYMERS OF VINYL ACETATE OR OF OTHER VINYL ESTERS, IN PRIMARY FO... | Disambiguate via `Article Keywords` & 8-digit leaf spec |
| `390761, 39076100` | HAVING A VISCOSITY NUMBER OF 78 ML/G OR HIGHER | Disambiguate via `Article Keywords` & 8-digit leaf spec |
| `39076110, 39076930` | PET FLAKE (CHIP) | Disambiguate via `Article Keywords` & 8-digit leaf spec |
| `39076190, 39076990, 39081019, 39081029` | OTHER PRIMARY FORM | Disambiguate via `Article Keywords` & 8-digit leaf spec |
| `39081011, 39081021, 39081031, 39081041` | FLAKE (CHIP) | Disambiguate via `Article Keywords` & 8-digit leaf spec |
| `3910, 391000` | SILICONES IN PRIMARY FORMS | Disambiguate via `Article Keywords` & 8-digit leaf spec |
| `39111010, 39111090` | PETROLEUM RESINS, COUMARONE - INDENE RESINS, POLYTERPENES, POLYSU... | Disambiguate via `Article Keywords` & 8-digit leaf spec |
| `391530, 391620, 391723, 391810` | OF POLYMERS OF VINYL CHLORIDE | Disambiguate via `Article Keywords` & 8-digit leaf spec |
| `391590, 391690, 391729, 391890` | OF OTHER PLASTICS | Disambiguate via `Article Keywords` & 8-digit leaf spec |
| `391610, 391721` | OF POLYMERS OF ETHYLENE | Disambiguate via `Article Keywords` & 8-digit leaf spec |
| `39169021, 39169022, 39169023, 39169024` | MONOFILAMENT OF WHICH ANY CROSS - SECTIONAL DIMENSION EXCEEDS 1MM... | Disambiguate via `Article Keywords` & 8-digit leaf spec |

## 4. Notable Truncated Statutory Text Entries

The following rows in the Master Excel file were clipped or truncated during source ingestion:

| HSN Code | Chapter | Truncated Description Snippet | Diagnostic Notes |
| :--- | :--- | :--- | :--- |
| `3903` | Ch 39 | `...POLYMERS OF STYRENE, IN PRIMARY FORMS - POLYSTYRENE:` | Matched pattern ':\s*$' |
| `3905` | Ch 39 | `...HER VINYL POLYMERS IN PRIMARY FORMS - POLY (VINYL ACETATE) :` | Matched pattern ':\s*$' |
| `3906` | Ch 39 | `...YLIC POLYMERS IN PRIMARY FORMS - POLY (METHYL METHACRYLATE):` | Matched pattern ':\s*$' |
| `3912` | Ch 39 | `...ECIFIED OR INCLUDED, IN PRIMARY FORMS - CELLULOSE ACETATES :` | Matched pattern ':\s*$' |
| `391239` | Ch 39 | `...OTHER -` | Matched pattern '[A-Z]{3,}\s*-\s*$'; Matched pattern '-\s*$' |
| `39139020` | Ch 39 | `...Y FORMS - OTHER :HARDENED PROTEINS (SUCH AS HARDENED CASEIN,` | Suspect truncated trailing token: 'CASEIN' |
| `3917` | Ch 39 | `...AGE CASINGS) OF HARDENED PROTEIN OR OF CELLULOSIC MATERIALS:` | Matched pattern ':\s*$' |
| `39207311` | Ch 39 | `...VES: OF CELLULOSE ACETATE: SHEET OF CELLULOSE ACETATE, NON -` | Matched pattern '[A-Z]{3,}\s*-\s*$'; Matched pattern '-\s*$' |
| `39207312` | Ch 39 | `...VES: OF CELLULOSE ACETATE: SHEET OF CELLULOSE ACETATE, NON -` | Matched pattern '[A-Z]{3,}\s*-\s*$'; Matched pattern '-\s*$' |
| `39207319` | Ch 39 | `...VES: OF CELLULOSE ACETATE: SHEET OF CELLULOSE ACETATE, NON -` | Matched pattern '[A-Z]{3,}\s*-\s*$'; Matched pattern '-\s*$' |
| `3921` | Ch 39 | `...ATES, SHEETS, FILM, FOIL AND STRIP, OF PLASTICS - CELLULAR :` | Matched pattern ':\s*$' |
| `620120` | Ch 62 | `...OF WOOL OR FINE ANIMAL HAIR :` | Matched pattern ':\s*$' |
| `620140` | Ch 62 | `...OF MAN-MADE FIBRES :` | Matched pattern ':\s*$' |
| `620190` | Ch 62 | `...OF OTHER TEXTILE MATERIALS :` | Matched pattern ':\s*$' |
| `620220` | Ch 62 | `...OF WOOL OR FINE ANIMAL HAIR :` | Matched pattern ':\s*$' |
| `620240` | Ch 62 | `...OF MAN-MADE FIBRES :` | Matched pattern ':\s*$' |
| `620290` | Ch 62 | `...OF OTHER TEXTILE MATERIALS :` | Matched pattern ':\s*$' |
| `620412` | Ch 62 | `...OF COTTON:` | Matched pattern ':\s*$' |
| `620413` | Ch 62 | `...OF SYNTHETIC FIBRES:` | Matched pattern ':\s*$' |
| `620432` | Ch 62 | `...OF COTTON:` | Matched pattern ':\s*$' |
| `620433` | Ch 62 | `...OF SYNTHETIC FIBRE:` | Matched pattern ':\s*$' |
| `620444` | Ch 62 | `...OF ARTIFICIAL FIBRES :` | Matched pattern ':\s*$' |
| `620452` | Ch 62 | `...OF COTTON :` | Matched pattern ':\s*$' |
| `620453` | Ch 62 | `...OF SYNTHETIC FIBRE :` | Matched pattern ':\s*$' |
| `620530` | Ch 62 | `...OF MAN-MADE FIBRES:` | Matched pattern ':\s*$' |

## 5. Field Completeness

| Field Name | Missing Records | Status |
| :--- | :--- | :--- |
| `HSN Code` | 0 | ✅ Complete |
| `chapter_code` | 0 | ✅ Complete |
| `chapter_title` | 0 | ✅ Complete |
| `HSN Description` | 0 | ✅ Complete |
| `Article Keywords` | 0 | ✅ Complete |
| `Material Keywords` | 0 | ✅ Complete |

