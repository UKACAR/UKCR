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
_TTL = 600  # 10 dk cache (grafik — günlük mumlar)
_LIVE_TTL = 60  # 1 dk cache (canlı ticker/kotasyon — sık güncellensin)

_snap_cache: dict = {"at": 0.0, "items": []}
_chart_cache: dict[str, dict] = {}
_quote_cache: dict[str, dict] = {}


def _quote(client: httpx.Client, symbol: str) -> tuple[float, float | None] | None:
    """(son fiyat, ÖNCEKİ GÜN kapanışı) döndürür — günlük değişim için.

    Not: Yahoo bazı sembollerde (BİST endeksleri, döviz, vadeli) meta'da
    `previousClose` döndürmez; `chartPreviousClose` ise seçilen aralığın (ör.
    5 gün) BAŞINDAN önceki kapanıştır — yani çok günlük, günlük değil. Bu yüzden
    önceki kapanışı günlük mum dizisinin sondan bir önceki geçerli değerinden
    alıyoruz (gerçek "dün vs bugün" değişimi).
    """
    try:
        r = client.get(_BASE + symbol, params={"interval": "1d", "range": "7d"})
        res = (r.json().get("chart") or {}).get("result")
        if not res:
            return None
        result = res[0]
        m = result.get("meta") or {}
        closes = (result.get("indicators", {}).get("quote") or [{}])[0].get("close") or []
        valid = [float(c) for c in closes if c is not None]

        rmp = m.get("regularMarketPrice")
        price = float(rmp) if rmp is not None else (valid[-1] if valid else None)
        if price is None:
            return None

        # 1) Otoriter meta varsa onu kullan (bu uçta genelde gelmez).
        prev = m.get("previousClose")
        if prev is None:
            prev = m.get("regularMarketPreviousClose")

        # 2) Yoksa günlük mumdan çıkar. ÖNEMLİ: Yahoo, piyasa açık/kapalı fark
        #    etmeksizin BUGÜNÜN barını regularMarketPrice ile AYNI kapanışla
        #    içerir. Son barın kapanışı rmp'ye eşit DEĞİLSE bugünün barı henüz
        #    oluşmamış demektir ve son bar zaten önceki kapanıştır — aksi halde
        #    valid[-2]'yi alıp 2 GÜNLÜK değişim hesaplardık (düzeltmenin önlediği
        #    asıl hata; özellikle erken seansta ve ~24s işlem gören vadelilerde).
        if prev is None and valid:
            last_close = valid[-1]
            today_bar = abs(last_close - price) <= max(abs(price), 1.0) * 1e-4
            if today_bar:
                prev = valid[-2] if len(valid) >= 2 else None
            else:
                prev = last_close

        return price, (float(prev) if prev is not None else None)
    except Exception:  # noqa: BLE001
        return None


def quote_one(symbol: str) -> tuple[float, float | None] | None:
    """Tek bir sembol için (fiyat, önceki gün kapanışı) — ~1 dk (canlı) cache'li."""
    now = time.time()
    c = _quote_cache.get(symbol)
    if c and now - c["at"] < _LIVE_TTL:
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
    if _snap_cache["items"] and now - _snap_cache["at"] < _LIVE_TTL:
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


_METALS = [
    ("gold", "Altın", "GC=F"),
    ("silver", "Gümüş", "SI=F"),
    ("platinum", "Platin", "PL=F"),
    ("palladium", "Paladyum", "PA=F"),
]
_metals_cache: dict = {"at": 0.0, "data": None}


def precious_metals() -> dict:
    """Kıymetli madenler: USD (ons/gram) + TL (ons/gram) fiyat ve günlük değişim.

    Ons fiyatı Yahoo vadeli sözleşmesinden (GC=F vb.), gram = ons / 31.1035,
    TL fiyatı × USD/TRY. Günlük değişim USD ve TL bazında ayrı verilir.
    """
    now = time.time()
    if _metals_cache["data"] and now - _metals_cache["at"] < _LIVE_TTL:
        return _metals_cache["data"]
    syms = [s for _, _, s in _METALS] + ["TRY=X"]
    try:
        with httpx.Client(timeout=15.0, headers=_UA) as c:
            q = {s: _quote(c, s) for s in syms}
    except Exception:  # noqa: BLE001
        return _metals_cache["data"] or {"metals": [], "usdtry": None}

    usd = q.get("TRY=X")
    metals: list[dict] = []
    for key, name, sym in _METALS:
        qm = q.get(sym)
        if not qm:
            continue
        ons, prev = qm
        gram = ons / _GRAM
        usd_change = (ons / prev - 1.0) if prev else None
        try_ons = try_gram = try_change = None
        if usd and usd[0]:
            u, uprev = usd
            try_ons = ons * u
            try_gram = gram * u
            if prev and uprev:
                prev_try_gram = (prev / _GRAM) * uprev
                try_change = (try_gram / prev_try_gram - 1.0) if prev_try_gram else None
        metals.append({
            "key": key, "name": name, "symbol": sym,
            "usd_ounce": ons, "usd_gram": gram,
            "try_ounce": try_ons, "try_gram": try_gram,
            "usd_change": usd_change, "try_change": try_change,
        })
    data = {"metals": metals, "usdtry": (usd[0] if usd else None)}
    if metals:
        _metals_cache["data"] = data
        _metals_cache["at"] = now
    return data


# Piyasa panoları (Yahoo sembolleri) — BİST / Dünya / VİOP dayanakları / Kripto
BOARDS: dict[str, dict] = {
    "bist": {
        "with_try": False,
        "items": [
            ("BİST 100", "XU100.IS"), ("BİST 30", "XU030.IS"),
            ("BİST Banka", "XBANK.IS"), ("BİST Sınai", "XUSIN.IS"),
            ("BİST Teknoloji", "XUTEK.IS"), ("BİST Holding", "XHOLD.IS"),
            ("THYAO", "THYAO.IS"), ("GARAN", "GARAN.IS"), ("AKBNK", "AKBNK.IS"),
            ("ASELS", "ASELS.IS"), ("KCHOL", "KCHOL.IS"), ("SASA", "SASA.IS"),
        ],
    },
    "world": {
        "with_try": False,
        "items": [
            ("S&P 500", "^GSPC"), ("Nasdaq", "^IXIC"), ("Dow Jones", "^DJI"),
            ("DAX (Almanya)", "^GDAXI"), ("FTSE 100 (İngiltere)", "^FTSE"),
            ("CAC 40 (Fransa)", "^FCHI"), ("Nikkei 225 (Japonya)", "^N225"),
            ("Hang Seng (Hong Kong)", "^HSI"), ("Brent Petrol", "BZ=F"),
            ("VIX (Korku Endeksi)", "^VIX"), ("EUR/USD", "EURUSD=X"),
        ],
    },
    "viop": {
        "with_try": False,
        "items": [
            ("BİST 30 (dayanak)", "XU030.IS"), ("Dolar/TL", "TRY=X"),
            ("Euro/TL", "EURTRY=X"), ("Ons Altın", "GC=F"), ("Ons Gümüş", "SI=F"),
        ],
    },
    "crypto": {
        "with_try": True,
        "items": [
            ("Bitcoin", "BTC-USD"), ("Ethereum", "ETH-USD"), ("BNB", "BNB-USD"),
            ("Solana", "SOL-USD"), ("XRP", "XRP-USD"), ("Cardano", "ADA-USD"),
            ("Dogecoin", "DOGE-USD"), ("Tron", "TRX-USD"), ("Avalanche", "AVAX-USD"),
            ("Polkadot", "DOT-USD"),
        ],
    },
}
_board_cache: dict[str, dict] = {}


def market_board(name: str) -> dict:
    """Bir piyasa panosunun anlık değerleri: [{label, symbol, value, change, try_value?}]."""
    conf = BOARDS.get(name)
    if not conf:
        return {"items": [], "usdtry": None}
    now = time.time()
    c = _board_cache.setdefault(name, {"at": 0.0, "data": None})
    if c["data"] and now - c["at"] < _LIVE_TTL:
        return c["data"]

    pairs = conf["items"]
    with_try = conf["with_try"]
    syms = {s for _, s in pairs}
    if with_try:
        syms.add("TRY=X")
    try:
        with httpx.Client(timeout=15.0, headers=_UA) as cl:
            q = {s: _quote(cl, s) for s in syms}
    except Exception:  # noqa: BLE001
        return c["data"] or {"items": [], "usdtry": None}

    usd = q.get("TRY=X") if with_try else None
    items: list[dict] = []
    for label, sym in pairs:
        qm = q.get(sym)
        if not qm:
            continue
        price, prev = qm
        it = {
            "label": label,
            "symbol": sym,
            "value": price,
            "change": (price / prev - 1.0) if prev else None,
        }
        if with_try and usd and usd[0]:
            it["try_value"] = price * usd[0]
        items.append(it)

    data = {"items": items, "usdtry": (usd[0] if usd else None)}
    if items:
        c["data"] = data
        c["at"] = now
    return data
