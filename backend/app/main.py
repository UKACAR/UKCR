"""Fon Takip — FastAPI uygulaması.

Çalıştırma (backend/ içinde, venv aktif):
    uvicorn app.main:app --reload
İnteraktif dokümanlar: http://127.0.0.1:8000/docs
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import alarms, compare, funds, portfolios, reminders
from app.core.config import BACKEND_DIR, settings
from app.db.init_db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()  # tabloları ve stopaj takvimini hazırla
    scheduler = None
    if settings.enable_scheduler:
        from app.scheduler import start_scheduler

        scheduler = start_scheduler()
    try:
        yield
    finally:
        if scheduler is not None:
            scheduler.shutdown(wait=False)


app = FastAPI(title=settings.app_name, lifespan=lifespan)

# Vite dev sunucusu için CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(funds.router)
app.include_router(portfolios.router)
app.include_router(compare.router)
app.include_router(reminders.router)
app.include_router(alarms.router)


@app.get("/api/health", tags=["meta"])
def health():
    return {"status": "ok", "app": settings.app_name}


# Üretilmiş frontend'i (varsa) servis et → tek port, tek süreç: http://localhost:8000
# `npm run build` ile frontend/dist üretilirse otomatik devreye girer.
# (API rotaları yukarıda tanımlı olduğu için onlar önce eşleşir; "/" kalanı yakalar.)
_frontend_dist = BACKEND_DIR.parent / "frontend" / "dist"
if _frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="frontend")
