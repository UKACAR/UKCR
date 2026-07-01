"""Gecelik veri güncelleme (APScheduler).

Kullanım:
  - Uygulama içi: settings.enable_scheduler=True ise FastAPI açılışında başlar.
  - Bağımsız:
        python -m app.scheduler once           # tam güncelleme (tüm fonlar)
        python -m app.scheduler once --tracked  # sadece tutulan fonlar (hızlı)
        python -m app.scheduler start           # zamanlayıcıyı blocking çalıştır

İş: fon evrenlerini (YAT/EMK/BYF) tazeler, fonların NAV'larını günceller ve
piyasa (Yahoo) cache'ini ısıtır. Her tür hataya dayanıklı (biri başarısız olsa
da diğerleri devam eder). TEFAS NAV'ları akşam yayınlar; varsayılan saat 20:00.
Üretimde Celery/RQ + Redis'e taşınabilir.
"""

from __future__ import annotations

import sys
from datetime import datetime

from sqlalchemy import select

from app.core.config import settings
from app.db.models import Instrument, Transaction
from app.db.session import SessionLocal
from app.ingestion import store, tefas
from app.services import market

_TEFAS_KINDS = ("YAT", "EMK", "BYF")


def run_daily_update(*, only_tracked: bool = False) -> dict:
    """Fon evrenleri + NAV'lar + piyasa cache'ini günceller."""
    funds: dict[str, object] = {}
    with SessionLocal() as db:
        # 1) Fon evrenlerini tazele (her tür hataya dayanıklı; EMK ara sıra timeout verir)
        with tefas.build_client(timeout=60.0) as client:
            for kind in _TEFAS_KINDS:
                try:
                    funds[kind] = store.upsert_funds(db, kind, client=client)
                except Exception as e:  # noqa: BLE001
                    funds[kind] = f"hata: {type(e).__name__}"

        # 2) NAV güncelle (tüm fonlar ya da sadece tutulanlar)
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
            with tefas.build_client() as client:
                for code in codes:
                    try:
                        rows += store.ingest_prices(db, code, 1, client=client)
                    except Exception:  # noqa: BLE001
                        pass

    # 3) Piyasa (Yahoo) cache'ini ısıt
    try:
        market.snapshot()
    except Exception:  # noqa: BLE001
        pass

    return {"funds": funds, "price_codes": len(codes), "price_rows": rows}


def _job() -> None:
    res = run_daily_update()
    print(f"[{datetime.now():%Y-%m-%d %H:%M}] Günlük güncelleme: {res}")


def _ai_job() -> None:
    """AI günlük piyasa raporunu yeniden üretir (her gün ai_report_hour'da)."""
    from app.services import ai_report

    try:
        with SessionLocal() as db:
            ai_report.generate(db)
        print(f"[{datetime.now():%Y-%m-%d %H:%M}] AI raporu güncellendi.")
    except Exception as e:  # noqa: BLE001
        print(f"[{datetime.now():%Y-%m-%d %H:%M}] AI raporu hatası: {type(e).__name__}")


def start_scheduler():
    """FastAPI içinde arka planda çalışan zamanlayıcı (handle döndürür)."""
    from apscheduler.schedulers.background import BackgroundScheduler

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        _job, "cron", hour=settings.daily_update_hour, minute=0,
        id="daily_update", replace_existing=True,
    )
    scheduler.add_job(
        _ai_job, "cron", hour=settings.ai_report_hour, minute=0,
        id="ai_report", replace_existing=True,
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
        only = "--tracked" in argv
        print(f"Güncelleme başladı (only_tracked={only})...", flush=True)
        print(run_daily_update(only_tracked=only))
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
        print("Kullanım: python -m app.scheduler [once|once --tracked|start]")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
