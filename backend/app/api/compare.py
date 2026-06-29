"""Fon karşılaştırma ucu: birden çok fonun getiri/risk metrikleri + rebased grafik.

period_days seçilen pencereyi (1H=7, 1A=30, 3A=90, 1Y=365, ...) belirler;
grafik o pencereye kırpılır, metrikler tam geçmişten hesaplanır.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Instrument, Price
from app.db.session import get_db
from app.ingestion import store
from app.schemas import CompareMetrics, CompareResponse
from app.services import analytics


def _ingest_months(days: int) -> int:
    """Gün penceresini TEFAS'ın kabul ettiği en küçük yeterli periyoda (ay) çevirir."""
    for m in (1, 3, 6, 12, 36, 60):
        if m * 31 >= days:
            return m
    return 60


router = APIRouter(prefix="/api/compare", tags=["compare"])


@router.get("", response_model=CompareResponse)
def compare(
    codes: str = Query(..., description="Virgülle ayrılmış fon kodları (en çok 6)"),
    period_days: int = Query(365, description="Pencere (gün): 7/30/90/365/1095/1825"),
    db: Session = Depends(get_db),
):
    code_list = [c.strip().upper() for c in codes.split(",") if c.strip()][:6]
    months = _ingest_months(period_days)

    metrics: list[CompareMetrics] = []
    series_by_code: dict[str, list[tuple]] = {}

    with store.tefas.build_client() as client:
        for code in code_list:
            store.ingest_prices(db, code, months, client=client)
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
            # Metrikler tam geçmişten; grafik seçilen pencereye kırpılır
            metrics.append(
                CompareMetrics(code=code, title=inst.title, **analytics.compute_metrics(series))
            )
            if series:
                cutoff = series[-1][0] - timedelta(days=period_days)
                series_by_code[code] = [(d, p) for d, p in series if d >= cutoff]
            else:
                series_by_code[code] = []

    chart = analytics.build_rebased_chart(series_by_code)
    return CompareResponse(funds=metrics, chart=chart)
