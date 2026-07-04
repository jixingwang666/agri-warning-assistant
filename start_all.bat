@echo off
title Agri Warning Assistant

echo ========================================
echo   Agri Warning Assistant - Start All
echo ========================================
echo.

REM --- Step 1: Start MySQL ---
echo [1/4] Starting MySQL service...
sc query MySQL80 | find "RUNNING" >nul
if %errorlevel% neq 0 (
    net start MySQL80 2>nul
    if %errorlevel% neq 0 (
        echo [ERROR] Cannot start MySQL. Run this script as Administrator.
        echo Right-click start_all.bat - Run as Administrator
        pause
        exit /b 1
    )
)
echo   MySQL80 is running

REM --- Step 2: Init Database ---
echo.
echo [2/4] Initializing database...
python -m data_management.run_init_mysql
if %errorlevel% neq 0 (
    echo [WARNING] DB init failed. Check MySQL password in .env
)

REM --- Step 3: Start Backend ---
echo.
echo [3/4] Starting backend on http://127.0.0.1:8000
start "Agri-Backend" cmd /c "python -m uvicorn data_management.app:app --host 127.0.0.1 --port 8000"

echo   Waiting for backend...
timeout /t 5 /nobreak >nul

REM --- Step 4: Start Frontend ---
echo.
echo [4/4] Starting frontend on http://127.0.0.1:5173
start "Agri-Frontend" cmd /c "python -m http.server 5173 -d frontend"

echo.
echo ========================================
echo   All services started!
echo.
echo   Frontend : http://127.0.0.1:5173
echo   API Docs : http://127.0.0.1:8000/docs
echo   Login    : admin / 123456
echo.
echo   Test guide: docs\test_guide.md
echo ========================================
echo.
start http://127.0.0.1:5173
pause
