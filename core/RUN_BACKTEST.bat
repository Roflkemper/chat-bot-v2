@echo off
chcp 65001 > nul

echo ============================
echo BACKTEST DEBUG START
echo ============================

REM НЕ закрывать окно при ошибке
setlocal enabledelayedexpansion

REM Активируем venv
if exist ".venv\Scripts\activate.bat" (
    echo [INFO] Activating venv...
    call .venv\Scripts\activate.bat
) else (
    echo [WARN] venv not found
)

echo.
echo [INFO] Python version:
python --version

echo.
echo [INFO] Running backtest...
echo.

python run_backtest.py

echo.
echo [INFO] Exit code: %errorlevel%

echo.
echo ============================
echo BACKTEST FINISHED
echo ============================

pause