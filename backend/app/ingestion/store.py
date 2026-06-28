"""TEFAS verisini veritabanına yazan ingestion servisi.

Komutlar (backend/ PYTHONPATH'te):
    python -m app.ingestion.store funds [YAT|EMK|BYF]   # fon listesini upsert et
    python -m app.ingestion.store prices <KOD> [periyod] # tek fonun NAV geçmişini yaz
    python -m app.ingestion.store all [periyod] [limit]  # tüm fonların fiyatlarını güncelle
    python -m app.ingestion.store demo                   # liste + 5 örnek fon (hızlı kanıt)
"""

from __future__ import annotations

import sys
import time
from decimal import Decimal

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import KIND_BES, KIND_ETF, KIND_FON, Instrument, Price
from app.db.session import SessionLocal
from app.ingestion import tefas

TEFAS_KIND_TO_INSTRUMENT = {"YAT": KIND_FON, "EMK": KIND_BES, "BYF": KIND_ETF}


def upsert_funds(db: Session, kind: str = "YAT", *, client: httpx.Client | None = None) -> int:
    """Liste ucundaki tüm fonları instruments tablosuna upsert eder."""
    infos = tefas.list_funds(kind, client=client)
    our_kind = TEFAS_KIND_TO_INSTRUMENT[kind]
    existing = {i.code: i for i in db.execute(select(Instrument)).scalars()}
    for fi in infos:
        inst = existing.get(fi.code)
        if inst is None:
            inst = Instrument(code=fi.code)
            db.add(inst)
            existing[fi.code] = inst
        inst.kind = our_kind
        inst.title = fi.title
        inst.fund_type_desc = fi.kind_desc
        inst.risk = fi.risk
        inst.status = fi.status
        inst.ret_1m, inst.ret_3m, inst.ret_6m = fi.ret_1m, fi.ret_3m, fi.ret_6m
        inst.ret_ytd, inst.ret_1y = fi.ret_ytd, fi.ret_1y
        inst.ret_3y, inst.ret_5y = fi.ret_3y, fi.ret_5y
    db.commit()
    return len(infos)


def ingest_prices(
    db: Session, code: str, period_months: int = 60, *, client: httpx.Client | None = None
) -> int:
    """Bir fonun NAV geçmişini prices tablosuna upsert eder. Yazılan/güncellenen satır sayısı."""
    code = code.upper().strip()
    prices = tefas.fetch_prices(code, period_months=period_months, client=client)
    if not prices:
        return 0

    inst = db.execute(select(Instrument).where(Instrument.code == code)).scalar_one_or_none()
    if inst is None:
        inst = Instrument(code=code, kind=KIND_FON, title=prices[-1].title)
        db.add(inst)
        db.flush()
    elif not inst.title and prices[-1].title:
        inst.title = prices[-1].title

    existing = {
        p.date: p
        for p in db.execute(select(Price).where(Price.instrument_id == inst.id)).scalars()
    }
    written = 0
    for fp in prices:
        val = Decimal(str(fp.price))
        if val <= 0:  # geçersiz NAV (ör. ihraç günü 0) — atla
            continue
        row = existing.get(fp.date)
        if row is None:
            db.add(
                Price(
                    instrument_id=inst.id,
                    date=fp.date,
                    price=val,
                    category_rank=fp.category_rank,
                    category_total=fp.category_total,
                )
            )
            written += 1
        else:
            row.price = val
            row.category_rank = fp.category_rank
            row.category_total = fp.category_total
    db.commit()
    return written


def ingest_all_prices(
    db: Session,
    period_months: int = 1,
    limit: int | None = None,
    *,
    sleep: float = 0.15,
    progress: bool = False,
) -> tuple[int, int]:
    """Tüm (veya ilk `limit`) enstrümanın fiyatlarını günceller. (işlenen_fon, yazılan_satır)."""
    codes = [c for (c,) in db.execute(select(Instrument.code)).all()]
    if limit:
        codes = codes[:limit]
    total_rows = 0
    with tefas.build_client() as client:
        for idx, code in enumerate(codes, 1):
            try:
                total_rows += ingest_prices(db, code, period_months, client=client)
            except Exception as e:  # noqa: BLE001  (tek fon hatası tüm job'u düşürmesin)
                if progress:
                    print(f"  ! {code}: {type(e).__name__}: {e}")
            if sleep:
                time.sleep(sleep)
            if progress and idx % 50 == 0:
                print(f"  {idx}/{len(codes)} ... ({total_rows} satır)")
    return len(codes), total_rows


def resolve_instrument(
    db: Session, code: str, *, period_months: int = 12
) -> Instrument | None:
    """Enstrümanı koddan bulur; yoksa TEFAS'tan çekip oluşturur (fiyatlarıyla)."""
    code = code.upper().strip()
    inst = db.execute(select(Instrument).where(Instrument.code == code)).scalar_one_or_none()
    if inst is None:
        ingest_prices(db, code, period_months)
        inst = db.execute(select(Instrument).where(Instrument.code == code)).scalar_one_or_none()
    return inst


def nav_on_or_before(db: Session, instrument_id: int, d) -> Decimal | None:
    """Verilen tarihte veya ondan önceki en yakın NAV (işlem fiyatı otomatik doldurma için)."""
    row = (
        db.execute(
            select(Price)
            .where(Price.instrument_id == instrument_id, Price.date <= d)
            .order_by(Price.date.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )
    return row.price if row else None


def _summary(db: Session) -> None:
    ni = db.scalar(select(func.count(Instrument.id))) or 0
    np_ = db.scalar(select(func.count(Price.id))) or 0
    print(f"DB durumu: {ni} enstrüman, {np_} fiyat kaydı")


def _main(argv: list[str]) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

    cmd = argv[1] if len(argv) > 1 else "demo"
    with SessionLocal() as db:
        if cmd == "funds":
            kind = argv[2] if len(argv) > 2 else "YAT"
            n = upsert_funds(db, kind)
            print(f"{n} fon upsert edildi ({kind}).")
        elif cmd == "prices":
            if len(argv) < 3:
                print("Kullanım: store prices <KOD> [periyod]")
                return 2
            period = int(argv[3]) if len(argv) > 3 else 60
            n = ingest_prices(db, argv[2], period)
            print(f"{argv[2].upper()}: {n} fiyat kaydı yazıldı/güncellendi.")
        elif cmd == "all":
            period = int(argv[2]) if len(argv) > 2 else 1
            limit = int(argv[3]) if len(argv) > 3 else None
            c, r = ingest_all_prices(db, period, limit, progress=True)
            print(f"{c} fon işlendi, {r} fiyat kaydı yazıldı/güncellendi.")
        elif cmd == "demo":
            n = upsert_funds(db, "YAT")
            print(f"{n} fon upsert edildi (YAT).")
            codes = [c for (c,) in db.execute(select(Instrument.code).limit(5)).all()]
            with tefas.build_client() as client:
                for code in codes:
                    k = ingest_prices(db, code, 3, client=client)
                    print(f"  {code}: {k} fiyat kaydı")
        else:
            print(f"Bilinmeyen komut: {cmd}")
            return 2
        _summary(db)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
