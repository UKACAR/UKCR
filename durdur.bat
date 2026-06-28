@echo off
title UKCR Durdur
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do taskkill /F /PID %%a >nul 2>&1
echo UKCR durduruldu.
timeout /t 2 /nobreak >nul
