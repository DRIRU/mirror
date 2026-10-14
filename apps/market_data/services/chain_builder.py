"""
Options Chain Data Builder.
Organizes instruments and quotes into a dual-sided Calls | Strike | Puts matrix.
"""

from __future__ import annotations
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional


def parse_symbol(symbol: str) -> Dict[str, Any]:
    parts = symbol.split("-")
    res = {
        "expiry_label": "Unknown",
        "expiry_date": None,
        "strike": 0.0,
        "strike_label": "?",
        "type": "Unknown",
        "valid": False,
    }
    if len(parts) >= 4 and parts[0].upper() == "BTC":
        res["expiry_label"] = parts[1]
        res["expiry_date"] = _parse_date(parts[1])
        try:
            res["strike"] = float(parts[2])
            res["strike_label"] = f"{int(res['strike']):,}"
        except ValueError:
            pass
        res["type"] = "Call" if parts[3].upper() == "C" else ("Put" if parts[3].upper() == "P" else "Unknown")
        res["valid"] = res["type"] in ("Call", "Put")
    return res


def _parse_date(label: str) -> Optional[datetime]:
    for fmt in ("%d%b%y", "%d%b%Y"):
        try:
            return datetime.strptime(label.upper(), fmt)
        except ValueError:
            pass
    return None


def get_dte(dt: Optional[datetime]) -> int:
    if not dt:
        return 0
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    delta = dt - now
    return max(0, int(delta.days))


def build_options_matrix(instruments: List[Dict[str, Any]], quote_cache: Dict[str, Any], expiry: str, index_price: float = 0.0) -> Dict[str, Any]:
    calls_by_strike = {}
    puts_by_strike = {}

    for inst in instruments:
        sym = inst.get("symbol", "")
        parsed = parse_symbol(sym)
        if not parsed["valid"] or parsed["expiry_label"] != expiry:
            continue
        strike = parsed["strike"]
        if parsed["type"] == "Call":
            calls_by_strike[strike] = inst
        else:
            puts_by_strike[strike] = inst

    strikes = sorted(set(calls_by_strike) | set(puts_by_strike))
    rows = []

    total_call_oi = 0.0
    total_put_oi = 0.0
    max_call_oi = 0.0
    max_put_oi = 0.0
    max_call_oi_strike = "—"
    max_put_oi_strike = "—"
    fetched_count = 0

    for strike in strikes:
        call_inst = calls_by_strike.get(strike)
        put_inst = puts_by_strike.get(strike)

        call_sym = call_inst.get("symbol") if call_inst else ""
        put_sym = put_inst.get("symbol") if put_inst else ""

        c_q = quote_cache.get(call_sym) or {}
        p_q = quote_cache.get(put_sym) or {}

        if c_q.get("status") == "ok":
            fetched_count += 1
        if p_q.get("status") == "ok":
            fetched_count += 1

        # Track OI
        c_oi = c_q.get("oi") or 0.0
        p_oi = p_q.get("oi") or 0.0
        total_call_oi += c_oi
        total_put_oi += p_oi
        if c_oi > max_call_oi:
            max_call_oi = c_oi
            max_call_oi_strike = f"{int(strike):,}"
        if p_oi > max_put_oi:
            max_put_oi = p_oi
            max_put_oi_strike = f"{int(strike):,}"

        # Moneyness
        mn = "OTM"
        is_atm = False
        if index_price > 0:
            diff_pct = abs(strike - index_price) / index_price * 100
            if diff_pct <= 0.5:
                mn = "ATM"
                is_atm = True
            elif strike < index_price:
                mn = "ITM" # Call ITM

        rows.append({
            "strike": strike,
            "strike_label": f"{int(strike):,}",
            "moneyness": mn,
            "is_atm": is_atm,
            "call": {
                "symbol": call_sym,
                "bid": c_q.get("bid"),
                "bid_size": c_q.get("bid_size"),
                "ask": c_q.get("ask"),
                "ask_size": c_q.get("ask_size"),
                "last": c_q.get("last"),
                "iv": c_q.get("iv"),
                "delta": c_q.get("delta"),
                "gamma": c_q.get("gamma"),
                "vega": c_q.get("vega"),
                "theta": c_q.get("theta"),
                "oi": c_q.get("oi"),
                "vol": c_q.get("volume"),
                "is_itm": strike < index_price if index_price > 0 else False,
                "status": c_q.get("status", "not_fetched"),
            },
            "put": {
                "symbol": put_sym,
                "bid": p_q.get("bid"),
                "bid_size": p_q.get("bid_size"),
                "ask": p_q.get("ask"),
                "ask_size": p_q.get("ask_size"),
                "last": p_q.get("last"),
                "iv": p_q.get("iv"),
                "delta": p_q.get("delta"),
                "gamma": p_q.get("gamma"),
                "vega": p_q.get("vega"),
                "theta": p_q.get("theta"),
                "oi": p_q.get("oi"),
                "vol": p_q.get("volume"),
                "is_itm": strike > index_price if index_price > 0 else False,
                "status": p_q.get("status", "not_fetched"),
            }
        })

    pcr = round(total_put_oi / total_call_oi, 2) if total_call_oi > 0 else 0.0

    return {
        "expiry": expiry,
        "rows": rows,
        "strikes_count": len(strikes),
        "fetched_count": fetched_count,
        "total_contracts": len(strikes) * 2,
        "total_call_oi": total_call_oi,
        "total_put_oi": total_put_oi,
        "pcr": pcr,
        "max_call_oi_strike": max_call_oi_strike,
        "max_put_oi_strike": max_put_oi_strike,
    }

