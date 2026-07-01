"""Piyasa verisi — Yahoo Finance (ücretsiz, anahtarsız, ~15 dk gecikmeli).

BİST endeksleri, döviz, altın/gümüş (ons -> gram TL hesaplanır) ve endeks grafiği.
Kişisel/araştırma kullanımı içindir.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
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


# (key, ad, sembol, birim, gram_hesapla) — gram=True ise ons/31.1035 gram fiyatı da verilir
_COMMODITIES = [
    ("gold", "Altın", "GC=F", "ons", True),
    ("silver", "Gümüş", "SI=F", "ons", True),
    ("platinum", "Platin", "PL=F", "ons", True),
    ("palladium", "Paladyum", "PA=F", "ons", True),
    ("copper", "Bakır", "HG=F", "libre", False),
    ("brent", "Brent Petrol", "BZ=F", "varil", False),
    ("wti", "Ham Petrol (WTI)", "CL=F", "varil", False),
    ("natgas", "Doğalgaz", "NG=F", "MMBtu", False),
]
_metals_cache: dict = {"at": 0.0, "data": None}


def precious_metals() -> dict:
    """Kıymetli madenler + emtia (petrol/doğalgaz/bakır): USD + TL fiyat/değişim.

    Fiyat Yahoo vadeli sözleşmesinden (birim başına: ons/varil/MMBtu/libre),
    TL = × USD/TRY. gram=True olanlar için ayrıca gram (ons/31.1035) verilir.
    """
    now = time.time()
    if _metals_cache["data"] and now - _metals_cache["at"] < _LIVE_TTL:
        return _metals_cache["data"]
    syms = [s for _, _, s, _, _ in _COMMODITIES] + ["TRY=X"]
    try:
        with httpx.Client(timeout=15.0, headers=_UA) as c:
            q = {s: _quote(c, s) for s in syms}
    except Exception:  # noqa: BLE001
        return _metals_cache["data"] or {"metals": [], "usdtry": None}

    usd = q.get("TRY=X")
    u, uprev = (usd if usd else (None, None))
    metals: list[dict] = []
    for key, name, sym, unit, is_gram in _COMMODITIES:
        qm = q.get(sym)
        if not qm:
            continue
        price, prev = qm  # USD / birim
        usd_change = (price / prev - 1.0) if prev else None
        try_price = try_change = None
        if u:
            try_price = price * u
            if prev and uprev:
                prev_try = prev * uprev
                try_change = (try_price / prev_try - 1.0) if prev_try else None
        item = {
            "key": key, "name": name, "symbol": sym, "unit": unit, "gram": is_gram,
            "usd_price": price, "try_price": try_price,
            "usd_change": usd_change, "try_change": try_change,
        }
        if is_gram:
            item["usd_gram"] = price / _GRAM
            item["try_gram"] = (price / _GRAM) * u if u else None
        metals.append(item)

    data = {"metals": metals, "usdtry": (u if usd else None)}
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


# ---- Günün enleri: en çok yükselen / düşen / işlem gören ----
_MOVERS_TTL = 600  # 10 dk (hisse taraması ağır)
_movers_cache: dict[str, dict] = {}

# Likit ~40 BİST hissesi (Yahoo sembolü = kod + ".IS")
_BIST_STOCKS = [
    ("GARAN", "Garanti BBVA"), ("AKBNK", "Akbank"), ("ISCTR", "İş Bankası C"),
    ("YKBNK", "Yapı Kredi"), ("VAKBN", "VakıfBank"), ("HALKB", "Halkbank"),
    ("THYAO", "Türk Hava Yolları"), ("PGSUS", "Pegasus"), ("TUPRS", "Tüpraş"),
    ("KCHOL", "Koç Holding"), ("SAHOL", "Sabancı Holding"), ("SISE", "Şişecam"),
    ("EREGL", "Ereğli Demir Çelik"), ("KRDMD", "Kardemir D"), ("ASELS", "Aselsan"),
    ("TOASO", "Tofaş"), ("FROTO", "Ford Otosan"), ("BIMAS", "BİM"),
    ("MGROS", "Migros"), ("SASA", "Sasa Polyester"), ("PETKM", "Petkim"),
    ("KOZAL", "Koza Altın"), ("KOZAA", "Koza Anadolu"), ("TCELL", "Turkcell"),
    ("TTKOM", "Türk Telekom"), ("ENKAI", "Enka İnşaat"), ("EKGYO", "Emlak Konut"),
    ("ARCLK", "Arçelik"), ("VESTL", "Vestel"), ("HEKTS", "Hektaş"),
    ("ALARK", "Alarko Holding"), ("GUBRF", "Gübretaş"), ("TAVHL", "TAV Havalimanları"),
    ("TKFEN", "Tekfen Holding"), ("OYAKC", "Oyak Çimento"), ("CIMSA", "Çimsa"),
    ("SOKM", "Şok Marketler"), ("ASTOR", "Astor Enerji"), ("DOAS", "Doğuş Otomotiv"),
    ("ISDMR", "İskenderun Demir"),
]
_CG_MARKETS = "https://api.coingecko.com/api/v3/coins/markets"


def _stock_row(client: httpx.Client, code: str, name: str) -> dict | None:
    """Bir BİST hissesi için (fiyat, günlük değişim, hacim) — 5 günlük mumdan."""
    try:
        r = client.get(_BASE + code + ".IS", params={"interval": "1d", "range": "5d"})
        res = (r.json().get("chart") or {}).get("result")
        if not res:
            return None
        result = res[0]
        m = result.get("meta") or {}
        q0 = (result.get("indicators", {}).get("quote") or [{}])[0]
        closes = q0.get("close") or []
        vols = q0.get("volume") or []
        valid = [
            (float(cl), float(v) if v is not None else 0.0)
            for cl, v in zip(closes, vols)
            if cl is not None
        ]
        if not valid:
            return None
        rmp = m.get("regularMarketPrice")
        price = float(rmp) if rmp is not None else valid[-1][0]
        last_close, last_vol = valid[-1]
        prev = m.get("previousClose")
        if prev is None:
            prev = m.get("regularMarketPreviousClose")
        if prev is None:
            today_bar = abs(last_close - price) <= max(abs(price), 1.0) * 1e-4
            if today_bar:
                prev = valid[-2][0] if len(valid) >= 2 else None
            else:
                prev = last_close
        change = (price / float(prev) - 1.0) if prev else None
        return {
            "code": code, "name": name, "price": price, "change": change,
            "volume": last_vol, "tl_volume": last_vol * price,
        }
    except Exception:  # noqa: BLE001
        return None


def bist_movers(top: int = 10) -> dict:
    """BİST: en çok yükselen / düşen / işlem gören (TL hacim). ~40 likit hisse."""
    now = time.time()
    c = _movers_cache.setdefault("bist", {"at": 0.0, "data": None})
    if c["data"] and now - c["at"] < _MOVERS_TTL:
        return c["data"]
    empty = {"currency": "TRY", "count": 0, "gainers": [], "losers": [], "most_traded": []}
    rows: list[dict] = []
    try:
        with httpx.Client(timeout=12.0, headers=_UA) as cl:
            with ThreadPoolExecutor(max_workers=8) as ex:
                for r in ex.map(lambda cn: _stock_row(cl, cn[0], cn[1]), _BIST_STOCKS):
                    if r and r["change"] is not None:
                        rows.append(r)
    except Exception:  # noqa: BLE001
        return c["data"] or empty
    if not rows:
        return c["data"] or empty

    def fmt(lst: list[dict]) -> list[dict]:
        return [
            {"code": r["code"], "name": r["name"], "price": r["price"],
             "change": r["change"], "volume": r["tl_volume"]}
            for r in lst
        ]

    data = {
        "currency": "TRY", "count": len(rows),
        "gainers": fmt(sorted(rows, key=lambda x: x["change"], reverse=True)[:top]),
        "losers": fmt(sorted(rows, key=lambda x: x["change"])[:top]),
        "most_traded": fmt(sorted(rows, key=lambda x: x["tl_volume"], reverse=True)[:top]),
    }
    c["data"] = data
    c["at"] = now
    return data


def crypto_movers(top: int = 10) -> dict:
    """Kripto: en çok yükselen / düşen / işlem gören (24s USD hacim). CoinGecko top-100."""
    now = time.time()
    c = _movers_cache.setdefault("crypto", {"at": 0.0, "data": None})
    if c["data"] and now - c["at"] < 180:  # 3 dk
        return c["data"]
    empty = {"currency": "USD", "count": 0, "gainers": [], "losers": [], "most_traded": []}
    try:
        with httpx.Client(timeout=15.0, headers=_UA) as cl:
            r = cl.get(_CG_MARKETS, params={
                "vs_currency": "usd", "order": "market_cap_desc",
                "per_page": 100, "page": 1, "price_change_percentage": "24h",
            })
            arr = r.json()
    except Exception:  # noqa: BLE001
        return c["data"] or empty
    if not isinstance(arr, list) or not arr:
        return c["data"] or empty
    rows: list[dict] = []
    for x in arr:
        ch = x.get("price_change_percentage_24h")
        rows.append({
            "code": (x.get("symbol") or "").upper(), "name": x.get("name"),
            "price": x.get("current_price"),
            "change": (ch / 100.0) if ch is not None else None,
            "volume": x.get("total_volume"),
        })
    with_chg = [r for r in rows if r["change"] is not None]
    with_vol = [r for r in rows if r["volume"] is not None]
    data = {
        "currency": "USD", "count": len(rows),
        "gainers": sorted(with_chg, key=lambda x: x["change"], reverse=True)[:top],
        "losers": sorted(with_chg, key=lambda x: x["change"])[:top],
        "most_traded": sorted(with_vol, key=lambda x: x["volume"], reverse=True)[:top],
    }
    c["data"] = data
    c["at"] = now
    return data


def board_movers(name: str) -> dict:
    """Pano için günün enleri (bist/crypto)."""
    if name == "bist":
        return bist_movers()
    if name == "crypto":
        return crypto_movers()
    return {"currency": None, "count": 0, "gainers": [], "losers": [], "most_traded": []}
