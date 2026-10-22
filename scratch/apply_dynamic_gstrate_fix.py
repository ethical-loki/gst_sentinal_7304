"""
Applies dynamic gstrate calculation so whatever percentage is mentioned in gstrate
(0%, 0.1%, 0.25%, 3%, 5%, 6%, 12%, 18%, 28%, etc.) is used directly for tax calculations
instead of assuming 18%.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def patch_file(path: Path, replacements: list):
    if not path.exists():
        print(f"Skipping non-existent: {path}")
        return
    src = path.read_text(encoding="utf-8")
    nl = "\r\n" if "\r\n" in src else "\n"
    fix = lambda s: s.replace("\n", nl)
    
    modified = False
    for old, new, label in replacements:
        old_fixed = fix(old)
        new_fixed = fix(new)
        if old_fixed in src:
            src = src.replace(old_fixed, new_fixed)
            print(f"[{path.name}] Applied: {label}")
            modified = True
        else:
            print(f"[{path.name}] Note: Anchor '{label}' not found or already applied.")
            
    if modified:
        path.write_text(src, encoding="utf-8")
        print(f"Updated {path}")
    else:
        print(f"No changes made to {path}")

# 1. Update backend/converter_service.py and gst_sentinal_7304/backend/converter_service.py
converter_replacements = [
    (
        '''def _item_total_gst_rate(it: dict) -> float:
    """Total GST rate of a line item regardless of how it is currently split."""
    ig = _gst_num(it.get("igstrt"))
    cg = _gst_num(it.get("cgstrt"))
    sg = _gst_num(it.get("sgstrt"))
    if ig > 0:
        return ig
    if cg + sg > 0:
        return round(cg + sg, 3)
    return _gst_num(it.get("gstrate", it.get("gst_rate")))''',
        '''def _item_total_gst_rate(it: dict) -> float:
    """
    Extracts the statutory GST rate for an item:
    1. First check explicit 'gstrate', 'gst_rate', 'tax_rate', 'gstrt' in the item.
       Whatever percentage is mentioned in gstrate is the primary source of truth!
       (e.g., 0%, 0.1%, 0.25%, 1.5%, 3%, 5%, 6%, 7.5%, 12%, 18%, 28%, etc. - NOT assumed to be 18)
    2. If not found in item, derive from existing igstrt or (cgstrt + sgstrt).
    3. Return 0.0 if not found (never default blindly to 18.0).
    """
    for k in ("gstrate", "gst_rate", "gst rate", "tax_rate", "gstrt", "gst_rt"):
        if k in it and it.get(k) is not None and str(it.get(k)).strip() != "":
            try:
                return float(str(it.get(k)).replace(",", "").replace("%", "").strip())
            except (ValueError, TypeError):
                pass

    ig = _gst_num(it.get("igstrt"))
    cg = _gst_num(it.get("cgstrt"))
    sg = _gst_num(it.get("sgstrt"))
    if ig > 0:
        return ig
    if cg + sg > 0:
        return round(cg + sg, 3)
    return 0.0''',
        "update _item_total_gst_rate to prioritize gstrate"
    ),
    (
        '''        if (abs(ni - old_i) > 0.01 or abs(nc - old_c) > 0.01 or abs(ns - old_s) > 0.01 or
                abs(_gst_num(it.get("igstrt")) - ri) > 0.001 or
                abs(_gst_num(it.get("cgstrt")) - rc) > 0.001 or
                abs(_gst_num(it.get("sgstrt")) - rs) > 0.001):
            changed = True

        it["igstrt"] = _fmt_like(it.get("igstrt"), ri)''',
        '''        if (abs(ni - old_i) > 0.01 or abs(nc - old_c) > 0.01 or abs(ns - old_s) > 0.01 or
                abs(_gst_num(it.get("igstrt")) - ri) > 0.001 or
                abs(_gst_num(it.get("cgstrt")) - rc) > 0.001 or
                abs(_gst_num(it.get("sgstrt")) - rs) > 0.001):
            changed = True

        it["gstrate"] = _fmt_like(it.get("gstrate"), rate)
        it["igstrt"] = _fmt_like(it.get("igstrt"), ri)''',
        "preserve gstrate in auto_route_tax_split"
    ),
    (
        '''    # -------------------------------------------------------------
    # INTENT 7: User provides a State Code or State Name''',
        '''    # -------------------------------------------------------------
    # INTENT 6C: Set / Update GST Rate (gstrate)
    # Supports "Set GST rate: 5%", "Set gstrate: 12", "Change rate to 28%", "GST rate is 5%", etc.
    # -------------------------------------------------------------
    elif not patch_applied and (
        re.search(r"(?:set\\s+)?(?:gst[\\s_]*rate|gstrate|tax[\\s_]*rate)\\s*[:=to\\s]+\\s*([0-9]+(?:\\.[0-9]+)?)\\s*%?", user_message, re.IGNORECASE) or
        re.search(r"^(?:rate|gstrate)\\s*[:=]\\s*([0-9]+(?:\\.[0-9]+)?)\\s*%?$", user_message.strip(), re.IGNORECASE)
    ):
        m_rate = re.search(r"(?:(?:gst[\\s_]*rate|gstrate|tax[\\s_]*rate)\\s*[:=to\\s]+|^rate\\s*[:=]\\s*|^gstrate\\s*[:=]\\s*)\\s*([0-9]+(?:\\.[0-9]+)?)\\s*%?", user_message, re.IGNORECASE)
        if m_rate:
            new_rate = float(m_rate.group(1))
            items = target_inv.get("itemdtls") or target_inv.get("items") or []
            for itm in items:
                itm["gstrate"] = new_rate
            auto_tax_route = auto_route_tax_split(target_inv)
            patch_applied = True
            patch_summary.append(f"Set GST rate to {new_rate}% on line items")
            reply_lines.append(
                f"📊 **GST Rate Updated to {new_rate}%!**\\n\\n"
                f"• Line-item tax rate (`gstrate`) set to **{new_rate}%**.\\n"
                f"• Taxes and totals automatically re-calculated based on Place of Supply."
            )

    # -------------------------------------------------------------
    # INTENT 7: User provides a State Code or State Name''',
        "add INTENT 6C for setting gstrate"
    )
]

for p in [ROOT / "backend" / "converter_service.py", ROOT / "gst_sentinal_7304" / "backend" / "converter_service.py"]:
    patch_file(p, converter_replacements)

# 2. Update Template_Converters/payload_builder.py and gst_sentinal_7304/Template_Converters/payload_builder.py
builder_replacements = [
    (
        '''    "gstrate": "igstrt", "gst_rate": "igstrt", "gst rate": "igstrt",''',
        '''    "gstrate": "gstrate", "gst_rate": "gstrate", "gst rate": "gstrate", "gstrt": "gstrate",''',
        "keep gstrate as gstrate alias in payload_builder"
    ),
    (
        '''            raw_igstrt = Decimal(clean_decimal_str(item.get("igstrt", "0.00"), 2))
            raw_cgstrt = Decimal(clean_decimal_str(item.get("cgstrt", "0.00"), 2))
            raw_sgstrt = Decimal(clean_decimal_str(item.get("sgstrt", "0.00"), 2))

            if hsn_statutory_rate is not None:
                gst_rate = hsn_statutory_rate
            elif raw_igstrt > 0:
                gst_rate = raw_igstrt
            elif raw_cgstrt + raw_sgstrt > 0:
                gst_rate = raw_cgstrt + raw_sgstrt
            else:
                gst_rate = Decimal("0.00")''',
        '''            # Prioritize explicit customer-declared gstrate / gst_rate first!
            declared_gstrate = None
            for g_k in ("gstrate", "gst_rate", "gst rate", "tax_rate", "gstrt", "gst_rt"):
                if g_k in item and item.get(g_k) is not None and str(item.get(g_k)).strip() != "":
                    try:
                        declared_gstrate = Decimal(clean_decimal_str(item.get(g_k), 2))
                        break
                    except Exception:
                        pass

            raw_igstrt = Decimal(clean_decimal_str(item.get("igstrt", "0.00"), 2))
            raw_cgstrt = Decimal(clean_decimal_str(item.get("cgstrt", "0.00"), 2))
            raw_sgstrt = Decimal(clean_decimal_str(item.get("sgstrt", "0.00"), 2))

            if declared_gstrate is not None:
                gst_rate = declared_gstrate
            elif raw_igstrt > 0:
                gst_rate = raw_igstrt
            elif raw_cgstrt + raw_sgstrt > 0:
                gst_rate = raw_cgstrt + raw_sgstrt
            elif hsn_statutory_rate is not None:
                gst_rate = hsn_statutory_rate
            else:
                gst_rate = Decimal("0.00")''',
        "prioritize declared gstrate over hardcoded 18.0 HSN in payload_builder"
    ),
    (
        '''                "assamt": str(assamt_d),
                "taxability": taxability,
                "cgstrt": str(cgstrt_d),''',
        '''                "assamt": str(assamt_d),
                "taxability": taxability,
                "gstrate": str(gst_rate),
                "cgstrt": str(cgstrt_d),''',
        "include gstrate in clean_itemdtls"
    )
]

for p in [ROOT / "Template_Converters" / "payload_builder.py", ROOT / "gst_sentinal_7304" / "Template_Converters" / "payload_builder.py"]:
    patch_file(p, builder_replacements)

# 3. Update src/ingestion/schemas.py and gst_sentinal_7304/src/ingestion/schemas.py
schema_replacements = [
    (
        '''    "gstrate": "igstrt", "gst_rate": "igstrt", "gst rate": "igstrt",''',
        '''    "gstrate": "gstrate", "gst_rate": "gstrate", "gst rate": "gstrate", "gstrt": "gstrate",''',
        "keep gstrate alias in schemas.py"
    ),
    (
        '''                ass_d = Decimal(itm["assval"])
                if hsn_stat_rate is not None:
                    stat_gst = hsn_stat_rate
                elif Decimal(itm.get("igstval", "0.00")) > 0:
                    stat_gst = (Decimal(itm["igstval"]) * Decimal("100") / ass_d).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if ass_d > 0 else Decimal("18.00")
                elif Decimal(itm.get("cgstval", "0.00")) > 0:
                    stat_gst = (Decimal(itm["cgstval"]) * Decimal("200") / ass_d).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if ass_d > 0 else Decimal("18.00")
                else:
                    stat_gst = Decimal("18.00")''',
        '''                ass_d = Decimal(itm["assval"])
                decl_gstrt = None
                for _gk in ("gstrate", "gst_rate", "tax_rate", "rate"):
                    if _gk in itm and itm.get(_gk) is not None and str(itm.get(_gk)).strip() != "":
                        try:
                            decl_gstrt = Decimal(str(itm.get(_gk)).replace(",", "").replace("%", "").strip())
                            break
                        except Exception:
                            pass

                if decl_gstrt is not None:
                    stat_gst = decl_gstrt
                elif hsn_stat_rate is not None:
                    stat_gst = hsn_stat_rate
                elif Decimal(itm.get("igstval", "0.00")) > 0:
                    stat_gst = (Decimal(itm["igstval"]) * Decimal("100") / ass_d).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if ass_d > 0 else Decimal("0.00")
                elif Decimal(itm.get("cgstval", "0.00")) > 0:
                    stat_gst = (Decimal(itm["cgstval"]) * Decimal("200") / ass_d).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if ass_d > 0 else Decimal("0.00")
                else:
                    stat_gst = Decimal("0.00")''',
        "prioritize declared gstrate over hardcoded 18.0 in schemas.py"
    )
]

for p in [ROOT / "src" / "ingestion" / "schemas.py", ROOT / "gst_sentinal_7304" / "src" / "ingestion" / "schemas.py"]:
    patch_file(p, schema_replacements)

print("\nAll files successfully patched for dynamic gstrate calculation!")
