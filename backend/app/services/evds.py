"""TCMB EVDS — TÜFE (enflasyon) ve döviz serileri; reel getiri için.

API anahtarı gerekir (settings.evds_api_key). 2024-04-05 sonrası anahtar HTTP
'key' header'ında gönderilir. Anahtar yoksa fonksiyonlar açıklayıcı hata verir;
reel getiri o ana kadar None döner.

reel getiri = (1 + nominal) / (1 + enflasyon) - 1   (nominal eksi enflasyon DEĞİL)
"""

from __future__ import annotations

from datetime import date

import httpx

from app.core.config import settings

EVDS_BASE = "https://evds2.tcmb.gov.tr/service/evds/"
CPI_SERIES = "TP.FG.J0"          # TÜFE genel endeks (2003=100)
USD_SERIES = "TP.DK.USD.A.YTL"   # USD/TRY (alış)


def real_return(nominal: float, inflation: float) -> float:
    """Nominal ve enflasyon (ondalık oran) -> reel getiri (ondalık)."""
    return (1.0 + nominal) / (1.0 + inflation) - 1.0


def _require_key() -> str:
    if not settings.evds_api_key:
        raise RuntimeError(
            "EVDS API anahtarı tanımlı değil. backend/.env içine EVDS_API_KEY=... ekleyin "
            "(https://evds2.tcmb.gov.tr ücretsiz kayıt)."
        )
    return settings.evds_api_key


def fetch_series(
    series: str, start: date, end: date, *, client: httpx.Client | None = None
) -> list[tuple[str, float]]:
    """EVDS'ten bir seriyi çeker -> [(tarih_etiketi, değer)]. Aylık seriler için tarih 'AY-YIL'."""
    key = _require_key()
    owns = client is None
    client = client or httpx.Client(timeout=settings.request_timeout)
    field = series.replace(".", "_")
    params = {
        "series": series,
        "startDate": start.strftime("%d-%m-%Y"),
        "endDate": end.strftime("%d-%m-%Y"),
        "type": "json",
    }
    try:
        resp = client.get(EVDS_BASE, params=params, headers={"key": key})
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
