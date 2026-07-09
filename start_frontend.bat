@echo off
setlocal
title Agri Warning - Frontend

set "PROJECT_DIR=%~dp0"
set "PYTHON_EXE=D:\Develop\Tools\agri-warning-venv\Scripts\python.exe"

cd /d "%PROJECT_DIR%"

echo ========================================
echo   Agri Warning Assistant - Frontend
echo ========================================
echo.

if not exist "%PYTHON_EXE%" (
    echo [ERROR] Python venv not found:
    echo         %PYTHON_EXE%
    pause
    exit /b 1
)

echo   Address: http://127.0.0.1:5173
echo   Make sure backend is running on port 8000
echo.
"%PYTHON_EXE%" -m http.server 5173 -d frontend

pause
