"""
CoinSwitch PRO HFT Market Data API Client (Read-Only).
Authenticates via Ed25519 signing using cryptography library.
"""

from __future__ import annotations
import json
import time
from datetime import datetime, timezone
from urllib.parse import quote
from typing import Optional, Dict, Any, List, Tuple
import requests
from requests.adapters import HTTPAdapter
from cryptography.hazmat.primitives.asymmetric import ed25519
from django.conf import settings

_session = requests.Session()
_adapter = HTTPAdapter(pool_connections=25, pool_maxsize=25, max_retries=1)
_session.mount("https://", _adapter)
_session.mount("http://", _adapter)

class CoinSwitchAPIError(Exception):
    pass


def _build_path(endpoint: str, params: Dict[str, Any]) -> str:
    parts = []
    for key, value in params.items():
        if value is None or value == "":
            continue
        key_enc = quote(str(key), safe="")
        if key == "cursor":
            value_enc = str(value)
        else:
            value_enc = quote(str(value), safe="-_.~")
        parts.append(f"{key_enc}={value_enc}")
    qs = "&".join(parts)
    return endpoint + ("?" + qs if qs else "")


def signed_get(endpoint: str, params: Optional[Dict[str, Any]] = None, timeout: int = 12) -> Tuple[requests.Response, Dict[str, Any]]:
    api_key = settings.COINSWITCH_API_KEY
    secret_key = settings.COINSWITCH_SECRET_KEY
    base_url = settings.COINSWITCH_BASE_URL

    if not api_key or not secret_key:
        raise CoinSwitchAPIError("Missing COINSWITCH_API_KEY or COINSWITCH_SECRET_KEY in environment.")

    path = _build_path(endpoint, params or {})
    epoch = str(int(time.time() * 1000))
    message = ("GET" + path + epoch).encode("utf-8")

    try:
        key_bytes = bytes.fromhex(secret_key)
        private_key = ed25519.Ed25519PrivateKey.from_private_bytes(key_bytes)
        signature = private_key.sign(message).hex()
    except Exception as exc:
        raise CoinSwitchAPIError(f"Ed25519 key signing failed: {exc}") from exc

    headers = {
        "Content-Type": "application/json",
        "X-AUTH-APIKEY": api_key,
        "X-AUTH-SIGNATURE": signature,
        "X-AUTH-EPOCH": epoch,
    }

    url = f"{base_url}{path}"
    response = _session.get(url, headers=headers, timeout=timeout)
    try:
        payload = response.json()
    except ValueError:
        payload = {"raw_text": response.text}
    return response, payload


def fetch_btc_instruments(max_pages: int = 10) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    all_items: List[Dict[str, Any]] = []
    audit_pages: List[Dict[str, Any]] = []
    cursor: Optional[str] = None
    seen_cursors = set()

    for page_num in range(1, max_pages + 1):
        params = {"category": "option", "limit": 500}
        if cursor:
            params["cursor"] = cursor

        response, payload = signed_get("/v5/market/instruments-info", params)
        audit_pages.append({
            "page": page_num,
            "url": response.url,
            "status": response.status_code,
            "retCode": payload.get("retCode") if isinstance(payload, dict) else None,
        })
        response.raise_for_status()

        if not isinstance(payload, dict) or payload.get("retCode") != 0:
            raise CoinSwitchAPIError(f"Instruments API error: {json.dumps(payload)[:500]}")

        result = payload.get("result") or {}
        items = result.get("list") or []
        all_items.extend(item for item in items if isinstance(item, dict))

        next_cursor = result.get("nextPageCursor") or ""
        if not next_cursor or next_cursor in seen_cursors or not items:
            break
        seen_cursors.add(next_cursor)
        cursor = next_cursor

    unique = {}
    for item in all_items:
        key = item.get("symbol") or item.get("symbolId")
        if key:
            unique[key] = item

    btc_options = [
        item for item in unique.values()
        if str(item.get("baseCoin", "")).upper() == "BTC" or str(item.get("symbol", "")).upper().startswith("BTC-")
    ]
    return btc_options, audit_pages


def fetch_all_btc_tickers() -> Dict[str, Dict[str, Any]]:
    """
    Fetch all BTC option quotes in a single batch API call.
    Returns dictionary mapping symbol -> quote dict.
    """
    try:
        resp, payload = signed_get("/v5/market/tickers", {"category": "option", "baseCoin": "BTC"})
        if resp.ok and isinstance(payload, dict) and payload.get("retCode") == 0:
            item_list = (payload.get("result") or {}).get("list") or []
            now = datetime.now(timezone.utc)
            quotes = {}
            for row in item_list:
                sym = row.get("symbol")
                if sym:
                    quotes[sym] = {
                        "symbol": sym,
                        "bid": _to_float(row.get("bid1Price")),
                        "bid_size": _to_float(row.get("bid1Size")),
                        "ask": _to_float(row.get("ask1Price")),
                        "ask_size": _to_float(row.get("ask1Size")),
                        "last": _to_float(row.get("lastPrice")),
                        "mark": _to_float(row.get("markPrice")),
                        "index": _to_float(row.get("indexPrice")),
                        "underlying": _to_float(row.get("underlyingPrice")),
                        "iv": _to_float(row.get("markIv") or row.get("bid1Iv") or row.get("iv")),
                        "delta": _to_float(row.get("delta")),
                        "gamma": _to_float(row.get("gamma")),
                        "vega": _to_float(row.get("vega")),
                        "theta": _to_float(row.get("theta")),
                        "oi": _to_float(row.get("openInterest")),
                        "volume": _to_float(row.get("volume24h")),
                        "source": "batch_ticker",
                        "status": "ok",
                        "fetched_at": now,
                    }
            return quotes
    except Exception:
        pass
    return {}


def fetch_ticker_quote(symbol: str) -> Dict[str, Any]:
    try:
        resp, payload = signed_get("/v5/market/tickers", {"category": "option", "symbol": symbol})
        if resp.ok and isinstance(payload, dict) and payload.get("retCode") == 0:
            ticker_list = (payload.get("result") or {}).get("list") or []
            row = next((x for x in ticker_list if x.get("symbol") == symbol), None)
            if not row and ticker_list:
                row = ticker_list[0]
            if row:
                return {
                    "symbol": symbol,
                    "bid": _to_float(row.get("bid1Price")),
                    "bid_size": _to_float(row.get("bid1Size")),
                    "ask": _to_float(row.get("ask1Price")),
                    "ask_size": _to_float(row.get("ask1Size")),
                    "last": _to_float(row.get("lastPrice")),
                    "mark": _to_float(row.get("markPrice")),
                    "index": _to_float(row.get("indexPrice")),
                    "underlying": _to_float(row.get("underlyingPrice")),
                    "iv": _to_float(row.get("iv")),
                    "delta": _to_float(row.get("delta")),
                    "gamma": _to_float(row.get("gamma")),
                    "vega": _to_float(row.get("vega")),
                    "theta": _to_float(row.get("theta")),
                    "oi": _to_float(row.get("openInterest")),
                    "volume": _to_float(row.get("volume24h")),
                    "source": "ticker",
                    "status": "ok",
                }
    except Exception:
        pass

    # Read-only order book fallback
    try:
        resp, payload = signed_get("/v5/market/orderbook", {"category": "option", "symbol": symbol, "limit": 1})
        if resp.ok and isinstance(payload, dict) and payload.get("retCode") == 0:
            ob = payload.get("result") or {}
            bids = ob.get("b") or []
            asks = ob.get("a") or []
            return {
                "symbol": symbol,
                "bid": _to_float(bids[0][0]) if bids else None,
                "bid_size": _to_float(bids[0][1]) if bids else None,
                "ask": _to_float(asks[0][0]) if asks else None,
                "ask_size": _to_float(asks[0][1]) if asks else None,
                "last": None,
                "source": "orderbook",
                "status": "ok",
            }
    except Exception as exc:
        return {"symbol": symbol, "status": "error", "error": str(exc)}

    return {"symbol": symbol, "status": "unavailable"}


def _to_float(val: Any) -> Optional[float]:
    if val is None or val == "":
        return None
    try:
        f = float(val)
        return f if f == f else None
    except (ValueError, TypeError):
        return None

