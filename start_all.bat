@echo off
setlocal
title Agri Warning Assistant

set "PROJECT_DIR=%~dp0"
set "PYTHON_EXE=D:\Develop\Tools\agri-warning-venv\Scripts\python.exe"
set "MYSQL_SERVICE=MySQL94"

cd /d "%PROJECT_DIR%"

echo ========================================
echo   Agri Warning Assistant - Start All
echo ========================================
echo.

if not exist "%PYTHON_EXE%" (
    echo [ERROR] Python venv not found:
    echo         %PYTHON_EXE%
    pause
    exit /b 1
)

echo [1/4] Checking MySQL service %MYSQL_SERVICE%...
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
        echo [ERROR] Cannot start %MYSQL_SERVICE%.
        echo         Please run as Administrator or start manually:
        echo         net start %MYSQL_SERVICE%
        pause
        exit /b 1
    )
)
echo   %MYSQL_SERVICE% is running

echo.
echo [2/4] Initializing database...
"%PYTHON_EXE%" -m data_management.run_init_mysql
if errorlevel 1 (
    echo [WARNING] DB init failed. Check Project\data_management\secrets.env
)

echo.
echo [3/4] Starting backend on http://127.0.0.1:8000
start "Agri Warning Backend" cmd /k ""%PYTHON_EXE%" -m uvicorn data_management.app:app --host 127.0.0.1 --port 8000"

echo   Waiting for backend...
timeout /t 5 /nobreak >nul

echo.
echo [4/4] Starting frontend on http://127.0.0.1:5173
start "Agri Warning Frontend" cmd /k ""%PYTHON_EXE%" -m http.server 5173 -d frontend"

echo.
echo ========================================
echo   All services started!
echo.
echo   Frontend : http://127.0.0.1:5173
echo   API Docs : http://127.0.0.1:8000/docs
echo   Login    : admin / 123456
echo.
echo   Config   : data_management\secrets.env
echo ========================================
echo.
start http://127.0.0.1:5173
pause
