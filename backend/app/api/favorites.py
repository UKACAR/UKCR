"""Favoriler (izleme listesi) — fon (TEFAS) ve hisse (BİST/Yahoo) karışık.

Fonlar `instruments`/`prices` tablosundan zenginleştirilir (son NAV + günlük
değişim). Hisseler Yahoo Finance'tan canlı çekilir (10 dk cache). Liste,
okuma anında güncel fiyatlarla doldurulur.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models import FAV_FUND, FAV_STOCK, Favorite, Instrument, Price, User
from app.db.session import get_db
from app.ingestion import store
from app.schemas import FavoriteCreate, FavoriteOut
from app.services import market

router = APIRouter(prefix="/api/favorites", tags=["favorites"])


def _fund_quote(db: Session, code: str) -> tuple[str | None, float | None, float | None, date | None]:
    """Fon için (başlık, son NAV, günlük değişim, son tarih)."""
    inst = db.execute(
        select(Instrument).where(Instrument.code == code)
    ).scalars().first()
    if inst is None:
        return None, None, None, None
    rows = (
        db.execute(
            select(Price.price, Price.date)
            .where(Price.instrument_id == inst.id)
            .order_by(Price.date.desc())
            .limit(2)
        )
        .all()
    )
    if not rows:
        return inst.title, None, None, None
    last = float(rows[0][0])
    last_date = rows[0][1]
    change = None
    if len(rows) >= 2 and rows[1][0]:
        prev = float(rows[1][0])
        if prev:
            change = last / prev - 1.0
    return inst.title, last, change, last_date


def _enrich(db: Session, fav: Favorite) -> FavoriteOut:
    out = FavoriteOut.model_validate(fav)
    out.title = fav.title or fav.code
    if fav.type == FAV_FUND:
        title, last, change, last_date = _fund_quote(db, fav.code)
        if title:
            out.title = title
        out.last_price = last
        out.change = change
        out.last_date = last_date
    else:  # STOCK
        q = market.quote_one(f"{fav.code}.IS")
        if q:
            last, prev = q
            out.last_price = last
            out.change = (last / prev - 1.0) if prev else None
    return out


@router.get("", response_model=list[FavoriteOut])
def list_favorites(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    favs = (
        db.execute(
            select(Favorite)
            .where(Favorite.user_id == user.id)
            .order_by(Favorite.sort, Favorite.created_at)
        )
        .scalars()
        .all()
    )
    return [_enrich(db, f) for f in favs]


@router.post("", response_model=FavoriteOut, status_code=201)
def add_favorite(
    body: FavoriteCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    code = body.code.strip().upper()
    if not code:
        raise HTTPException(status_code=422, detail="Kod boş olamaz")

    existing = (
        db.execute(
            select(Favorite).where(
                Favorite.user_id == user.id,
                Favorite.type == body.type,
                Favorite.code == code,
            )
        )
        .scalars()
        .first()
    )
    if existing is not None:
        return _enrich(db, existing)  # zaten ekli — idempotent

    if body.type == FAV_FUND:
        inst = store.resolve_instrument(db, code)
        if inst is None:
            raise HTTPException(status_code=404, detail=f"Fon bulunamadı: {code}")
        title = inst.title or code
    else:  # STOCK
        q = market.quote_one(f"{code}.IS")
        if q is None:
            raise HTTPException(status_code=404, detail=f"Hisse bulunamadı: {code}")
        title = code

    fav = Favorite(user_id=user.id, type=body.type, code=code, title=title)
    db.add(fav)
    db.commit()
    db.refresh(fav)
    return _enrich(db, fav)


@router.delete("/{fav_id}", status_code=204)
def delete_favorite(
    fav_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    f = db.get(Favorite, fav_id)
    if f is None or f.user_id != user.id:
        raise HTTPException(status_code=404, detail="Favori bulunamadı")
    db.delete(f)
    db.commit()
