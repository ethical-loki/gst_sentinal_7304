"""Patch both converter_service.py copies with automatic GSTIN-based tax split routing."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGETS = [ROOT / "backend" / "converter_service.py",
           ROOT / "gst_sentinal_7304" / "backend" / "converter_service.py"]

HELPER = '''def _gst_num(v: Any) -> float:
    """Safely parse a numeric GST field (accepts str/int/float, strips commas)."""
    if v is None or v == "":
        return 0.0
    try:
        return float(str(v).replace(",", "").strip())
    except (ValueError, TypeError):
        return 0.0


def _item_total_gst_rate(it: dict) -> float:
    """Total GST rate of a line item regardless of how it is currently split."""
    ig = _gst_num(it.get("igstrt"))
    cg = _gst_num(it.get("cgstrt"))
    sg = _gst_num(it.get("sgstrt"))
    if ig > 0:
        return ig
    if cg + sg > 0:
        return round(cg + sg, 3)
    return _gst_num(it.get("gstrate", it.get("gst_rate")))


def _fmt_like(old: Any, new: float, nd: int = 2) -> Any:
    """Write a number back using the same type (string vs number) as the original field."""
    return f"{new:.{nd}f}" if isinstance(old, str) or old is None else round(new, nd)


def auto_route_tax_split(inv: dict) -> Optional[Dict[str, Any]]:
    """
    Automatically routes GST on every line item based on Supplier GSTIN vs Buyer GSTIN / POS:
      - Supplier state = first 2 digits of Supplier GSTIN (fallback supplier_state).
      - POS = declared POS, else derived from Buyer GSTIN prefix (fallback buyer_state).
      - Interstate (supplier != POS), Export, SEZ or IGST-on-intra  -> IGST only.
      - Intrastate (supplier == POS)                                 -> CGST + SGST (rate / 2 each).
    Recomputes item tax amounts, totitemval and invoice-level totals (valdtls / valdt1 / top-level).
    Returns a summary dict ({"changed": bool, ...}) or None when states cannot be resolved.
    """
    if not isinstance(inv, dict):
        return None
    supp_dt = inv.get("supplierdt1") if isinstance(inv.get("supplierdt1"), dict) else {}
    buyer_dt = inv.get("buyerdt1") if isinstance(inv.get("buyerdt1"), dict) else {}
    tran_dt = inv.get("trandt1") if isinstance(inv.get("trandt1"), dict) else {}

    sup_gstin = str(supp_dt.get("supplier_gstin") or inv.get("supplier_gstin") or inv.get("self_gstin") or "").strip().upper()
    buy_gstin = str(buyer_dt.get("buyer_gstin") or inv.get("buyer_gstin") or "").strip().upper()

    if len(sup_gstin) >= 2 and sup_gstin[:2].isdigit():
        sup_st = sup_gstin[:2]
    else:
        raw_ss = str(supp_dt.get("supplier_state") or inv.get("supplier_state") or "").strip()
        sup_st = raw_ss.zfill(2) if raw_ss.isdigit() else ""

    trancatg = str(tran_dt.get("trancatg") or inv.get("trancatg") or "B2B").strip().upper()
    is_export = trancatg in ("EXP", "EXPWP", "EXPWOP")
    is_sez = trancatg in ("SEZWP", "SEZWOP")
    igst_intra = str(tran_dt.get("igstonintra") or inv.get("igstonintra") or inv.get("igst_on_intra") or "N").strip().upper() == "Y"

    buyer_prefix = buy_gstin[:2] if (buy_gstin != "URP" and len(buy_gstin) >= 2 and buy_gstin[:2].isdigit()) else ""
    raw_pos = str(buyer_dt.get("pos") or inv.get("pos") or "").strip()
    pos = raw_pos.zfill(2) if raw_pos.isdigit() else ""
    pos_derived = False
    if not pos:
        if is_export:
            pos = "96"
        else:
            raw_bs = str(buyer_dt.get("buyer_state") or inv.get("buyer_state") or "").strip()
            pos = buyer_prefix or (raw_bs.zfill(2) if raw_bs.isdigit() else "")
        if pos:
            pos_derived = True
            if buyer_dt or "buyerdt1" in inv:
                inv.setdefault("buyerdt1", {})["pos"] = pos
            else:
                inv["pos"] = pos

    if not sup_st or not pos:
        return None

    is_interstate = bool(is_export or is_sez or igst_intra or sup_st != pos)
    items = inv.get("itemdtls") or inv.get("items") or []
    changed = False
    tot_i = tot_c = tot_s = 0.0

    for it in items:
        if not isinstance(it, dict):
            continue
        rate = _item_total_gst_rate(it)
        ass = _gst_num(it.get("assamt") or it.get("assval") or it.get("pretaxval") or it.get("taxable_value"))
        old_i = _gst_num(it.get("igstamt", it.get("igstval")))
        old_c = _gst_num(it.get("cgstamt", it.get("cgstval")))
        old_s = _gst_num(it.get("sgstamt", it.get("sgstval")))

        if is_interstate:
            ri, rc, rs = rate, 0.0, 0.0
            ni, nc, ns = round(ass * rate / 100.0, 2), 0.0, 0.0
        else:
            half = round(rate / 2.0, 3)
            ri, rc, rs = 0.0, half, half
            nc = round(ass * half / 100.0, 2)
            ni, ns = 0.0, nc

        if (abs(ni - old_i) > 0.01 or abs(nc - old_c) > 0.01 or abs(ns - old_s) > 0.01 or
                abs(_gst_num(it.get("igstrt")) - ri) > 0.001 or
                abs(_gst_num(it.get("cgstrt")) - rc) > 0.001 or
                abs(_gst_num(it.get("sgstrt")) - rs) > 0.001):
            changed = True

        it["igstrt"] = _fmt_like(it.get("igstrt"), ri)
        it["cgstrt"] = _fmt_like(it.get("cgstrt"), rc)
        it["sgstrt"] = _fmt_like(it.get("sgstrt"), rs)
        it["igstamt"] = _fmt_like(it.get("igstamt"), ni)
        it["cgstamt"] = _fmt_like(it.get("cgstamt"), nc)
        it["sgstamt"] = _fmt_like(it.get("sgstamt"), ns)
        for k, v in (("igstval", ni), ("cgstval", nc), ("sgstval", ns)):
            if k in it:
                it[k] = _fmt_like(it.get(k), v)
        if "totitemval" in it:
            new_tot = _gst_num(it.get("totitemval")) - (old_i + old_c + old_s) + (ni + nc + ns)
            if new_tot <= 0:
                new_tot = ass + ni + nc + ns + _gst_num(it.get("cessamt")) + _gst_num(it.get("statecessamt"))
            it["totitemval"] = _fmt_like(it.get("totitemval"), new_tot)
        tot_i += ni
        tot_c += nc
        tot_s += ns

    if changed:
        new_tax = tot_i + tot_c + tot_s
        for blk_name in ("valdtls", "valdt1", None):
            blk = inv if blk_name is None else inv.get(blk_name)
            if not isinstance(blk, dict):
                continue
            # Top-level invoice: only touch totals that already exist there
            if blk_name is None and not any(k in blk for k in ("igstval", "cgstval", "sgstval")):
                continue
            old_blk_tax = _gst_num(blk.get("igstval")) + _gst_num(blk.get("cgstval")) + _gst_num(blk.get("sgstval"))
            blk["igstval"] = _fmt_like(blk.get("igstval"), tot_i)
            blk["cgstval"] = _fmt_like(blk.get("cgstval"), tot_c)
            blk["sgstval"] = _fmt_like(blk.get("sgstval"), tot_s)
            if "totinvval" in blk:
                blk["totinvval"] = _fmt_like(blk.get("totinvval"), _gst_num(blk.get("totinvval")) - old_blk_tax + new_tax)

    return {
        "changed": changed,
        "pos_derived": pos_derived,
        "supplier_state": sup_st,
        "pos": pos,
        "is_interstate": is_interstate,
        "igst": round(tot_i, 2),
        "cgst": round(tot_c, 2),
        "sgst": round(tot_s, 2),
    }


'''

PRE_VALIDATION = '''    # 2b. Auto-route GST tax split (IGST vs CGST+SGST) from Supplier GSTIN & Buyer GSTIN / POS state codes
    auto_tax_route = None
    try:
        auto_tax_route = auto_route_tax_split(target_inv)
    except Exception:
        auto_tax_route = None

'''

POST_PATCH = '''    # Re-run automatic GSTIN-based tax split routing after any intent patch (GSTIN / State / POS / HSN edits)
    try:
        _post_route = auto_route_tax_split(target_inv)
        if _post_route and (_post_route.get("changed") or not auto_tax_route):
            _was_changed = bool(auto_tax_route and auto_tax_route.get("changed"))
            auto_tax_route = dict(_post_route, changed=bool(_post_route.get("changed") or _was_changed))
    except Exception:
        pass
    if auto_tax_route and auto_tax_route.get("changed"):
        patch_applied = True
        _r = auto_tax_route
        if _r["is_interstate"]:
            _route_txt = f"Interstate {_r['supplier_state']} -> {_r['pos']}: IGST Rs {_r['igst']:,.2f}"
        else:
            _route_txt = f"Intrastate {_r['supplier_state']}: CGST Rs {_r['cgst']:,.2f} + SGST Rs {_r['sgst']:,.2f}"
        patch_summary.append(f"Auto-routed GST split from Supplier & Buyer GSTIN ({_route_txt})")
        reply_lines.insert(0,
            f"🧮 **GST Split Auto-Calculated from GSTINs:** Supplier GSTIN state `{_r['supplier_state']}` vs "
            f"Place of Supply `{_r['pos']}` ➔ **{'Interstate → IGST' if _r['is_interstate'] else 'Intrastate → CGST + SGST'}**. "
            f"Line-item rates, tax amounts and invoice totals were recalculated automatically.\\n"
        )

'''


def patch(path: Path) -> None:
    src = path.read_text(encoding="utf-8")
    if "def auto_route_tax_split(" in src:
        print(f"Already patched: {path}")
        return
    nl = "\r\n" if "\r\n" in src else "\n"
    fix = lambda s: s.replace("\n", nl)

    def rep(old: str, new: str, label: str, count: int = 1):
        nonlocal src
        old_n = fix(old)
        if src.count(old_n) < 1:
            raise SystemExit(f"[{label}] anchor not found in {path}")
        src = src.replace(old_n, fix(new), count)

    # A. Helper before buyer risk profiler
    rep("def compute_buyer_risk_profile(invoice: dict) -> dict:",
        HELPER + "def compute_buyer_risk_profile(invoice: dict) -> dict:", "helper")
    # B. Auto-route on every Copilot turn before validation
    anchor_b = "    # 3. Always run fresh validation pipeline on active payload to guarantee errors are 100% accurate"
    rep(anchor_b, PRE_VALIDATION + anchor_b, "pre-validation")
    # C. Re-route after intents, before post-patch re-validation
    anchor_c = "    # -------------------------------------------------------------\n    # POST-PATCH RE-VALIDATION"
    rep(anchor_c, POST_PATCH + anchor_c, "post-patch")
    # D. INTENT 6B: use real total rate (was defaulting to 18% when igstrt == 0)
    rep('                gst_r = float(itm.get("gstrate", itm.get("gst_rate", itm.get("igstrt", 18.0))) or 18.0)',
        '                gst_r = _item_total_gst_rate(itm)', "intent6b")
    rep('            items = target_inv.get("itemdtls", target_inv.get("items", []))\n            for itm in items:\n                gst_r = _item_total_gst_rate(itm)',
        '            items = target_inv.get("itemdtls", target_inv.get("items", []))\n            gst_r, half_r = 18.0, 9.0\n            for itm in items:\n                gst_r = _item_total_gst_rate(itm)', "intent6b-init")
    # E. INTENT 8: same rate fix + keep *amt keys in sync with *val keys
    rep('                g_rate = float(it.get("gstrate", it.get("gst_rate", it.get("igstrt", 18.0))) or 18.0)',
        '                g_rate = _item_total_gst_rate(it)', "intent8")
    rep('                it["totitemval"] = round(ass + it.get("igstval", 0)',
        '                it["igstamt"], it["cgstamt"], it["sgstamt"] = it["igstval"], it["cgstval"], it["sgstval"]\n'
        '                it["totitemval"] = round(ass + it.get("igstval", 0)', "intent8-amt")

    path.write_text(src, encoding="utf-8")
    print(f"Patched: {path}")


for t in TARGETS:
    if t.exists():
        patch(t)
    else:
        print(f"Missing: {t}", file=sys.stderr)
