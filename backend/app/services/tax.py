"""Stopaj (withholding) tahmini — iktisap tarihine göre.

NOT: Bilgilendirme amaçlıdır, vergi tavsiyesi DEĞİLDİR. Oranlar tax_rates
tablosundan (iktisap tarihine göre) okunur. "(Hisse Senedi Yoğun Fon)" %0
kabul edilir. Gerçek hayatta tutma süresi muafiyetleri (>1 yıl / >2 yıl) ve
fon türüne özel istisnalar vardır; bunlar ileride eklenecek.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import Instrument, TaxRate
from app.services.valuation import RemainingLot

_ZERO = Decimal("0")


def rate_for_date(db: Session, d) -> float:
    """Verilen iktisap tarihinde geçerli stopaj oranını (ondalık) döndürür."""
    row = (
        db.execute(
            select(TaxRate)
            .where(TaxRate.valid_from <= d)
            .where(or_(TaxRate.valid_to.is_(None), TaxRate.valid_to >= d))
            .order_by(TaxRate.valid_from.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )
    return row.rate if row else 0.0


def is_equity_intensive(instrument: Instrument) -> bool:
    """'(Hisse Senedi Yoğun Fon)' tespiti -> %0 stopaj."""
    text = f"{instrument.fund_type_desc or ''} {instrument.title or ''}".lower()
    return "yoğun" in text or "yogun" in text


def estimate_stopaj(
    db: Session, instrument: Instrument, lots: list[RemainingLot], last_price: Decimal
) -> Decimal:
    """Bugün satılırsa kalan lotlar üzerinden tahmini stopaj (sadece kâr eden lotlar)."""
    if is_equity_intensive(instrument):
        return _ZERO
    total = _ZERO
    for lot in lots:
        gain = (last_price - lot.unit_cost) * lot.quantity
        if gain > 0:
            total += gain * Decimal(str(rate_for_date(db, lot.acquisition_date)))
    return total
