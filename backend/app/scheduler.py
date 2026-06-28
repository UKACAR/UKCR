"""Gecelik veri güncelleme (APScheduler).

Kullanım:
  - Uygulama içi: settings.enable_scheduler=True ise FastAPI açılışında başlar.
  - Bağımsız:
        python -m app.scheduler once         # bir kez çalıştır (tutulan fonlar)
        python -m app.scheduler once --all    # bir kez, TÜM fonlar
        python -m app.scheduler start         # zamanlayıcıyı blocking çalıştır

İş: fon listesini/getirilerini tazeler ve (varsayılan) portföylerde TUTULAN
fonların NAV'larını günceller. TEFAS NAV'ları akşam yayınlar; varsayılan 20:00.
Üretimde Celery/RQ + Redis'e taşınabilir.
"""

from __future__ import annotations

import sys
from datetime import datetime

from sqlalchemy import select

from app.core.config import settings
from app.db.models import Instrument, Transaction
from app.db.session import SessionLocal
from app.ingestion import store


def run_daily_update(*, only_tracked: bool = True) -> dict:
    """Fon metadatasını tazeler + (tutulan/tüm) fonların NAV'larını günceller."""
    with SessionLocal() as db:
        funds_n = store.upsert_funds(db, "YAT")
        if only_tracked:
            ids = [i for (i,) in db.execute(select(Transaction.instrument_id).distinct()).all()]
            codes = (
                [c for (c,) in db.execute(select(Instrument.code).where(Instrument.id.in_(ids))).all()]
                if ids
                else []
            )
        else:
            codes = [c for (c,) in db.execute(select(Instrument.code)).all()]

        rows = 0
        if codes:
            with store.tefas.build_client() as client:
                for code in codes:
                    try:
                        rows += store.ingest_prices(db, code, 1, client=client)
                    except Exception:  # noqa: BLE001  (tek fon hatası job'u düşürmesin)
                        pass
        return {"funds_refreshed": funds_n, "price_codes": len(codes), "price_rows": rows}


def _job() -> None:
    res = run_daily_update()
    print(f"[{datetime.now():%Y-%m-%d %H:%M}] Günlük güncelleme: {res}")


def start_scheduler():
    """FastAPI içinde arka planda çalışan zamanlayıcı (handle döndürür)."""
    from apscheduler.schedulers.background import BackgroundScheduler

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        _job, "cron", hour=settings.daily_update_hour, minute=0,
        id="daily_update", replace_existing=True,
    )
    scheduler.start()
    return scheduler


def _main(argv: list[str]) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

    cmd = argv[1] if len(argv) > 1 else "once"
    if cmd == "once":
        res = run_daily_update(only_tracked="--all" not in argv)
        print(f"Güncelleme tamam: {res}")
    elif cmd == "start":
        from apscheduler.schedulers.blocking import BlockingScheduler

        sched = BlockingScheduler()
        sched.add_job(_job, "cron", hour=settings.daily_update_hour, minute=0)
        print(f"Zamanlayıcı başladı (her gün {settings.daily_update_hour:02d}:00). Ctrl+C ile çık.")
        try:
            sched.start()
        except (KeyboardInterrupt, SystemExit):
            pass
    else:
        print("Kullanım: python -m app.scheduler [once|once --all|start]")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
