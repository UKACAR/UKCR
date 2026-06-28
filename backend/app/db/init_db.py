"""Tablo oluşturma ve temel tohum (seed) verisi.

Çalıştırma (backend/ PYTHONPATH'te olacak şekilde):
    python -m app.db.init_db
"""

from __future__ import annotations

from datetime import date

from app.db import models  # noqa: F401  (modelleri Base.metadata'ya kaydeder)
from app.db.base import Base
from app.db.models import TaxRate
from app.db.session import SessionLocal, engine

# Yatırım fonu kazançlarında stopaj — İKTİSAP (alış) tarihine göre.
# Kaynak: Resmî Gazete kararları; oran zamanla değişti. (rate ondalık: 0.175 = %17.5)
# NOT: Bilgi amaçlıdır, vergi tavsiyesi değildir; "(Hisse Senedi Yoğun Fon)" = %0 ayrıca ele alınır.
_STOPAJ_TAKVIMI = [
    (date(2020, 12, 23), date(2024, 4, 30), 0.0, "0% dönemi"),
    (date(2024, 5, 1), date(2024, 10, 31), 0.075, "%7.5"),
    (date(2024, 11, 1), date(2025, 1, 31), 0.10, "%10"),
    (date(2025, 2, 1), date(2025, 7, 8), 0.15, "%15"),
    (date(2025, 7, 9), None, 0.175, "%17.5 (09.07.2025'ten itibaren)"),
]


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _migrate_sqlite()
    _seed_tax_rates()


# Basit SQLite migration'ı (üretimde Alembic'e taşınacak). create_all mevcut
# tabloya yeni kolon EKLEMEZ; bu yüzden eksik kolonları elle ALTER ile ekleriz.
_NEW_COLUMNS = {
    "instruments": [
        ("buy_valor_days", "INTEGER"),
        ("sell_valor_days", "INTEGER"),
        ("redemption_notice_days", "INTEGER"),
        ("valor_note", "VARCHAR(255)"),
    ],
}


def _migrate_sqlite() -> None:
    if not engine.url.get_backend_name().startswith("sqlite"):
        return
    with engine.begin() as conn:
        for table, columns in _NEW_COLUMNS.items():
            existing = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
            for col, ddl in columns:
                if col not in existing:
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")


def _seed_tax_rates() -> None:
    with SessionLocal() as db:
        if db.query(TaxRate).count() > 0:
            return
        db.add_all(
            TaxRate(valid_from=vf, valid_to=vt, rate=r, note=n)
            for vf, vt, r, n in _STOPAJ_TAKVIMI
        )
        db.commit()


if __name__ == "__main__":
    init_db()
    print("Tablolar oluşturuldu:")
    for t in Base.metadata.sorted_tables:
        print(f"  - {t.name}")
    with SessionLocal() as db:
        print(f"Stopaj takvimi kayıtları: {db.query(TaxRate).count()}")
