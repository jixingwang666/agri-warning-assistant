@echo off
setlocal
title Agri Warning - Backend

set "PROJECT_DIR=%~dp0"
set "PYTHON_EXE=D:\Develop\Tools\agri-warning-venv\Scripts\python.exe"
set "MYSQL_SERVICE=MySQL94"

cd /d "%PROJECT_DIR%"

echo ========================================
echo   Agri Warning Assistant - Backend
echo ========================================
echo.

if not exist "%PYTHON_EXE%" (
    echo [ERROR] Python venv not found:
    echo         %PYTHON_EXE%
    pause
    exit /b 1
)

echo [1/3] Checking MySQL service %MYSQL_SERVICE%...
sc query %MYSQL_SERVICE% | findstr /I "RUNNING" >nul
if errorlevel 1 (
    net session >nul 2>&1
    if errorlevel 1 (
        echo   %MYSQL_SERVICE% is not running and Administrator permission is required.
        echo   Requesting Administrator permission...
        powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
        exit /b
    )
    echo   %MYSQL_SERVICE% is not running. Trying to start it...
    net start %MYSQL_SERVICE% 2>nul
    if errorlevel 1 (
        echo   [WARN] Cannot start %MYSQL_SERVICE%.
        echo          Run this script as Administrator or start manually:
        echo          net start %MYSQL_SERVICE%
    ) else (
        echo   %MYSQL_SERVICE% started
    )
) else (
    echo   %MYSQL_SERVICE% is running
)

echo.
echo [2/3] Checking database schema without clearing existing data...
"%PYTHON_EXE%" -m data_management.run_init_mysql
if errorlevel 1 (
    echo   [WARN] DB init failed. Check data_management\secrets.env
)

echo.
echo [3/3] Starting FastAPI backend...
echo   Address: http://127.0.0.1:8000
echo   Docs:    http://127.0.0.1:8000/docs
echo.
"%PYTHON_EXE%" -m uvicorn data_management.app:app --host 127.0.0.1 --port 8000 --reload

pause
