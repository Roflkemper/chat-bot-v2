@echo off
setlocal
title GRID ORCHESTRATOR - UNIFIED APP (TZ-010)
cd /d "%~dp0"
if not exist .venv (
    py -m venv .venv
    if errorlevel 1 goto :fail
)
call .venv\Scripts\activate.bat
if errorlevel 1 goto :fail
python -m pip install -r requirements.txt
if errorlevel 1 goto :fail
python app_runner.py
set EXIT_CODE=%ERRORLEVEL%
if not "%EXIT_CODE%"=="0" echo.
echo App exited with code %EXIT_CODE%.
pause
exit /b %EXIT_CODE%

:fail
echo.
echo Startup failed. Check Python / venv / pip output above.
pause
exit /b 1
