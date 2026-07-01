"""Fon Takip — FastAPI uygulaması.

Çalıştırma (backend/ içinde, venv aktif):
    uvicorn app.main:app --reload
İnteraktif dokümanlar: http://127.0.0.1:8000/docs
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.api import alarms, compare, favorites, funds, overview, portfolios, reminders
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
app.include_router(favorites.router)
app.include_router(overview.router)


@app.get("/api/health", tags=["meta"])
def health():
    return {"status": "ok", "app": settings.app_name}


# Üretilmiş frontend'i (varsa) servis et → tek port, tek süreç: http://localhost:8000
# API rotaları yukarıda tanımlı; aşağıdaki SPA yakalayıcı yalnız kalan yolları alır.
# ÖNEMLİ: index.html no-cache ile sunulur → yeni derleme tarayıcıda ANINDA görünür
# (hash'li /assets dosyaları uzun cache'lenir; adları değiştiği için güvenli).
_frontend_dist = (BACKEND_DIR.parent / "frontend" / "dist").resolve()
if _frontend_dist.is_dir():
    _index = _frontend_dist / "index.html"

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        candidate = (_frontend_dist / full_path).resolve()
        if (
            full_path
            and str(candidate).startswith(str(_frontend_dist))  # dizin dışına çıkma
            and candidate.is_file()
        ):
            resp = FileResponse(str(candidate))
            if full_path.startswith("assets/"):
                resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            return resp
        return FileResponse(str(_index), headers={"Cache-Control": "no-cache, must-revalidate"})
