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
_SNAPSHOT_DAYS = 14  # ilk işlem bu kadar yakınsa portföy "anlık" → backtest


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
    returns: dict[str, float | None] = {}
    for key, days in PERIODS:
        base_idx = bisect_right(dates, today - timedelta(days=days)) - 1
        if base_idx < 0:
            returns[key] = None
            continue
        prod = 1.0
        for j in range(base_idx + 1, len(series)):
            prod *= 1.0 + rets[j]
        returns[key] = round(prod - 1.0, 6)
    return {"daily": daily, "returns": returns}


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
    empty = {"mode": "none", "daily": [], "returns": {k: None for k, _ in PERIODS}}
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

    first_tx = min(t.trade_date for t in txs)
    backtest = (today - first_tx).days < _SNAPSHOT_DAYS

    series: list[tuple[date, float, float, float]] = []
    value_prev: float | None = None

    if backtest:
        # Sabit güncel adetler geçmiş NAV'larla değerlenir.
        holdings: dict[int, float] = {}
        for iid in fund_ids:
            h = 0.0
            for t in by_fund[iid]:
                h += float(t.quantity) if t.type == TX_BUY else -float(t.quantity)
            holdings[iid] = h
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
        mode = "backtest"
    else:
        tx_ptr = {iid: 0 for iid in fund_ids}
        holdings = {iid: 0.0 for iid in fund_ids}
        for D in axis:
            netcost = 0.0
            for iid in fund_ids:
                lst = by_fund[iid]
                while tx_ptr[iid] < len(lst) and lst[tx_ptr[iid]].trade_date <= D:
                    t = lst[tx_ptr[iid]]
                    q, pr, fee = float(t.quantity), float(t.price), float(t.fee or 0)
                    if t.type == TX_BUY:
                        holdings[iid] += q
                        if t.trade_date == D:
                            netcost += q * pr + fee
                    else:
                        holdings[iid] -= q
                        if t.trade_date == D:
                            netcost -= q * pr - fee
                    tx_ptr[iid] += 1
            value = 0.0
            for iid in fund_ids:
                if holdings[iid]:
                    nav = _nav_asof(*navs[iid], D)
                    if nav is not None:
                        value += holdings[iid] * nav
            if value_prev is not None and value_prev > 0:
                pl = value - value_prev - netcost
                ret = pl / value_prev
            else:
                pl, ret = 0.0, 0.0
            series.append((D, value, pl, ret))
            value_prev = value
        mode = "actual"

    out = _table_and_returns(series, today, table_months)
    out["mode"] = mode
    return out
