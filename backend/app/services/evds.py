"""TCMB EVDS — TÜFE (enflasyon) ve döviz serileri; reel getiri için.

EVDS evds3'e taşındı. Çalışan API (2026):
    GET https://evds3.tcmb.gov.tr/igmevdsms-dis/series=<SERI>&startDate=dd-mm-yyyy&endDate=dd-mm-yyyy&type=json
    Header: key: <API_ANAHTARI>   (anahtar URL'de DEĞİL header'da; aksi halde 403)

Yanıt: {"items": [{"Tarih": "2024-1", "TP_FG_J0": "1984.02", ...}, ...]}
(seri alan adı: nokta -> alt çizgi, ör. TP.FG.J0 -> TP_FG_J0)

reel getiri = (1 + nominal) / (1 + enflasyon) - 1   (nominal eksi enflasyon DEĞİL)
"""

from __future__ import annotations

from datetime import date

import httpx

from app.core.config import settings

EVDS_BASE = "https://evds3.tcmb.gov.tr/igmevdsms-dis/"
CPI_SERIES = "TP.FG.J0"          # TÜFE genel endeks (2003=100), aylık
USD_SERIES = "TP.DK.USD.A.YTL"   # USD/TRY (alış)

# Geçmiş TÜFE değişmediği için dönem enflasyonunu bellekte cache'leriz.
_inflation_cache: dict[tuple[str, str], float | None] = {}
_monthly_infl_cache: dict[tuple[str, str], dict] = {}


def monthly_inflation(
    start: date, end: date, *, client: httpx.Client | None = None
) -> dict[tuple[int, int], float]:
    """[start, end] aralığındaki aylık TÜFE enflasyonu: {(yıl, ay): oran}.

    Aylık oran = TÜFE[ay] / TÜFE[önceki ay] - 1. Anahtar yoksa boş döner.
    Yayınlanmamış (gecikmeli) güncel aylar sözlükte bulunmaz.
    """
    if not settings.evds_api_key:
        return {}
    ck = (start.isoformat(), end.isoformat())
    if ck in _monthly_infl_cache:
        return _monthly_infl_cache[ck]

    out: dict[tuple[int, int], float] = {}
    try:
        # Bir önceki ayı da iste (ilk ayın oranı için baz lazım).
        y, m = start.year, start.month - 1
        if m == 0:
            m, y = 12, y - 1
        pts: list[tuple[tuple[int, int], float]] = []
        for label, val in fetch_series(CPI_SERIES, date(y, m, 1), end, client=client):
            ym = _ym(label)
            if ym and val:
                pts.append((ym, val))
        pts.sort(key=lambda x: x[0])
        for i in range(1, len(pts)):
            prev_v = pts[i - 1][1]
            cur_ym, cur_v = pts[i]
            if prev_v:
                out[cur_ym] = cur_v / prev_v - 1.0
    except Exception:  # noqa: BLE001
        out = {}

    _monthly_infl_cache[ck] = out
    return out


def real_return(nominal: float, inflation: float) -> float:
    """Nominal ve enflasyon (ondalık oran) -> reel getiri (ondalık)."""
    return (1.0 + nominal) / (1.0 + inflation) - 1.0


def _require_key() -> str:
    if not settings.evds_api_key:
        raise RuntimeError(
            "EVDS API anahtarı tanımlı değil. backend/.env içine EVDS_API_KEY=... ekleyin "
            "(https://evds3.tcmb.gov.tr ücretsiz kayıt)."
        )
    return settings.evds_api_key


def fetch_series(
    series: str, start: date, end: date, *, client: httpx.Client | None = None
) -> list[tuple[str, float]]:
    """EVDS'ten bir seriyi çeker -> [(tarih_etiketi, değer)]. Aylık seriler için tarih 'YIL-AY'."""
    key = _require_key()
    owns = client is None
    client = client or httpx.Client(timeout=settings.request_timeout)
    field = series.replace(".", "_")
    url = (
        f"{EVDS_BASE}series={series}"
        f"&startDate={start.strftime('%d-%m-%Y')}"
        f"&endDate={end.strftime('%d-%m-%Y')}"
        "&type=json"
    )
    try:
        resp = client.get(url, headers={"key": key})
        resp.raise_for_status()
        items = resp.json().get("items", [])
    finally:
        if owns:
            client.close()

    out: list[tuple[str, float]] = []
    for it in items:
        raw = it.get(field)
        if raw in (None, "", "null"):
            continue
        try:
            out.append((it.get("Tarih", ""), float(raw)))
        except (TypeError, ValueError):
            continue
    return out


def inflation_between(cpi_start: float, cpi_end: float) -> float:
    """İki TÜFE endeks değeri arasındaki kümülatif enflasyon (ondalık)."""
    if not cpi_start:
        return 0.0
    return cpi_end / cpi_start - 1.0


def _ym(label: str) -> tuple[int, int] | None:
    """'YIL-AY' (ör. '2026-3') -> (2026, 3)."""
    try:
        y, m = label.split("-")
        return int(y), int(m)
    except (ValueError, AttributeError):
        return None


def period_inflation(
    start: date, end: date, *, client: httpx.Client | None = None
) -> float | None:
    """[start, end] dönemindeki kümülatif TÜFE enflasyonu (ondalık) ya da None.

    TÜFE aylık ve gecikmeli yayınlanır. Dönem, yayınlanan son TÜFE'den daha
    yeniyse: kapsanan kısım kesin hesaplanır, kapsanmayan güncel kuyruk son
    aylık enflasyon oranıyla tahmin edilir. Anahtar yoksa None.
    """
    if not settings.evds_api_key:
        return None
    ck = (start.isoformat(), end.isoformat())
    if ck in _inflation_cache:
        return _inflation_cache[ck]

    result: float | None = None
    try:
        # Başlangıçtan ~13 ay öncesini de iste (baz + güncel oran için)
        y, m = start.year, start.month - 13
        while m <= 0:
            m += 12
            y -= 1
        wide_start = date(y, m, 1)

        pts: list[tuple[tuple[int, int], float]] = []
        for label, val in fetch_series(CPI_SERIES, wide_start, end, client=client):
            ym = _ym(label)
            if ym and val:
                pts.append((ym, val))
        pts.sort(key=lambda x: x[0])

        if pts:
            start_ym = (start.year, start.month)
            base = next((v for ym, v in reversed(pts) if ym <= start_ym), pts[0][1])
            latest_ym, latest_v = pts[-1]
            covered = (latest_v / base - 1.0) if base else 0.0

            end_ym = (end.year, end.month)
            remaining = (end_ym[0] - latest_ym[0]) * 12 + (end_ym[1] - latest_ym[1])
            est = 0.0
            if remaining > 0 and len(pts) >= 2:
                recent = pts[-min(13, len(pts)):]
                n = len(recent) - 1
                if n > 0 and recent[0][1]:
                    monthly = (recent[-1][1] / recent[0][1]) ** (1.0 / n) - 1.0
                    est = (1.0 + monthly) ** remaining - 1.0
            result = (1.0 + covered) * (1.0 + est) - 1.0
    except Exception:  # noqa: BLE001  (EVDS hatası reel getiriyi None bıraksın)
        result = None

    _inflation_cache[ck] = result
    return result
