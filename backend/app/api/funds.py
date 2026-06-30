"""Fon uçları: arama/listeleme, detay, fiyat serisi."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.models import Instrument, Price
from app.db.session import get_db
from app.ingestion import store
from app.schemas import FundDetail, FundListItem, PriceOut, ValorUpdate
from app.services import valor
from app.services.allocation import get_allocation

router = APIRouter(prefix="/api/funds", tags=["funds"])


@router.get("", response_model=list[FundListItem])
def list_funds(
    q: str | None = Query(None, description="Kod veya ad içinde arama"),
    kind: str | None = Query(None, description="FON / BES / ETF / HISSE"),
    limit: int = Query(50, le=1000),
    db: Session = Depends(get_db),
):
    stmt = select(Instrument)
    if kind:
        stmt = stmt.where(Instrument.kind == kind.upper())
    if q:
        like = f"%{q.upper()}%"
        stmt = stmt.where(or_(Instrument.code.like(like), func.upper(Instrument.title).like(like)))
    stmt = stmt.order_by(Instrument.code).limit(limit)
    return db.execute(stmt).scalars().all()


def _get_instrument(db: Session, code: str) -> Instrument:
    inst = db.execute(select(Instrument).where(Instrument.code == code.upper())).scalars().first()
    if inst is None:
        raise HTTPException(status_code=404, detail=f"Fon bulunamadı: {code.upper()}")
    return inst


def _fund_detail_payload(db: Session, inst: Instrument) -> FundDetail:
    last = (
        db.execute(
            select(Price).where(Price.instrument_id == inst.id).order_by(Price.date.desc()).limit(1)
        )
        .scalars()
        .first()
    )
    count = db.scalar(select(func.count(Price.id)).where(Price.instrument_id == inst.id)) or 0
    out = FundDetail.model_validate(inst)
    if last:
        out.last_price = float(last.price)
        out.last_date = last.date
        out.category_rank = last.category_rank
        out.category_total = last.category_total
    out.price_count = count
    if inst.sell_valor_days is not None:
        out.settlement_if_sold_today = valor.settlement_date(
            date.today(), inst.sell_valor_days, inst.redemption_notice_days
        )
    return out


@router.get("/{code}", response_model=FundDetail)
def fund_detail(code: str, db: Session = Depends(get_db)):
    return _fund_detail_payload(db, _get_instrument(db, code))


@router.patch("/{code}/valor", response_model=FundDetail)
def set_valor(code: str, body: ValorUpdate, db: Session = Depends(get_db)):
    inst = _get_instrument(db, code)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(inst, key, value)
    db.commit()
    db.refresh(inst)
    return _fund_detail_payload(db, inst)


def _monthly_returns(
    db: Session, instrument_id: int, n_years: int = 3, *, real: bool = False
) -> list[dict]:
    """Son n_years takvim yılı için aylık % getiriler (ay-sonu NAV'larından).

    Aylık getiri = ay_sonu_NAV / önceki_ay_sonu_NAV - 1. Yıl toplamı, o yılın
    mevcut aylık getirilerinin bileşik çarpımıdır (Oca→Ara = Ara/önceki_Ara).
    real=True ise her ay EVDS aylık TÜFE'siyle reelleştirilir
    ((1+nominal)/(1+enflasyon)-1); enflasyonu olmayan (gecikmeli) aylar nominal kalır.
    """
    rows = db.execute(
        select(Price.date, Price.price)
        .where(Price.instrument_id == instrument_id)
        .order_by(Price.date)
    ).all()
    if not rows:
        return []
    # her (yıl, ay) için ay-sonu (en geç tarihli) NAV
    month_end: dict[tuple[int, int], tuple[date, float]] = {}
    for d, p in rows:
        key = (d.year, d.month)
        cur = month_end.get(key)
        if cur is None or d > cur[0]:
            month_end[key] = (d, float(p))
    keys = sorted(month_end)
    ret: dict[tuple[int, int], float] = {}
    for i in range(1, len(keys)):
        prev = month_end[keys[i - 1]][1]
        cur = month_end[keys[i]][1]
        if prev:
            ret[keys[i]] = cur / prev - 1.0

    last_year = keys[-1][0]
    first_year = last_year - n_years + 1

    if real and ret:
        from app.services import evds

        last_ym = keys[-1]
        infl = evds.monthly_inflation(date(first_year, 1, 1), date(last_ym[0], last_ym[1], 1))
        if infl:
            for k in list(ret.keys()):
                if k in infl:
                    ret[k] = evds.real_return(ret[k], infl[k])

    out: list[dict] = []
    for y in range(first_year, last_year + 1):
        months = [ret.get((y, m)) for m in range(1, 13)]
        vals = [v for v in months if v is not None]
        total = None
        if vals:
            prod = 1.0
            for v in vals:
                prod *= 1.0 + v
            total = round(prod - 1.0, 6)
        out.append({
            "year": y,
            "months": [round(v, 6) if v is not None else None for v in months],
            "total": total,
        })
    return out


@router.get("/{code}/monthly-returns")
def fund_monthly_returns(
    code: str,
    years: int = Query(3, ge=1, le=5),
    real: bool = Query(False, description="Reel (TÜFE'den arındırılmış) aylık getiri"),
    db: Session = Depends(get_db),
):
    """Fonun son `years` takvim yılı için aylık % getiri tablosu (nominal veya reel)."""
    inst = db.execute(select(Instrument).where(Instrument.code == code.upper())).scalars().first()
    count = (
        db.scalar(select(func.count(Price.id)).where(Price.instrument_id == inst.id))
        if inst is not None
        else 0
    ) or 0
    # 3+ yıllık tablo için yeterli geçmiş yoksa daha uzun çek (≈ günlük 250/yıl).
    if inst is None or count < 250 * years:
        store.ingest_prices(db, code, 60)
        inst = db.execute(select(Instrument).where(Instrument.code == code.upper())).scalars().first()
    if inst is None:
        raise HTTPException(status_code=404, detail=f"Fon bulunamadı: {code.upper()}")
    return {"code": code.upper(), "real": real, "rows": _monthly_returns(db, inst.id, years, real=real)}


@router.get("/{code}/allocation")
def fund_allocation(
    code: str,
    refresh: bool = Query(True, description="Kurucu sitesinden canlı çek"),
    db: Session = Depends(get_db),
):
    """Fonun varlık/portföy dağılımı (kurucu resmî sitesinden) + son 3 güncelleme + değişim."""
    return get_allocation(db, code, refresh=refresh)


@router.get("/{code}/prices", response_model=list[PriceOut])
def fund_prices(
    code: str,
    period: int = Query(12, description="Kaç aylık geçmiş (1,3,6,12,36,60)"),
    refresh: bool = Query(False, description="TEFAS'tan yeniden çek"),
    db: Session = Depends(get_db),
):
    inst = db.execute(select(Instrument).where(Instrument.code == code.upper())).scalars().first()
    has_prices = (
        inst is not None
        and db.scalar(select(func.count(Price.id)).where(Price.instrument_id == inst.id))
    )
    if inst is None or refresh or not has_prices:
        store.ingest_prices(db, code, period)
        inst = db.execute(select(Instrument).where(Instrument.code == code.upper())).scalars().first()
    if inst is None:
        raise HTTPException(status_code=404, detail=f"Fon bulunamadı: {code.upper()}")
    rows = (
        db.execute(select(Price).where(Price.instrument_id == inst.id).order_by(Price.date))
        .scalars()
        .all()
    )
    return rows
