"""Günün Özeti ucu: piyasa (döviz) + en çok kazanan/kaybeden fonlar."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas import OverviewOut
from app.services import overview

router = APIRouter(prefix="/api/overview", tags=["overview"])


@router.get("", response_model=OverviewOut)
def get_overview(db: Session = Depends(get_db)):
    gainers, losers, as_of = overview.top_fund_movers(db)
    return OverviewOut(
        as_of=as_of,
        market=overview.market_snapshot(),
        gainers=gainers,
        losers=losers,
    )
