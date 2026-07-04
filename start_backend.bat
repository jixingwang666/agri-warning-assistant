@echo off
title Agri Warning - Backend

echo ========================================
echo   Agri Warning Assistant - Backend
echo ========================================
echo.

echo [1/3] Checking MySQL service...
sc query MySQL80 | find "RUNNING" >nul
if %errorlevel% neq 0 (
    echo   Starting MySQL80...
    net start MySQL80 2>nul
    if %errorlevel% neq 0 (
        echo   [WARN] Cannot start MySQL. Run as Administrator or start manually:
        echo          net start MySQL80
    ) else (
        echo   MySQL80 started
    )
) else (
    echo   MySQL80 is running
)

echo.
echo [2/3] Initializing database...
python -m data_management.run_init_mysql
if %errorlevel% neq 0 (
    echo   [WARN] DB init failed
)

echo.
echo [3/3] Starting FastAPI backend...
echo   Address: http://127.0.0.1:8000
echo   Docs:    http://127.0.0.1:8000/docs
echo.
python -m uvicorn data_management.app:app --host 127.0.0.1 --port 8000 --reload

pause
