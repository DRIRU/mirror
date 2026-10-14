"""
Market Data Views for the CoinSwitch PRO Options Terminal.
"""

from datetime import datetime, timezone
from django.shortcuts import render
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods
from .services.quote_service import store
from .services.chain_builder import parse_symbol, get_dte, build_options_matrix


def _get_sorted_expiries(instruments):
    expiries_set = set()
    for inst in instruments:
        p = parse_symbol(inst.get("symbol", ""))
        if p["valid"] and p["expiry_label"] != "Unknown":
            expiries_set.add((p["expiry_label"], p["expiry_date"]))

    def _sort_key(item):
        return item[1] if item[1] else datetime.max

    sorted_list = sorted(expiries_set, key=_sort_key)
    res = []
    for label, dt in sorted_list:
        d = get_dte(dt)
        res.append({
            "label": label,
            "dte": d,
            "display": f"{dt.strftime('%d %b %y') if dt else label} · {d}d",
            "is_zero_dte": d == 0,
        })
    return res


def options_chain_view(request):
    instruments = store.get_instruments()
    store.warmup_index_price()
    expiries = _get_sorted_expiries(instruments)

    # Auto-select nearest live expiry
    selected_expiry = request.GET.get("expiry")
    if not selected_expiry:
        # Default to first non-zero DTE if available
        live = [e["label"] for e in expiries if not e["is_zero_dte"]]
        selected_expiry = live[0] if live else (expiries[0]["label"] if expiries else "")

    quotes = store.get_quote_cache()
    index_price = store.get_latest_index_price()
    mark_price = store.get_latest_mark_price()
    underlying_price = store.get_latest_underlying_price()

    matrix = build_options_matrix(instruments, quotes, selected_expiry, index_price)

    selected_expiry_info = next((e for e in expiries if e["label"] == selected_expiry), None)

    context = {
        "expiries": expiries,
        "selected_expiry": selected_expiry,
        "selected_expiry_info": selected_expiry_info,
        "matrix": matrix,
        "index_price": index_price,
        "mark_price": mark_price,
        "underlying_price": underlying_price,
        "instruments_count": len(instruments),
        "last_batch_run": store.last_batch_run,
        "now_utc": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
    }
    return render(request, "market_data/chain.html", context)


def chain_table_partial(request):
    expiry = request.GET.get("expiry", "")
    instruments = store.get_instruments()
    quotes = store.get_quote_cache()
    index_price = store.get_latest_index_price()

    # If lazy load is requested or auto_fetch is on, fetch quotes if not already cached
    auto_fetch = request.GET.get("auto", "0") == "1"
    symbols_for_exp = [
        inst.get("symbol") for inst in instruments
        if parse_symbol(inst.get("symbol", ""))["valid"] and parse_symbol(inst.get("symbol", ""))["expiry_label"] == expiry
    ]
    cached_count = sum(1 for s in symbols_for_exp if quotes.get(s, {}).get("status") == "ok")

    summary = None
    if auto_fetch and cached_count < max(5, len(symbols_for_exp) // 2):
        workers = int(request.GET.get("workers", 8))
        summary = store.fetch_quotes_for_symbols(symbols_for_exp, max_workers=workers)
        quotes = store.get_quote_cache()
        index_price = store.get_latest_index_price()

    matrix = build_options_matrix(instruments, quotes, expiry, index_price)
    return render(request, "market_data/partials/chain_table.html", {
        "matrix": matrix,
        "selected_expiry": expiry,
        "batch_summary": summary,
        "index_price": index_price,
        "underlying_price": store.get_latest_underlying_price(),
        "instruments_count": len(instruments),
        "is_htmx": True,
    })


@require_http_methods(["GET", "POST"])
def fetch_quotes_action(request):
    expiry = request.POST.get("expiry") or request.GET.get("expiry") or ""
    instruments = store.get_instruments()
    
    # Collect symbols for this expiry
    symbols = []
    for inst in instruments:
        p = parse_symbol(inst.get("symbol", ""))
        if p["valid"] and p["expiry_label"] == expiry:
            symbols.append(inst.get("symbol"))

    workers_param = request.POST.get("workers") or request.GET.get("workers") or 8
    workers = int(workers_param)
    workers = max(1, min(workers, 15))

    summary = store.fetch_quotes_for_symbols(symbols, max_workers=workers)
    
    quotes = store.get_quote_cache()
    index_price = store.get_latest_index_price()
    matrix = build_options_matrix(instruments, quotes, expiry, index_price)

    context = {
        "matrix": matrix,
        "selected_expiry": expiry,
        "batch_summary": summary,
        "index_price": index_price,
        "underlying_price": store.get_latest_underlying_price(),
        "instruments_count": len(instruments),
        "is_htmx": True,
    }
    return render(request, "market_data/partials/chain_table.html", context)


@require_http_methods(["POST"])
def refresh_instruments_action(request):
    try:
        count = store.refresh_instruments()
        return JsonResponse({"status": "ok", "count": count})
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


def contract_drawer_partial(request):
    side = request.GET.get("side", "").strip().lower()
    call_sym = request.GET.get("call", "").strip()
    put_sym = request.GET.get("put", "").strip()
    single_sym = request.GET.get("symbol", "").strip()
    strike = request.GET.get("strike", "").strip()

    if single_sym:
        p_single = parse_symbol(single_sym)
        if not side:
            side = "call" if p_single.get("type") == "Call" else "put"
        if not strike:
            strike = p_single.get("strike_label", "")
        if p_single.get("type") == "Call" and not call_sym:
            call_sym = single_sym
        elif p_single.get("type") == "Put" and not put_sym:
            put_sym = single_sym

    quotes = store.get_quote_cache()

    # If quotes are missing from cache, fetch them on the fly
    needed = []
    if call_sym and (call_sym not in quotes or quotes[call_sym].get("status") != "ok"):
        needed.append(call_sym)
    if put_sym and (put_sym not in quotes or quotes[put_sym].get("status") != "ok"):
        needed.append(put_sym)
    
    if needed:
        store.fetch_quotes_for_symbols(needed, max_workers=2)
        quotes = store.get_quote_cache()

    call_quote = quotes.get(call_sym) or {}
    put_quote = quotes.get(put_sym) or {}

    call_parsed = parse_symbol(call_sym) if call_sym else {}
    put_parsed = parse_symbol(put_sym) if put_sym else {}

    display_strike = strike or call_parsed.get("strike_label") or put_parsed.get("strike_label") or "—"

    if side not in ("call", "put"):
        side = "call"

    if side == "call":
        active_contract = {
            "side": "CALL",
            "type": "Call",
            "symbol": call_sym,
            "quote": call_quote,
            "parsed": call_parsed,
            "theme": "emerald",
            "badge_class": "bg-emerald-950/80 border-emerald-500 text-emerald-300",
            "border_class": "border-emerald-600/50",
            "accent_text": "text-emerald-400",
        }
        alt_contract = {
            "side": "PUT",
            "type": "Put",
            "symbol": put_sym,
            "quote": put_quote,
            "parsed": put_parsed,
            "theme": "rose",
            "badge_class": "bg-rose-950/80 border-rose-500 text-rose-300",
            "border_class": "border-rose-600/50",
            "accent_text": "text-rose-400",
        }
    else:
        active_contract = {
            "side": "PUT",
            "type": "Put",
            "symbol": put_sym,
            "quote": put_quote,
            "parsed": put_parsed,
            "theme": "rose",
            "badge_class": "bg-rose-950/80 border-rose-500 text-rose-300",
            "border_class": "border-rose-600/50",
            "accent_text": "text-rose-400",
        }
        alt_contract = {
            "side": "CALL",
            "type": "Call",
            "symbol": call_sym,
            "quote": call_quote,
            "parsed": call_parsed,
            "theme": "emerald",
            "badge_class": "bg-emerald-950/80 border-emerald-500 text-emerald-300",
            "border_class": "border-emerald-600/50",
            "accent_text": "text-emerald-400",
        }

    delta = active_contract["quote"].get("delta")
    if delta is not None:
        abs_d = abs(delta)
        if abs_d >= 0.7:
            moneyness_text = "Deep ITM"
        elif abs_d >= 0.55:
            moneyness_text = "In The Money (ITM)"
        elif abs_d >= 0.45:
            moneyness_text = "At The Money (ATM)"
        elif abs_d >= 0.2:
            moneyness_text = "Out of The Money (OTM)"
        else:
            moneyness_text = "Deep OTM"
    else:
        moneyness_text = "Active Contract"

    bid = active_contract["quote"].get("bid")
    ask = active_contract["quote"].get("ask")
    spread_val = None
    spread_pct = None
    if bid is not None and ask is not None and ask >= bid:
        spread_val = ask - bid
        if bid > 0:
            spread_pct = (spread_val / bid) * 100

    return render(request, "market_data/partials/drawer.html", {
        "side": side,
        "strike": display_strike,
        "contract": active_contract,
        "alt_contract": alt_contract,
        "moneyness_text": moneyness_text,
        "spread_val": spread_val,
        "spread_pct": spread_pct,
        "call_sym": call_sym,
        "put_sym": put_sym,
        "call_quote": call_quote,
        "put_quote": put_quote,
        "call_parsed": call_parsed,
        "put_parsed": put_parsed,
    })


