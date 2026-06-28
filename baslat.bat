@echo off
title UKCR Baslatici
set PYTHONUTF8=1
echo UKCR baslatiliyor, lutfen bekleyin...
cd /d "%~dp0backend"
start "UKCR Sunucu" ".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
timeout /t 5 /nobreak >nul
start "" "http://localhost:8000"
echo.
echo UKCR calisiyor: http://localhost:8000
echo Kapatmak icin acilan "UKCR Sunucu" penceresini kapatin (veya durdur.bat).
timeout /t 4 /nobreak >nul
