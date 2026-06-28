"""Günün Özeti verisi: en çok kazanan/kaybeden fonlar + piyasa (döviz)."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Instrument, Price
from app.services import evds

# Döviz anlık görüntüsü günde bir değişir; tarih bazlı cache.
_market_cache: dict[str, list[dict]] = {}

_FX_PAIRS = [
    ("Dolar", "TP.DK.USD.A.YTL"),
    ("Euro", "TP.DK.EUR.A.YTL"),
]


def top_fund_movers(db: Session, limit: int = 10) -> tuple[list[dict], list[dict], date | None]:
    """Son günlük NAV değişimine göre en çok kazanan/kaybeden fonlar."""
    max_date = db.scalar(select(func.max(Price.date)))
    if max_date is None:
        return [], [], None

    window_start = max_date - timedelta(days=12)
    rows = db.execute(
        select(Price.instrument_id, Price.date, Price.price)
        .where(Price.date >= window_start)
        .order_by(Price.instrument_id, Price.date)
    ).all()

    series: dict[int, list[tuple[date, float]]] = defaultdict(list)
    for iid, d, p in rows:
        series[iid].append((d, float(p)))

    moves: list[tuple[int, float, float]] = []
    for iid, pts in series.items():
        if len(pts) >= 2 and pts[-2][1]:
            moves.append((iid, pts[-1][1] / pts[-2][1] - 1.0, pts[-1][1]))
    if not moves:
        return [], [], max_date

    insts = {
        i.id: i
        for i in db.execute(
            select(Instrument).where(Instrument.id.in_([m[0] for m in moves]))
        ).scalars()
    }
    items = [
        {"code": insts[iid].code, "title": insts[iid].title, "last_price": last, "change": chg}
        for iid, chg, last in moves
        if iid in insts and insts[iid].title
    ]
    gainers = sorted(items, key=lambda x: x["change"], reverse=True)[:limit]
    losers = sorted(items, key=lambda x: x["change"])[:limit]
    return gainers, losers, max_date


def market_snapshot(*, client: httpx.Client | None = None) -> list[dict]:
    """Döviz (EVDS): USD, EUR — son değer + günlük değişim. Anahtar yoksa boş."""
    if not settings.evds_api_key:
        return []

    cache_key = date.today().isoformat()
    if cache_key in _market_cache:
        return _market_cache[cache_key]

    end = date.today()
    start = end - timedelta(days=16)
    out: list[dict] = []
    owns = client is None
    client = client or httpx.Client(timeout=settings.request_timeout)
    try:
        for label, ser in _FX_PAIRS:
            try:
                vals = [v for _, v in evds.fetch_series(ser, start, end, client=client) if v]
                if vals:
                    change = (vals[-1] / vals[-2] - 1.0) if (len(vals) >= 2 and vals[-2]) else None
                    out.append({"label": label, "value": vals[-1], "change": change})
            except Exception:  # noqa: BLE001  (tek seri hatası diğerlerini düşürmesin)
                continue
    finally:
        if owns:
            client.close()

    _market_cache[cache_key] = out
    return out
