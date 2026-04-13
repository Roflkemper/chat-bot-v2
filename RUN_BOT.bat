@echo off
setlocal
title CHAT BOT VERSION 2 - TELEGRAM LIVE
cd /d "%~dp0"
if not exist .venv (
    py -m venv .venv
    if errorlevel 1 goto :fail
)
call .venv\Scripts\activate.bat
if errorlevel 1 goto :fail
python -m pip install -r requirements.txt
if errorlevel 1 goto :fail
python telegram_bot_runner.py
set EXIT_CODE=%ERRORLEVEL%
if not "%EXIT_CODE%"=="0" echo.
echo Bot exited with code %EXIT_CODE%.
pause
exit /b %EXIT_CODE%

:fail
echo.
echo Startup failed. Check Python / venv / pip output above.
pause
exit /b 1
