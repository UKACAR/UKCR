"""Fon karşılaştırma ucu: birden çok fonun getiri/risk metrikleri + rebased grafik."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Instrument, Price
from app.db.session import get_db
from app.ingestion import store
from app.schemas import CompareMetrics, CompareResponse
from app.services import analytics

router = APIRouter(prefix="/api/compare", tags=["compare"])


@router.get("", response_model=CompareResponse)
def compare(
    codes: str = Query(..., description="Virgülle ayrılmış fon kodları (en çok 6)"),
    period: int = Query(12, description="Kaç aylık pencere (1,3,6,12,36,60)"),
    db: Session = Depends(get_db),
):
    code_list = [c.strip().upper() for c in codes.split(",") if c.strip()][:6]

    metrics: list[CompareMetrics] = []
    series_by_code: dict[str, list[tuple]] = {}

    with store.tefas.build_client() as client:
        for code in code_list:
            # İstenen pencereyi garanti et (yoksa/eksikse TEFAS'tan çek)
            store.ingest_prices(db, code, period, client=client)
            inst = db.execute(select(Instrument).where(Instrument.code == code)).scalars().first()
            if inst is None:
                continue
            rows = (
                db.execute(
                    select(Price).where(Price.instrument_id == inst.id).order_by(Price.date)
                )
                .scalars()
                .all()
            )
            series = [(r.date, float(r.price)) for r in rows]
            series_by_code[code] = series
            metrics.append(
                CompareMetrics(code=code, title=inst.title, **analytics.compute_metrics(series))
            )

    chart = analytics.build_rebased_chart(series_by_code)
    return CompareResponse(funds=metrics, chart=chart)
