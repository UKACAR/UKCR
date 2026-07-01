"""Fon hisse/menkul kıymet bazlı dökümü.

Kaynak: fonun resmî AYLIK portföy raporu (KAP standart "Fon Portföy Değeri
Tablosu", PDF). Kurucu sitesinden yakalanan `report_url` (şu an İş Portföy)
pdfplumber ile ayrıştırılıp her kalem (kod + ad + portföydeki %) çıkarılır.
Rapor aylık yayınlandığından sonuç 12 saat cache'lenir.

Not: Tüm kurucular bu raporu uygulamaya açık PDF olarak vermez; report_url yoksa
döküm boş döner ve üst katman resmî rapor linkini / gösterge içeriği sunar.
"""

from __future__ import annotations

import io
import re
import time

import httpx
from sqlalchemy.orm import Session

from app.services import market
from app.services.allocation import get_allocation

# Yarı iletken fonlarında (döküm ayrıştırılamazsa) gösterge içerik: öne çıkan
# küresel yarı iletken hisseleri + canlı günlük değişim. Fonun birebir portföyü
# DEĞİLDİR; "içinde bu tür hisseler bulunur" fikri verir.
_SEMI_TOP = [
    ("NVDA", "NVIDIA"), ("AVGO", "Broadcom"), ("AMD", "Advanced Micro Devices"),
    ("TSM", "TSMC"), ("QCOM", "Qualcomm"), ("TXN", "Texas Instruments"),
    ("INTC", "Intel"), ("MU", "Micron"), ("ADI", "Analog Devices"),
    ("LRCX", "Lam Research"), ("KLAC", "KLA"), ("AMAT", "Applied Materials"),
    ("MRVL", "Marvell"), ("ASML", "ASML"),
]
_semi_cache: dict = {"at": 0.0, "data": None}

_UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}
_ISIN = re.compile(r"\b([A-Z]{2}[A-Z0-9]{9,10})\b")
_TICKER = re.compile(r"\s*([A-Z][A-Z0-9]{1,5})\b")
# Satır sonundaki 1-3 ondalık (raporun grup/portföy oranları). Sonuncusu portföy %.
_TAIL = re.compile(r"((?:\d{1,3}[.,]\d{2,6}\s+){0,2}\d{1,3}[.,]\d{2,6})\s*$")

_cache: dict[str, dict] = {}
_TTL = 12 * 3600


def _dec(x: str) -> float:
    """'2.18' veya '2,18' -> 2.18; '138,707,441.11' -> 138707441.11."""
    x = x.strip()
    if x.count(",") == 1 and "." not in x:  # Türkçe ondalık
        x = x.replace(",", ".")
    else:
        x = x.replace(",", "")
    try:
        return float(x)
    except ValueError:
        return 0.0


def parse_kap_pdf(pdf_bytes: bytes) -> list[dict]:
    """KAP portföy raporu PDF'inden kalemleri (kod, ad, %, değer, yabancı) çıkarır."""
    import pdfplumber

    agg: dict[str, dict] = {}
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            for line in (page.extract_text() or "").splitlines():
                mi = _ISIN.search(line)
                mt = _TAIL.search(line)
                mk = _TICKER.match(line)
                if not (mi and mt and mk):
                    continue
                isin = mi.group(1)
                ticker = mk.group(1)
                if ticker in ("US", "TL", "TR"):
                    continue
                pct = _dec(mt.group(1).split()[-1])
                if pct <= 0 or pct > 100:
                    continue
                foreign = not isin.startswith("TR")
                # ad: para birimi/tip işaretiyle ISIN arası (best-effort)
                seg = line[mk.end():mi.start()]
                name = re.sub(r"\b(TL|US EQUITY|USD|EQUITY)\b", " ", seg)
                name = re.sub(r"\s+", " ", name).strip(" -.,")
                nums = [_dec(x) for x in re.findall(r"\d{1,3}(?:,\d{3})+\.\d+", line)]
                value = max(nums) if nums else 0.0

                a = agg.setdefault(ticker, {"code": ticker, "name": name, "pct": 0.0,
                                            "value": 0.0, "foreign": foreign})
                a["pct"] += pct
                a["value"] += value
                if len(name) > len(a["name"]):
                    a["name"] = name

    items = sorted(agg.values(), key=lambda x: x["pct"], reverse=True)
    for it in items:
        it["pct"] = round(it["pct"], 2)
        it["value"] = round(it["value"], 2)
    return items


def semi_index_holdings() -> list[dict]:
    """Öne çıkan küresel yarı iletken hisseleri + canlı günlük değişim (60 sn cache)."""
    now = time.time()
    if _semi_cache["data"] and now - _semi_cache["at"] < 60:
        return _semi_cache["data"]
    out: list[dict] = []
    for sym, name in _SEMI_TOP:
        q = market.quote_one(sym)
        if not q:
            continue
        price, prev = q
        out.append({
            "code": sym, "name": name, "price": price,
            "change": (price / prev - 1.0) if prev else None,
        })
    if out:
        _semi_cache["data"] = out
        _semi_cache["at"] = now
    return out


def _is_semiconductor(title: str) -> bool:
    # upper() dotless ı'yı zaten I yapar; İ'yi de I'ya indir → "YARI ILETKEN".
    t = (title or "").upper().replace("İ", "I")
    return "YARI ILETKEN" in t or "SEMICONDUCTOR" in t


def fund_holdings(db: Session, code: str) -> dict:
    """Fonun hisse bazlı dökümü: {holdings, as_of, source_url, report_url, parsed, note}."""
    code = code.upper()
    c = _cache.get(code)
    if c and time.time() - c["at"] < _TTL:
        data = c["data"]
        # Gösterge endeks canlıdır — cache'lenmiş rapor verisini korurken tazele
        # (aksi halde frontend'in 60 sn yoklaması 12 saat aynı fiyatı görürdü).
        if data.get("index_name"):
            data = {**data, "index_holdings": semi_index_holdings()}
        return data

    try:
        alloc = get_allocation(db, code, refresh=False)
    except Exception:  # noqa: BLE001
        alloc = None
    alloc = alloc or {}
    report_url = alloc.get("report_url")
    source_url = alloc.get("source_url")
    snaps = alloc.get("snapshots") or []
    as_of = snaps[0].get("as_of") if snaps else None

    holdings: list[dict] = []
    parsed = False
    note = None
    if report_url:
        try:
            with httpx.Client(timeout=45.0, headers=_UA, follow_redirects=True) as client:
                r = client.get(report_url)
            # Content-type'a güvenme: Pusula application/pdf deyip Java-serialized
            # blob dönebiliyor — yalnız gerçek PDF imzasını kabul et.
            if r.content[:5] == b"%PDF-":
                holdings = parse_kap_pdf(r.content)
                parsed = bool(holdings)
            if not parsed:
                note = "Resmî rapor bu fon için ayrıştırılamadı; rapor linkinden görebilirsiniz."
        except Exception as e:  # noqa: BLE001
            note = f"Rapor okunamadı ({type(e).__name__}); rapor linkinden görebilirsiniz."
    else:
        note = "Bu fonun kurucusu hisse bazlı dökümü uygulamaya açık vermiyor; resmî rapora bakın."

    # Ayrıştırılamayan YARI İLETKEN fonları için gösterge içerik (endeks hisseleri).
    title = alloc.get("title") or ""
    index_holdings = None
    index_name = None
    if not parsed and _is_semiconductor(title):
        index_holdings = semi_index_holdings()
        index_name = "Küresel yarı iletken (temsili)"

    data = {
        "code": code,
        "title": title or None,
        "as_of": as_of,
        "source_url": source_url,
        "report_url": report_url,
        "parsed": parsed,
        "count": len(holdings),
        "holdings": holdings,
        "index_name": index_name,
        "index_holdings": index_holdings,
        "note": note,
    }
    _cache[code] = {"at": time.time(), "data": data}
    return data
