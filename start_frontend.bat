@echo off
title Agri Warning - Frontend

echo ========================================
echo   Agri Warning Assistant - Frontend
echo ========================================
echo.
echo   Address: http://127.0.0.1:5173
echo   Make sure backend is running on port 8000
echo.
python -m http.server 5173 -d frontend

pause
