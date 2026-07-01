"""Getiri ve portföy özeti: XIRR (para-ağırlıklı), K/Z, stopaj, reel getiri.

Saf çekirdek `summarize(...)` DB'den bağımsızdır; `portfolio_summary(db, ...)`
ince bir DB sarmalayıcısıdır.

Doğrudan çalıştırma (sentetik kanıt, DB'ye yazmadan):
    python -m app.services.returns
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
import math
from datetime import date
from decimal import Decimal

import pyxirr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import TX_BUY, Instrument, Price, Transaction
from app.db.session import SessionLocal
from app.services import evds, tax
from app.services.valuation import TxIn, build_positions, value_position

_ZERO = Decimal("0")


@dataclass
class PositionView:
    code: str
    title: str
    units: Decimal
    avg_cost: Decimal
    last_price: Decimal
    last_date: date | None
    cost_basis: Decimal
    market_value: Decimal
    unrealized_pl: Decimal
    realized_pl: Decimal
    total_pl: Decimal
    estimated_stopaj: Decimal


@dataclass
class Summary:
    as_of: date
    total_invested: Decimal       # toplam alış maliyeti (komisyon dahil)
    current_value: Decimal
    unrealized_pl: Decimal
    realized_pl: Decimal
    total_pl: Decimal
    simple_return: float | None   # kümülatif nominal getiri (total_pl / invested)
    xirr: float | None            # yıllık para-ağırlıklı getiri
    estimated_stopaj: Decimal
    net_value: Decimal            # current_value - estimated_stopaj
    real_return: float | None     # reel (enflasyona göre) getiri; TÜFE yoksa None
    xirr_note: str | None = None  # XIRR None ise kısa neden
    positions: list[PositionView] = field(default_factory=list)


def xirr(cashflows: list[tuple[date, float]]) -> float | None:
    """Tarihli nakit akışlarından yıllık para-ağırlıklı getiri (XIRR).

    Önce pyxirr (Newton); yakınsamazsa makul yıllık oran aralığında (-%99,99 .. +
    %10.000) bisection ile kök aranır. Kök bu aralık dışındaysa (uç/aşırı oran) ya
    da işaret karışımı yoksa None döner.
    """
    if len(cashflows) < 2:
        return None
    dates = [d for d, _ in cashflows]
    amounts = [a for _, a in cashflows]
    if not (any(a > 0 for a in amounts) and any(a < 0 for a in amounts)):
        return None

    # 1) pyxirr (Newton)
    try:
        r = pyxirr.xirr(dates, amounts)
        if r is not None and math.isfinite(r):
            return float(r)
    except Exception:  # noqa: BLE001  (yakınsamama vb.)
        pass

    # 2) Sağlam yedek: NPV'nin işaret değiştirdiği aralıkta bisection.
    t0 = min(dates)

    def _npv(rate: float) -> float:
        return sum(a / (1.0 + rate) ** ((d - t0).days / 365.0) for d, a in zip(dates, amounts))

    lo, hi = -0.9999, 100.0  # yıllık -%99,99 .. +%10.000
    try:
        flo, fhi = _npv(lo), _npv(hi)
    except (OverflowError, ZeroDivisionError):
        return None
    if not (math.isfinite(flo) and math.isfinite(fhi)) or flo * fhi > 0:
        return None  # kök aralık dışında (dönem çok kısa / uç oran)
    for _ in range(200):
        mid = (lo + hi) / 2.0
        fm = _npv(mid)
        if abs(fm) < 1e-7:
            return float(mid)
        if flo * fm < 0:
            hi = mid
        else:
            lo, flo = mid, fm
    return float((lo + hi) / 2.0)


def _xirr_note(cashflows: list[tuple[date, float]], as_of: date) -> str:
    """XIRR hesaplanamadığında kullanıcıya kısa neden."""
    neg = [(d, -a) for d, a in cashflows if a < 0]
    if len(cashflows) < 2 or not neg or not any(a > 0 for _, a in cashflows):
        return "İşlem verisi yetersiz (XIRR için alım + güncel değer gerekir)."
    inv_total = sum(a for _, a in neg)
    inv_today = sum(a for d, a in neg if d >= as_of)
    if inv_total and inv_today / inv_total >= 0.5:
        return (
            "Alışların çoğu değerleme günüyle aynı tarihli; yıllık XIRR için işlemlere "
            "gerçek alış tarihlerini girin."
        )
    return "Getiri yıllığa çevrilemedi (dönem çok kısa veya uç değer)."


def build_cashflows(txs: list[TxIn], current_value: Decimal, as_of: date) -> list[tuple[date, float]]:
    """XIRR için nakit akışları: alım negatif, satım pozitif, bugünkü değer son pozitif."""
    cfs: list[tuple[date, float]] = []
    for t in txs:
        amt = t.quantity * t.price
        if t.type == TX_BUY:
            cfs.append((t.trade_date, -float(amt + t.fee)))
        else:
            cfs.append((t.trade_date, float(amt - t.fee)))
    if current_value > 0:
        cfs.append((as_of, float(current_value)))
    return cfs


def summarize(
    txs: list[TxIn],
    instruments: dict[int, Instrument],
    price_map: dict[int, tuple[date, Decimal]],
    *,
    db: Session | None = None,
    as_of: date | None = None,
    inflation: float | None = None,
) -> Summary:
    """İşlemler + son fiyatlardan portföy özeti üretir."""
    if as_of is None:
        dates = [d for d, _ in price_map.values()]
        as_of = max(dates) if dates else date.today()

    positions = build_positions(txs)

    total_value = _ZERO
    total_unreal = _ZERO
    total_real = _ZERO
    total_stopaj = _ZERO
    views: list[PositionView] = []

    for iid, pos in positions.items():
        last = price_map.get(iid)
        last_price = last[1] if last else _ZERO
        last_date = last[0] if last else None
        vp = value_position(pos, last_price, last_date)

        inst = instruments.get(iid)
        stopaj = _ZERO
        if db is not None and inst is not None and last_price:
            stopaj = tax.estimate_stopaj(db, inst, pos.lots, last_price)

        total_value += vp.market_value
        total_unreal += vp.unrealized_pl
        total_real += vp.realized_pl
        total_stopaj += stopaj

        views.append(
            PositionView(
                code=inst.code if inst else str(iid),
                title=inst.title if inst else "",
                units=vp.units,
                avg_cost=vp.avg_cost,
                last_price=vp.last_price,
                last_date=vp.last_date,
                cost_basis=vp.cost_basis,
                market_value=vp.market_value,
                unrealized_pl=vp.unrealized_pl,
                realized_pl=vp.realized_pl,
                total_pl=vp.total_pl,
                estimated_stopaj=stopaj,
            )
        )

    total_invested = _ZERO
    for t in txs:
        if t.type == TX_BUY:
            total_invested += t.quantity * t.price + t.fee

    total_pl = total_unreal + total_real
    simple_return = float(total_pl / total_invested) if total_invested else None
    cfs = build_cashflows(txs, total_value, as_of)
    port_xirr = xirr(cfs)
    xirr_note = None if port_xirr is not None else _xirr_note(cfs, as_of)
    rreturn = (
        evds.real_return(simple_return, inflation)
        if (simple_return is not None and inflation is not None)
        else None
    )

    return Summary(
        as_of=as_of,
        total_invested=total_invested,
        current_value=total_value,
        unrealized_pl=total_unreal,
        realized_pl=total_real,
        total_pl=total_pl,
        simple_return=simple_return,
        xirr=port_xirr,
        estimated_stopaj=total_stopaj,
        net_value=total_value - total_stopaj,
        real_return=rreturn,
        xirr_note=xirr_note,
        positions=sorted(views, key=lambda v: v.market_value, reverse=True),
    )


def portfolio_summary(db: Session, portfolio_id: int, *, as_of: date | None = None) -> Summary:
    """DB'deki bir portföyün özeti."""
    txs_orm = (
        db.execute(
            select(Transaction)
            .where(Transaction.portfolio_id == portfolio_id)
            .order_by(Transaction.trade_date)
        )
        .scalars()
        .all()
    )
    txs = [
        TxIn(t.instrument_id, t.type, t.quantity, t.price, t.trade_date, t.fee or _ZERO)
        for t in txs_orm
    ]
    inst_ids = {t.instrument_id for t in txs}
    instruments = {
        i.id: i
        for i in db.execute(select(Instrument).where(Instrument.id.in_(inst_ids))).scalars()
    }
    price_map: dict[int, tuple[date, Decimal]] = {}
    for iid in inst_ids:
        row = (
            db.execute(
                select(Price).where(Price.instrument_id == iid).order_by(Price.date.desc()).limit(1)
            )
            .scalars()
            .first()
        )
        if row:
            price_map[iid] = (row.date, row.price)

    if as_of is None:
        price_dates = [d for d, _ in price_map.values()]
        as_of = max(price_dates) if price_dates else date.today()
    # Reel getiri: yatırım dönemindeki (ilk işlem -> bugün) TÜFE enflasyonu
    inflation = None
    if txs:
        inflation = evds.period_inflation(min(t.trade_date for t in txs), as_of)

    return summarize(txs, instruments, price_map, db=db, as_of=as_of, inflation=inflation)


# --------------------------------------------------------------------------- #
# Sentetik kanıt (DB'ye yazmadan): gerçek fiyat serisi üzerinde örnek işlemler
# --------------------------------------------------------------------------- #
def _demo() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

    with SessionLocal() as db:
        # En çok fiyat kaydı olan enstrümanı seç
        iid = db.execute(
            select(Price.instrument_id)
            .group_by(Price.instrument_id)
            .order_by(func.count(Price.id).desc())
            .limit(1)
        ).scalar_one_or_none()
        if iid is None:
            print("Önce veri yükleyin: python -m app.ingestion.store demo")
            return 2

        inst = db.get(Instrument, iid)
        prices = (
            db.execute(select(Price).where(Price.instrument_id == iid).order_by(Price.date))
            .scalars()
            .all()
        )
        first, mid, last = prices[0], prices[len(prices) // 2], prices[-1]

        # Sentetik işlemler: 1000 al, sonra 500 al, sonra 300 sat
        txs = [
            TxIn(iid, "BUY", Decimal("1000"), first.price, first.date),
            TxIn(iid, "BUY", Decimal("500"), mid.price, mid.date),
            TxIn(iid, "SELL", Decimal("300"), last.price, last.date),
        ]
        price_map = {iid: (last.date, last.price)}
        s = summarize(txs, {iid: inst}, price_map, db=db, as_of=last.date)

        print(f"Fon: {inst.code} — {inst.title}")
        print(f"Tür: {inst.fund_type_desc or '-'} | Risk: {inst.risk or '-'}")
        print(f"\nSentetik işlemler:")
        for t in txs:
            print(f"  {t.trade_date}  {t.type:<4} {t.quantity} adet @ {t.price}")

        print(f"\n=== ÖZET (as_of {s.as_of}) ===")
        print(f"  Yatırılan (maliyet) : {s.total_invested:,.2f} TL")
        print(f"  Güncel değer        : {s.current_value:,.2f} TL")
        print(f"  Gerçekleşmemiş K/Z  : {s.unrealized_pl:,.2f} TL")
        print(f"  Gerçekleşen K/Z     : {s.realized_pl:,.2f} TL")
        print(f"  Toplam K/Z          : {s.total_pl:,.2f} TL")
        sr = f"%{s.simple_return*100:.2f}" if s.simple_return is not None else "-"
        xr = f"%{s.xirr*100:.2f}" if s.xirr is not None else "-"
        print(f"  Kümülatif getiri    : {sr}")
        print(f"  XIRR (yıllık)       : {xr}")
        print(f"  Tahmini stopaj      : {s.estimated_stopaj:,.2f} TL")
        print(f"  Net değer (vergi -) : {s.net_value:,.2f} TL")
        rr = f"%{s.real_return*100:.2f}" if s.real_return is not None else "- (TÜFE/EVDS anahtarı gerekli)"
        print(f"  Reel getiri         : {rr}")

        print(f"\n  Pozisyonlar:")
        for v in s.positions:
            print(
                f"    {v.code}: {v.units} adet, ort.maliyet {v.avg_cost:.6f}, "
                f"son {v.last_price:.6f}, değer {v.market_value:,.2f}, "
                f"gerç.olmayan K/Z {v.unrealized_pl:,.2f}, stopaj {v.estimated_stopaj:,.2f}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(_demo())
