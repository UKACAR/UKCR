"""Günün Özeti uçları: piyasa, en çok kazanan/kaybeden (kind'e göre), haberler."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Price
from app.db.session import get_db
from app.schemas import IndexPoint, MoversOut, NewsItem, OverviewOut
from app.services import market, news, overview

router = APIRouter(prefix="/api", tags=["overview"])


@router.get("/overview", response_model=OverviewOut)
def get_overview(db: Session = Depends(get_db)):
    as_of = db.scalar(select(func.max(Price.date)))
    return OverviewOut(as_of=as_of, market=market.snapshot())


@router.get("/index", response_model=list[IndexPoint])
def get_index(symbol: str = Query("XU100.IS"), range: str = Query("1mo")):
    return market.index_chart(symbol, range)


@router.get("/movers", response_model=MoversOut)
def get_movers(
    kind: str = Query("FON", description="FON / ETF / BES"),
    db: Session = Depends(get_db),
):
    gainers, losers, as_of = overview.top_fund_movers(db, kind=kind)
    return MoversOut(as_of=as_of, gainers=gainers, losers=losers)


@router.get("/news", response_model=list[NewsItem])
def get_news():
    return news.latest()


@router.get("/metals")
def get_metals():
    """Kıymetli madenler: USD/TL fiyat + günlük değişim."""
    return market.precious_metals()


@router.get("/metals/news", response_model=list[NewsItem])
def get_metals_news():
    return news.metals_news()
