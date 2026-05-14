@echo off
chcp 65001 > nul

echo ============================
echo BACKTEST 90D START
echo ============================

REM Активируем venv если есть
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
) else (
    echo [WARN] venv not found, running system python
)

REM Проверка python
where python > nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found in PATH
    pause
    exit /b
)

echo.
echo [INFO] Running backtest...
echo.

python run_backtest.py

echo.
echo ============================
echo BACKTEST FINISHED
echo ============================

pause