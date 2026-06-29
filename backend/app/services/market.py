"""Piyasa verisi — Yahoo Finance (ücretsiz, anahtarsız, ~15 dk gecikmeli).

BİST endeksleri, döviz, altın/gümüş (ons -> gram TL hesaplanır) ve endeks grafiği.
Kişisel/araştırma kullanımı içindir.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import httpx

_UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}
_BASE = "https://query1.finance.yahoo.com/v8/finance/chart/"
_GRAM = 31.1035  # bir ons = 31.1035 gram
_TTL = 600  # 10 dk cache

_snap_cache: dict = {"at": 0.0, "items": []}
_chart_cache: dict[str, dict] = {}
_quote_cache: dict[str, dict] = {}


def _quote(client: httpx.Client, symbol: str) -> tuple[float, float | None] | None:
    try:
        r = client.get(_BASE + symbol, params={"interval": "1d", "range": "5d"})
        res = (r.json().get("chart") or {}).get("result")
        if not res:
            return None
        m = res[0]["meta"]
        price = m.get("regularMarketPrice")
        prev = m.get("previousClose") or m.get("chartPreviousClose")
        if price is None:
            return None
        return float(price), (float(prev) if prev else None)
    except Exception:  # noqa: BLE001
        return None


def quote_one(symbol: str) -> tuple[float, float | None] | None:
    """Tek bir sembol için (fiyat, önceki kapanış) — 10 dk cache'li."""
    now = time.time()
    c = _quote_cache.get(symbol)
    if c and now - c["at"] < _TTL:
        return c["q"]
    try:
        with httpx.Client(timeout=12.0, headers=_UA) as client:
            q = _quote(client, symbol)
    except Exception:  # noqa: BLE001
        q = None
    if q:
        _quote_cache[symbol] = {"at": now, "q": q}
    return q


def snapshot() -> list[dict]:
    now = time.time()
    if _snap_cache["items"] and now - _snap_cache["at"] < _TTL:
        return _snap_cache["items"]
    items = _fetch_snapshot()
    if items:
        _snap_cache["items"] = items
        _snap_cache["at"] = now
    return _snap_cache["items"]


def _fetch_snapshot() -> list[dict]:
    symbols = ["XU100.IS", "XU030.IS", "TRY=X", "EURTRY=X", "GC=F", "SI=F"]
    try:
        with httpx.Client(timeout=15.0, headers=_UA) as c:
            q = {s: _quote(c, s) for s in symbols}
    except Exception:  # noqa: BLE001
        return []

    out: list[dict] = []

    def add(label: str, qt: tuple[float, float | None] | None) -> None:
        if qt:
            price, prev = qt
            out.append({"label": label, "value": price, "change": (price / prev - 1.0) if prev else None})

    add("BİST 100", q["XU100.IS"])
    add("BİST 30", q["XU030.IS"])
    add("Dolar", q["TRY=X"])
    add("Euro", q["EURTRY=X"])

    usd, gold, silver = q["TRY=X"], q["GC=F"], q["SI=F"]
    if usd and gold:
        gt = gold[0] / _GRAM * usd[0]
        gp = (gold[1] / _GRAM * usd[1]) if (gold[1] and usd[1]) else None
        out.append({"label": "Gram Altın", "value": gt, "change": (gt / gp - 1.0) if gp else None})
    if usd and silver:
        st = silver[0] / _GRAM * usd[0]
        sp = (silver[1] / _GRAM * usd[1]) if (silver[1] and usd[1]) else None
        out.append({"label": "Gram Gümüş", "value": st, "change": (st / sp - 1.0) if sp else None})
    return out


def index_chart(symbol: str = "XU100.IS", rng: str = "1mo") -> list[dict]:
    key = f"{symbol}:{rng}"
    now = time.time()
    cached = _chart_cache.get(key)
    if cached and now - cached["at"] < _TTL:
        return cached["points"]

    points: list[dict] = []
    try:
        with httpx.Client(timeout=15.0, headers=_UA) as c:
            r = c.get(_BASE + symbol, params={"interval": "1d", "range": rng})
            res = (r.json().get("chart") or {}).get("result")
            if res:
                result = res[0]
                ts = result.get("timestamp") or []
                closes = (result.get("indicators", {}).get("quote") or [{}])[0].get("close") or []
                for t, cl in zip(ts, closes):
                    if cl is not None:
                        d = datetime.fromtimestamp(t, tz=timezone.utc).date().isoformat()
                        points.append({"date": d, "close": float(cl)})
    except Exception:  # noqa: BLE001
        points = []

    if points:
        _chart_cache[key] = {"at": now, "points": points}
    return points
