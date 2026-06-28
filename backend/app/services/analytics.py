"""Fon analitiği: NAV serisinden getiri, volatilite, max düşüş ve rebased seri.

Getirileri TEFAS'ın hazır alanlarına güvenmek yerine NAV geçmişinden kendimiz
hesaplarız (tutarlı ve şeffaf). Tüm fonlar aynı yöntemle ölçülür.
"""

from __future__ import annotations

import math
from datetime import date, timedelta

Series = list[tuple[date, float]]


def _price_on_or_before(series: Series, target: date) -> float | None:
    prior = None
    for d, p in series:
        if d <= target:
            prior = p
        else:
            break
    return prior


def window_return(series: Series, days: int) -> float | None:
    if not series:
        return None
    last_d, last_p = series[-1]
    base = _price_on_or_before(series, last_d - timedelta(days=days))
    if not base:
        return None
    return last_p / base - 1.0


def ytd_return(series: Series) -> float | None:
    if not series:
        return None
    last_d, last_p = series[-1]
    jan1 = date(last_d.year, 1, 1)
    base = next((p for d, p in series if d >= jan1), None)
    if not base:
        return None
    return last_p / base - 1.0


def volatility(series: Series) -> float | None:
    """Günlük getirilerin yıllıklandırılmış standart sapması (~252 işlem günü)."""
    if len(series) < 3:
        return None
    rets = [
        series[i][1] / series[i - 1][1] - 1.0
        for i in range(1, len(series))
        if series[i - 1][1]
    ]
    if len(rets) < 2:
        return None
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    return math.sqrt(var) * math.sqrt(252)


def max_drawdown(series: Series) -> float | None:
    """En yüksek tepeden en derin dibe oransal düşüş (negatif)."""
    if not series:
        return None
    peak = None
    mdd = 0.0
    for _, p in series:
        if peak is None or p > peak:
            peak = p
        if peak:
            mdd = min(mdd, p / peak - 1.0)
    return mdd


def compute_metrics(series: Series) -> dict:
    last_d, last_p = (series[-1] if series else (None, None))
    return {
        "last_price": last_p,
        "last_date": last_d,
        "ret_1m": window_return(series, 30),
        "ret_3m": window_return(series, 90),
        "ret_6m": window_return(series, 180),
        "ret_1y": window_return(series, 365),
        "ret_ytd": ytd_return(series),
        "volatility": volatility(series),
        "max_drawdown": max_drawdown(series),
    }


def build_rebased_chart(series_by_code: dict[str, Series]) -> list[dict]:
    """Tüm serileri ORTAK başlangıç tarihinden 100'e normalize edip birleştirir.

    Karşılaştırma yalnızca ortak bir başlangıçtan anlamlıdır; bu yüzden tüm
    fonların verisinin bulunduğu en geç ilk-tarih (common start) baz alınır ve
    her fon o tarihte 100'den başlar. Çıktı recharts için hazır:
    [{date, KOD1: 100.0, KOD2: 100.0}, ...].
    """
    present = {c: s for c, s in series_by_code.items() if s}
    if not present:
        return []

    common_start = max(s[0][0] for s in present.values())  # en geç ilk-tarih

    rebased: dict[str, dict[date, float]] = {}
    all_dates: set[date] = set()
    for code, series in present.items():
        windowed = [(d, p) for d, p in series if d >= common_start]
        if not windowed:
            continue
        base = windowed[0][1] or 1.0
        rebased[code] = {d: p / base * 100.0 for d, p in windowed}
        all_dates.update(rebased[code])

    out: list[dict] = []
    for d in sorted(all_dates):
        row: dict = {"date": d.isoformat()}
        for code in rebased:
            v = rebased[code].get(d)
            row[code] = round(v, 2) if v is not None else None
        out.append(row)
    return out
