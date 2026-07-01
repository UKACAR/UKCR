"""Portföy uçları: CRUD, işlem ekleme/listeleme, özet (XIRR/K-Z/stopaj)."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models import Portfolio, Transaction, User
from app.db.session import get_db
from app.ingestion import store
from app.schemas import (
    ImportResult,
    PortfolioCreate,
    PortfolioOut,
    SummaryOut,
    TransactionCreate,
    TransactionOut,
)
from app.services import csvio
from app.services.performance import portfolio_performance
from app.services.returns import portfolio_summary

router = APIRouter(prefix="/api/portfolios", tags=["portfolios"])


def _owned_portfolio(db: Session, user: User, portfolio_id: int) -> Portfolio:
    p = db.get(Portfolio, portfolio_id)
    if p is None or p.user_id != user.id:
        raise HTTPException(status_code=404, detail="Portföy bulunamadı")
    return p


@router.get("", response_model=list[PortfolioOut])
def list_portfolios(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.execute(select(Portfolio).where(Portfolio.user_id == user.id)).scalars().all()


@router.post("", response_model=PortfolioOut, status_code=201)
def create_portfolio(
    body: PortfolioCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    p = Portfolio(user_id=user.id, name=body.name)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@router.get("/{portfolio_id}/transactions", response_model=list[TransactionOut])
def list_transactions(
    portfolio_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    p = _owned_portfolio(db, user, portfolio_id)
    return (
        db.execute(
            select(Transaction)
            .where(Transaction.portfolio_id == p.id)
            .order_by(Transaction.trade_date)
        )
        .scalars()
        .all()
    )


@router.post("/{portfolio_id}/transactions", response_model=TransactionOut, status_code=201)
def add_transaction(
    portfolio_id: int,
    body: TransactionCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    p = _owned_portfolio(db, user, portfolio_id)

    inst = store.resolve_instrument(db, body.fund_code)
    if inst is None:
        raise HTTPException(status_code=404, detail=f"Fon bulunamadı: {body.fund_code.upper()}")

    price = body.price
    if price is None:
        nav = store.nav_on_or_before(db, inst.id, body.trade_date)
        if nav is None:
            raise HTTPException(
                status_code=422,
                detail="O tarihe ait NAV bulunamadı; fiyatı elle girin (price).",
            )
        price = float(nav)

    tx = Transaction(
        portfolio_id=p.id,
        instrument_id=inst.id,
        type=body.type,
        quantity=Decimal(str(body.quantity)),
        price=Decimal(str(price)),
        trade_date=body.trade_date,
        fee=Decimal(str(body.fee)),
        note=body.note,
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return tx


@router.delete("/{portfolio_id}/transactions/{tx_id}", status_code=204)
def delete_transaction(
    portfolio_id: int,
    tx_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    p = _owned_portfolio(db, user, portfolio_id)
    tx = db.get(Transaction, tx_id)
    if tx is None or tx.portfolio_id != p.id:
        raise HTTPException(status_code=404, detail="İşlem bulunamadı")
    db.delete(tx)
    db.commit()


@router.get("/{portfolio_id}/summary", response_model=SummaryOut)
def summary(
    portfolio_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    p = _owned_portfolio(db, user, portfolio_id)
    return SummaryOut.model_validate(portfolio_summary(db, p.id))


@router.get("/{portfolio_id}/performance")
def performance(
    portfolio_id: int,
    months: int = 6,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Günlük değer/kar-zarar tablosu (son `months` ay) + dönem getirileri (TWR)."""
    p = _owned_portfolio(db, user, portfolio_id)
    return portfolio_performance(db, p.id, table_months=months)


def _csv_response(text: str, filename: str) -> Response:
    return Response(
        content=text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{portfolio_id}/export/transactions.csv")
def export_transactions(
    portfolio_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    p = _owned_portfolio(db, user, portfolio_id)
    txs = (
        db.execute(
            select(Transaction)
            .where(Transaction.portfolio_id == p.id)
            .order_by(Transaction.trade_date)
        )
        .scalars()
        .all()
    )
    return _csv_response(csvio.transactions_to_csv(txs), f"islemler_p{p.id}.csv")


@router.get("/{portfolio_id}/export/positions.csv")
def export_positions(
    portfolio_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    p = _owned_portfolio(db, user, portfolio_id)
    return _csv_response(
        csvio.positions_to_csv(portfolio_summary(db, p.id)), f"pozisyonlar_p{p.id}.csv"
    )


@router.post("/{portfolio_id}/import/transactions", response_model=ImportResult)
def import_transactions(
    portfolio_id: int,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    p = _owned_portfolio(db, user, portfolio_id)
    text = file.file.read().decode("utf-8-sig", errors="replace")
    rows, errors = csvio.parse_transactions_csv(text)

    imported = 0
    for row in rows:
        inst = store.resolve_instrument(db, row["fund_code"])
        if inst is None:
            errors.append(f"{row['fund_code']}: fon bulunamadı")
            continue
        price = row["price"]
        if price is None:
            nav = store.nav_on_or_before(db, inst.id, row["trade_date"])
            if nav is None:
                errors.append(f"{row['fund_code']} {row['trade_date']}: NAV yok, fiyat girilmemiş")
                continue
            price = float(nav)
        db.add(
            Transaction(
                portfolio_id=p.id,
                instrument_id=inst.id,
                type=row["type"],
                quantity=Decimal(str(row["quantity"])),
                price=Decimal(str(price)),
                trade_date=row["trade_date"],
                fee=Decimal(str(row["fee"])),
                note=row["note"],
            )
        )
        imported += 1
    db.commit()
    return ImportResult(imported=imported, errors=errors)
