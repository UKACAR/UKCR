"""Vade/valör hatırlatma uçları."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models import Reminder, User
from app.db.session import get_db
from app.ingestion import store
from app.schemas import ReminderCreate, ReminderOut

router = APIRouter(prefix="/api/reminders", tags=["reminders"])


@router.get("", response_model=list[ReminderOut])
def list_reminders(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return (
        db.execute(
            select(Reminder).where(Reminder.user_id == user.id).order_by(Reminder.date)
        )
        .scalars()
        .all()
    )


@router.post("", response_model=ReminderOut, status_code=201)
def create_reminder(
    body: ReminderCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    instrument_id = None
    if body.fund_code:
        inst = store.resolve_instrument(db, body.fund_code)
        if inst is None:
            raise HTTPException(status_code=404, detail=f"Fon bulunamadı: {body.fund_code.upper()}")
        instrument_id = inst.id
    r = Reminder(
        user_id=user.id,
        instrument_id=instrument_id,
        title=body.title,
        date=body.date,
        kind=body.kind,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


@router.patch("/{reminder_id}", response_model=ReminderOut)
def update_reminder(
    reminder_id: int,
    done: bool,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    r = db.get(Reminder, reminder_id)
    if r is None or r.user_id != user.id:
        raise HTTPException(status_code=404, detail="Hatırlatma bulunamadı")
    r.done = done
    db.commit()
    db.refresh(r)
    return r


@router.delete("/{reminder_id}", status_code=204)
def delete_reminder(
    reminder_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    r = db.get(Reminder, reminder_id)
    if r is None or r.user_id != user.id:
        raise HTTPException(status_code=404, detail="Hatırlatma bulunamadı")
    db.delete(r)
    db.commit()
