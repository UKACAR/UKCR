"""Pozisyon ve maliyet hesabı (lot bazlı, FIFO).

İşlemler (transactions) değişmez lot kayıtlarıdır; pozisyon, maliyet ve
gerçekleşen/gerçekleşmemiş K/Z bunlardan türetilir. Stopaj, kalan lotların
İKTİSAP tarihine göre uygulanacağı için lotlar tarihiyle birlikte tutulur.

Bu modül saf (DB'den bağımsız) hesap yapar; girdi `TxIn` listesidir.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.db.models import TX_BUY

_ZERO = Decimal("0")


@dataclass(frozen=True)
class TxIn:
    """Hesap için sadeleştirilmiş işlem girdisi."""
    instrument_id: int
    type: str  # BUY / SELL
    quantity: Decimal
    price: Decimal
    trade_date: date
    fee: Decimal = _ZERO


@dataclass(frozen=True)
class RemainingLot:
    """Henüz satılmamış (açık) lot — stopaj için iktisap tarihiyle."""
    acquisition_date: date
    quantity: Decimal
    unit_cost: Decimal  # alış komisyonu dahil birim maliyet


@dataclass
class Position:
    instrument_id: int
    units: Decimal              # kalan adet
    cost_basis: Decimal         # kalan lotların toplam maliyeti
    avg_cost: Decimal           # kalan lotların ortalama birim maliyeti
    realized_pl: Decimal        # gerçekleşen K/Z (satışlardan)
    lots: list[RemainingLot] = field(default_factory=list)


@dataclass
class ValuedPosition:
    instrument_id: int
    units: Decimal
    cost_basis: Decimal
    avg_cost: Decimal
    realized_pl: Decimal
    last_price: Decimal
    last_date: date | None
    market_value: Decimal
    unrealized_pl: Decimal
    total_pl: Decimal
    lots: list[RemainingLot] = field(default_factory=list)


def _dec(v) -> Decimal:
    return v if isinstance(v, Decimal) else Decimal(str(v))


def build_positions(txs: list[TxIn]) -> dict[int, Position]:
    """İşlemlerden enstrüman başına FIFO pozisyonları kurar."""
    by_inst: dict[int, list[TxIn]] = defaultdict(list)
    # Aynı gün önce alımlar işlensin ki satış mevcut lottan düşülebilsin.
    for t in sorted(txs, key=lambda x: (x.trade_date, 0 if x.type == TX_BUY else 1)):
        by_inst[t.instrument_id].append(t)

    positions: dict[int, Position] = {}
    for iid, items in by_inst.items():
        lots: deque[list] = deque()  # [qty_remaining, unit_cost, acq_date]
        realized = _ZERO
        for t in items:
            qty = _dec(t.quantity)
            price = _dec(t.price)
            fee = _dec(t.fee)
            if t.type == TX_BUY:
                total_cost = qty * price + fee
                unit_cost = (total_cost / qty) if qty else _ZERO
                lots.append([qty, unit_cost, t.trade_date])
            else:  # SELL — FIFO
                proceeds = qty * price - fee
                consumed_cost = _ZERO
                remaining = qty
                while remaining > 0 and lots:
                    lot = lots[0]
                    take = min(remaining, lot[0])
                    consumed_cost += take * lot[1]
                    lot[0] -= take
                    remaining -= take
                    if lot[0] <= 0:
                        lots.popleft()
                realized += proceeds - consumed_cost  # satılan kısmın K/Z'si

        units = sum((l[0] for l in lots), _ZERO)
        cost_basis = sum((l[0] * l[1] for l in lots), _ZERO)
        avg_cost = (cost_basis / units) if units else _ZERO
        rem = [RemainingLot(acquisition_date=l[2], quantity=l[0], unit_cost=l[1]) for l in lots]
        positions[iid] = Position(iid, units, cost_basis, avg_cost, realized, rem)
    return positions


def value_position(pos: Position, last_price: Decimal, last_date: date | None) -> ValuedPosition:
    last_price = _dec(last_price)
    market_value = pos.units * last_price
    unrealized = market_value - pos.cost_basis
    return ValuedPosition(
        instrument_id=pos.instrument_id,
        units=pos.units,
        cost_basis=pos.cost_basis,
        avg_cost=pos.avg_cost,
        realized_pl=pos.realized_pl,
        last_price=last_price,
        last_date=last_date,
        market_value=market_value,
        unrealized_pl=unrealized,
        total_pl=unrealized + pos.realized_pl,
        lots=pos.lots,
    )
