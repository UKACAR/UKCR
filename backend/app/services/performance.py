"""Portföy zaman serisi: günlük değer, günlük kar/zarar ve dönem getirileri (TWR).

İki mod:
- **actual**: gerçek işlem geçmişi. Günlük değer(D)=Σ(D'de tutulan adet)×NAV(D);
  günlük K/Z(D)=değer(D)−değer(D−1)−o gün net nakit akışı (yalnız fiyat hareketi).
- **backtest**: portföy son ~14 günde kurulmuşsa (anlık dağılım), MEVCUT adetler
  geçmiş NAV'larla değerlenir → "bu dağılım son 6 ay/1Y nasıl performans gösterirdi".

Günlük getiri=K/Z/değer(D−1). Dönem getirisi bu günlük getirilerin bileşiğidir
(zaman ağırlıklı getiri, nakit akışından arındırılmış).
"""

from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import TX_BUY, Instrument, Price, Transaction
from app.ingestion import store

PERIODS = [("week", 7), ("m1", 30), ("m3", 90), ("m6", 180), ("y1", 365)]


def _nav_asof(dates: list[date], navs: list[float], d: date) -> float | None:
    i = bisect_right(dates, d) - 1
    return navs[i] if i >= 0 else None


def _table_and_returns(series: list[tuple[date, float, float, float]], today: date, table_months: int) -> dict:
    tbl_cut = today - timedelta(days=table_months * 30 + 5)
    daily = [
        {"date": d.isoformat(), "value": round(v, 2), "pl": round(pl, 2), "pl_pct": round(r, 6)}
        for (d, v, pl, r) in series
        if d >= tbl_cut and v > 0
    ]
    dates = [s[0] for s in series]
    rets = [s[3] for s in series]
    pls = [s[2] for s in series]
    returns: dict[str, float | None] = {}
    returns_tl: dict[str, float | None] = {}
    for key, days in PERIODS:
        base_idx = bisect_right(dates, today - timedelta(days=days)) - 1
        if base_idx < 0:
            returns[key] = None
            returns_tl[key] = None
            continue
        prod = 1.0
        tl_sum = 0.0
        for j in range(base_idx + 1, len(series)):
            prod *= 1.0 + rets[j]
            tl_sum += pls[j]  # dönem boyunca fiyat hareketinden gelen TL K/Z
        returns[key] = round(prod - 1.0, 6)
        returns_tl[key] = round(tl_sum, 2)
    return {"daily": daily, "returns": returns, "returns_tl": returns_tl}


def portfolio_performance(db: Session, portfolio_id: int, *, table_months: int = 6) -> dict:
    txs = (
        db.execute(
            select(Transaction)
            .where(Transaction.portfolio_id == portfolio_id)
            .order_by(Transaction.trade_date)
        )
        .scalars()
        .all()
    )
    empty = {
        "mode": "none",
        "daily": [],
        "returns": {k: None for k, _ in PERIODS},
        "returns_tl": {k: None for k, _ in PERIODS},
    }
    if not txs:
        return empty

    by_fund: dict[int, list[Transaction]] = defaultdict(list)
    for t in txs:
        by_fund[t.instrument_id].append(t)
    fund_ids = list(by_fund.keys())

    today = date.today()
    range_start = today - timedelta(days=400)

    for iid in fund_ids:
        earliest = db.scalar(select(func.min(Price.date)).where(Price.instrument_id == iid))
        if earliest is None or earliest > today - timedelta(days=380):
            inst = db.get(Instrument, iid)
            if inst is not None:
                try:
                    store.ingest_prices(db, inst.code, 36)
                except Exception:  # noqa: BLE001
                    pass

    navs: dict[int, tuple[list[date], list[float]]] = {}
    axis_set: set[date] = set()
    for iid in fund_ids:
        rows = db.execute(
            select(Price.date, Price.price)
            .where(Price.instrument_id == iid, Price.date >= range_start)
            .order_by(Price.date)
        ).all()
        navs[iid] = ([r[0] for r in rows], [float(r[1]) for r in rows])
        axis_set.update(navs[iid][0])

    axis = sorted(d for d in axis_set if d <= today)
    if not axis:
        return empty

    # Portföyün GÜNCEL net dağılımını geçmiş NAV'larla değerle. İşlem fiyatı/
    # tarih tutarsızlıklarından (maliyet fiyatıyla girilen pozisyon, tek eski
    # test işlemi vb.) bağımsız ve sağlamdır → "bu dağılım son 6 ayda nasıl
    # performans gösterirdi". Günlük K/Z = güncel adetlerin piyasa değerindeki
    # günlük değişim.
    holdings: dict[int, float] = {
        iid: sum(
            float(t.quantity) if t.type == TX_BUY else -float(t.quantity)
            for t in by_fund[iid]
        )
        for iid in fund_ids
    }
    series: list[tuple[date, float, float, float]] = []
    value_prev: float | None = None
    for D in axis:
        value = 0.0
        for iid in fund_ids:
            if holdings[iid]:
                nav = _nav_asof(*navs[iid], D)
                if nav is not None:
                    value += holdings[iid] * nav
        if value_prev is not None and value_prev > 0:
            pl = value - value_prev
            ret = pl / value_prev
        else:
            pl, ret = 0.0, 0.0
        series.append((D, value, pl, ret))
        value_prev = value

    out = _table_and_returns(series, today, table_months)
    out["mode"] = "holdings"
    return out
