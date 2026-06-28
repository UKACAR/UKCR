"""Fon NAV (fiyat) eşik alarmları.

Alarm durumu okuma anında canlı hesaplanır (en güncel NAV vs eşik). İlk kez
tetiklendiğinde triggered_at damgalanır. (Üretimde gecelik job da değerlendirir.)
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models import ALARM_ABOVE, ALARM_BELOW, Alarm, Price, User
from app.db.session import get_db
from app.ingestion import store
from app.schemas import AlarmCreate, AlarmOut

router = APIRouter(prefix="/api/alarms", tags=["alarms"])


def _latest_price(db: Session, instrument_id: int) -> float | None:
    row = (
        db.execute(
            select(Price.price)
            .where(Price.instrument_id == instrument_id)
            .order_by(Price.date.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )
    return float(row) if row is not None else None


def _is_triggered(kind: str, threshold: float, last_price: float | None) -> bool:
    if last_price is None:
        return False
    if kind == ALARM_ABOVE:
        return last_price >= threshold
    if kind == ALARM_BELOW:
        return last_price <= threshold
    return False


def _to_out(alarm: Alarm, last_price: float | None, triggered: bool) -> AlarmOut:
    out = AlarmOut.model_validate(alarm)
    out.last_price = last_price
    out.triggered = triggered
    return out


@router.get("", response_model=list[AlarmOut])
def list_alarms(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    alarms = (
        db.execute(
            select(Alarm).where(Alarm.user_id == user.id).order_by(Alarm.created_at.desc())
        )
        .scalars()
        .all()
    )
    result: list[AlarmOut] = []
    changed = False
    for a in alarms:
        lp = _latest_price(db, a.instrument_id)
        triggered = a.active and _is_triggered(a.kind, a.threshold, lp)
        if triggered and a.triggered_at is None:
            a.triggered_at = datetime.now(timezone.utc)
            changed = True
        result.append(_to_out(a, lp, triggered))
    if changed:
        db.commit()
    return result


@router.post("", response_model=AlarmOut, status_code=201)
def create_alarm(
    body: AlarmCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    inst = store.resolve_instrument(db, body.fund_code)
    if inst is None:
        raise HTTPException(status_code=404, detail=f"Fon bulunamadı: {body.fund_code.upper()}")
    a = Alarm(
        user_id=user.id,
        instrument_id=inst.id,
        kind=body.kind,
        threshold=body.threshold,
        note=body.note,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    lp = _latest_price(db, a.instrument_id)
    return _to_out(a, lp, a.active and _is_triggered(a.kind, a.threshold, lp))


@router.patch("/{alarm_id}", response_model=AlarmOut)
def toggle_alarm(
    alarm_id: int,
    active: bool,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    a = db.get(Alarm, alarm_id)
    if a is None or a.user_id != user.id:
        raise HTTPException(status_code=404, detail="Alarm bulunamadı")
    a.active = active
    if not active:
        a.triggered_at = None  # tekrar aktifleşince yeniden tetiklenebilsin
    db.commit()
    db.refresh(a)
    lp = _latest_price(db, a.instrument_id)
    return _to_out(a, lp, a.active and _is_triggered(a.kind, a.threshold, lp))


@router.delete("/{alarm_id}", status_code=204)
def delete_alarm(
    alarm_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    a = db.get(Alarm, alarm_id)
    if a is None or a.user_id != user.id:
        raise HTTPException(status_code=404, detail="Alarm bulunamadı")
    db.delete(a)
    db.commit()
