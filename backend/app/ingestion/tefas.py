"""TEFAS veri çekme adaptörü.

TEFAS'ın yeni SPA arka ucu (2026) iki JSON ucu sunar:

    POST /api/funds/fonGetiriBazliBilgiGetir   -> fon listesi + dönem getirileri
    POST /api/funds/fonFiyatBilgiGetir         -> tek fonun günlük NAV geçmişi

Eski ``/api/DB/BindHistoryInfo`` ve ``BindHistoryAllocation`` uçları 2026'da
kapatıldı ("Method not found or disabled!" / ERR-006). Yeni uç; fon büyüklüğü
(AUM), yatırımcı sayısı ve varlık dağılımı GEÇMİŞİNİ artık yayınlamıyor —
yalnızca NAV (pay fiyatı) + kategori sırası + dönem getirileri var.

İstek gövdesi JSON'dur (eski API'deki gibi form değil). Geçmiş, sabit "periyod"
(ay) enum'u ile çekilir: {1, 3, 6, 12, 36, 60}; azami 5 yıl. Tarayıcı benzeri
header'lar gerekir. Fiyatlar günlüktür (T+1 kapanış NAV'ı), anlık değildir.

Doğrudan çalıştırma (Faz 0 testi):
    python tefas.py [FONKODU]
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from datetime import date, datetime

import httpx

TEFAS_BASE = "https://www.tefas.gov.tr"
PRICE_ENDPOINT = "/api/funds/fonFiyatBilgiGetir"
LIST_ENDPOINT = "/api/funds/fonGetiriBazliBilgiGetir"

# API'nin kabul ettiği geçmiş periyotları (ay). Başka değer "Sistem Hatası!!" döner.
VALID_PERIODS = (1, 3, 6, 12, 36, 60)
FUND_KINDS = ("YAT", "EMK", "BYF")  # menkul kıymet fonu / BES / borsa yatırım fonu (ETF)


@dataclass(frozen=True)
class FundInfo:
    """Liste ucundan gelen fon özeti (karşılaştırma/keşif için)."""
    code: str               # fonKodu
    title: str              # fonUnvan
    kind_desc: str          # fonTurAciklama (ör. "Altın Fonu")
    risk: int | None        # riskDegeri (1-7)
    status: str | None      # tefasDurum
    ret_1m: float | None    # getiri1a
    ret_3m: float | None    # getiri3a
    ret_6m: float | None    # getiri6a
    ret_ytd: float | None   # getiriyb (yılbaşından bugüne)
    ret_1y: float | None    # getiri1y
    ret_3y: float | None    # getiri3y
    ret_5y: float | None    # getiri5y


@dataclass(frozen=True)
class FundPrice:
    """Fiyat ucundan gelen tek günlük NAV kaydı."""
    code: str                   # fonKodu
    title: str                  # fonUnvan
    date: date                  # tarih
    price: float                # fiyat (pay fiyatı / NAV)
    category_rank: int | None   # kategoriDerece
    category_total: int | None  # kategoriFonSay


def _headers() -> dict[str, str]:
    """WAF'ı geçmek için tarayıcı benzeri header'lar."""
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
        "Origin": TEFAS_BASE,
        "Referer": f"{TEFAS_BASE}/",
        "X-Requested-With": "XMLHttpRequest",
    }


def build_client(timeout: float = 30.0) -> httpx.Client:
    """Yeniden kullanılabilir, doğru header'lı bir TEFAS HTTP istemcisi döndürür."""
    return httpx.Client(timeout=timeout, headers=_headers())


def _f(v):
    if v in (None, "", "-"):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _i(v):
    f = _f(v)
    return int(f) if f is not None else None


def snap_period(start: date, today: date | None = None) -> int:
    """İstenen başlangıç tarihini API'nin kabul ettiği en yakın (>=) periyoda yuvarlar."""
    today = today or datetime.now().date()
    delta_days = max(0, (today - start).days)
    months_needed = math.ceil(delta_days / 30) + 1
    for p in VALID_PERIODS:
        if p >= months_needed:
            return p
    return VALID_PERIODS[-1]


def list_funds(kind: str = "YAT", *, client: httpx.Client | None = None) -> list[FundInfo]:
    """Verilen türdeki tüm fonları dönem getirileriyle birlikte döndürür.

    kind: YAT = menkul kıymet yatırım fonları, EMK = BES, BYF = ETF.
    """
    assert kind in FUND_KINDS, f"kind ∈ {FUND_KINDS}"
    owns = client is None
    client = client or httpx.Client(timeout=30.0, headers=_headers())
    payload = {
        "dil": "TR", "fonTipi": kind, "kurucuKodu": None, "sfonTurKod": None,
        "fonTurAciklama": None, "islem": 1, "fonTurKod": None, "fonGrubu": None,
        "donemGetiri1a": "1", "donemGetiri3a": "1", "donemGetiri6a": "1",
        "donemGetiri1y": "1", "donemGetiriyb": "1", "donemGetiri3y": "1",
        "donemGetiri5y": "1", "basTarih": None, "bitTarih": None,
        "calismaTipi": 2, "getiriOrani": "1",
    }
    try:
        resp = client.post(TEFAS_BASE + LIST_ENDPOINT, json=payload)
        resp.raise_for_status()
        rows = resp.json().get("resultList") or []
    finally:
        if owns:
            client.close()

    out: list[FundInfo] = []
    for r in rows:
        code = (r.get("fonKodu") or "").strip()
        if not code:
            continue
        out.append(
            FundInfo(
                code=code,
                title=(r.get("fonUnvan") or "").strip(),
                kind_desc=(r.get("fonTurAciklama") or "").strip(),
                risk=_i(r.get("riskDegeri")),
                status=(r.get("tefasDurum") or None),
                ret_1m=_f(r.get("getiri1a")),
                ret_3m=_f(r.get("getiri3a")),
                ret_6m=_f(r.get("getiri6a")),
                ret_ytd=_f(r.get("getiriyb")),
                ret_1y=_f(r.get("getiri1y")),
                ret_3y=_f(r.get("getiri3y")),
                ret_5y=_f(r.get("getiri5y")),
            )
        )
    return out


def fetch_prices(
    fonkod: str,
    period_months: int = 1,
    *,
    start: date | None = None,
    end: date | None = None,
    client: httpx.Client | None = None,
) -> list[FundPrice]:
    """Bir fonun günlük NAV geçmişini (tarihe göre artan) döndürür.

    period_months: {1,3,6,12,36,60} ay. `start` verilirse uygun periyoda yuvarlanır.
    start/end verilirse sonuç o tarih penceresine kırpılır.
    """
    if start is not None:
        period_months = snap_period(start)
    if period_months not in VALID_PERIODS:
        period_months = next((p for p in VALID_PERIODS if p >= period_months), VALID_PERIODS[-1])

    owns = client is None
    client = client or httpx.Client(timeout=30.0, headers=_headers())
    payload = {"fonKodu": fonkod.upper().strip(), "dil": "TR", "periyod": period_months}
    try:
        resp = client.post(TEFAS_BASE + PRICE_ENDPOINT, json=payload)
        resp.raise_for_status()
        rows = resp.json().get("resultList") or []
    finally:
        if owns:
            client.close()

    out: list[FundPrice] = []
    for r in rows:
        try:
            dt = datetime.strptime(r.get("tarih"), "%Y-%m-%d").date()
        except (TypeError, ValueError):
            continue
        out.append(
            FundPrice(
                code=(r.get("fonKodu") or "").strip(),
                title=(r.get("fonUnvan") or "").strip(),
                date=dt,
                price=_f(r.get("fiyat")) or 0.0,
                category_rank=_i(r.get("kategoriDerece")),
                category_total=_i(r.get("kategoriFonSay")),
            )
        )
    out.sort(key=lambda p: p.date)
    if start:
        out = [p for p in out if p.date >= start]
    if end:
        out = [p for p in out if p.date <= end]
    return out


def _main(argv: list[str]) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Windows konsolunda Türkçe karakter
    except Exception:  # noqa: BLE001
        pass

    fonkod = argv[1] if len(argv) > 1 else None
    try:
        with httpx.Client(timeout=30.0, headers=_headers()) as client:
            funds = list_funds("YAT", client=client)
            print(f"Fon listesi (YAT): {len(funds)} fon\n")
            print(f"{'KOD':<6}{'AD':<44}{'1Y %':>8}{'RİSK':>6}")
            for fi in funds[:5]:
                r1y = f"{fi.ret_1y:.1f}" if fi.ret_1y is not None else "-"
                print(f"{fi.code:<6}{fi.title[:42]:<44}{r1y:>8}{str(fi.risk or '-'):>6}")

            fonkod = fonkod or funds[0].code
            print(f"\nFiyat geçmişi: {fonkod} (son ~1 ay)")
            prices = fetch_prices(fonkod, period_months=1, client=client)
            if not prices:
                print("Veri yok — fon kodunu kontrol et.")
                return 2

            print(f"{len(prices)} kayıt. Fon: {prices[-1].title}\n")
            print(f"{'TARİH':<12}{'FİYAT':>14}{'KAT. SIRA':>12}")
            for p in prices[-10:]:
                rank = f"{p.category_rank}/{p.category_total}" if p.category_rank is not None else "-"
                print(f"{p.date.isoformat():<12}{p.price:>14.6f}{rank:>12}")

            first, last = prices[0], prices[-1]
            if first.price:
                chg = (last.price / first.price - 1) * 100
                print(f"\nDönem getirisi ({first.date} -> {last.date}): %{chg:.2f}")
    except httpx.HTTPStatusError as e:
        print(f"HTTP hata: {e.response.status_code}\n{(e.response.text or '')[:400]}")
        return 1
    except Exception as e:  # noqa: BLE001  (Faz 0 tanı amaçlı)
        print(f"Hata: {type(e).__name__}: {e}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
