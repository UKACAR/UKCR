"""Veritabanı motoru ve oturum (session) yönetimi."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

_is_sqlite = settings.database_url.startswith("sqlite")
# timeout: eşzamanlı yazımlarda "database is locked" yerine 30 sn beklesin
_connect_args = {"check_same_thread": False, "timeout": 30.0} if _is_sqlite else {}

engine = create_engine(
    settings.database_url,
    echo=False,
    future=True,
    connect_args=_connect_args,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    """FastAPI bağımlılığı: istek başına bir oturum."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
