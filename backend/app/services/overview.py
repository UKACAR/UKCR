"""Günün Özeti: en çok kazanan/kaybeden fonlar (piyasa verisi market.py'de)."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Instrument, Price


def top_fund_movers(
    db: Session, kind: str | None = None, limit: int = 10
) -> tuple[list[dict], list[dict], date | None]:
    """Son günlük NAV değişimine göre en çok kazanan/kaybeden fonlar (kind: FON/ETF/BES)."""
    max_date = db.scalar(select(func.max(Price.date)))
    if max_date is None:
        return [], [], None

    window_start = max_date - timedelta(days=12)
    price_q = select(Price.instrument_id, Price.date, Price.price).where(Price.date >= window_start)
    if kind:
        price_q = price_q.where(
            Price.instrument_id.in_(select(Instrument.id).where(Instrument.kind == kind))
        )
    rows = db.execute(price_q.order_by(Price.instrument_id, Price.date)).all()

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
