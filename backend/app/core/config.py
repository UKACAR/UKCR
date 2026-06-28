"""Uygulama ayarları (pydantic-settings).

Ortam değişkenleri veya backend/.env üzerinden geçersiz kılınabilir.
Örn. üretimde:  DATABASE_URL=postgresql+psycopg://user:pass@host/db
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# .../backend  (config.py -> core -> app -> backend)
BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    # .env'i çalışma dizininden bağımsız olarak backend/ altında ara
    model_config = SettingsConfigDict(env_file=str(BACKEND_DIR / ".env"), extra="ignore")

    app_name: str = "UKCR API"
    debug: bool = True

    # Geliştirmede SQLite (dosya backend/ altında); üretimde Postgres'e geçilir.
    database_url: str = f"sqlite:///{(BACKEND_DIR / 'fon_takip.db').as_posix()}"

    # TEFAS / EVDS
    request_timeout: float = 30.0
    evds_api_key: str | None = None  # TCMB EVDS (TÜFE/USD) için; reel getiri aşamasında

    # Zamanlayıcı (gecelik veri güncelleme)
    enable_scheduler: bool = False  # True ise FastAPI açılışında devreye girer
    daily_update_hour: int = 20  # TEFAS NAV'ları akşam yayınlar


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
