@echo off
setlocal
cd /d "%~dp0"
chcp 65001 > nul

echo ============================
echo BACKTEST 90D START [TRADE-PLAN REALISM]
echo ============================

if exist .venv\Scripts\python.exe (
  echo [INFO] Using project venv python
  .venv\Scripts\python.exe run_backtest.py
) else (
  echo [WARN] venv python not found, using system python
  python run_backtest.py
)

set EXIT_CODE=%errorlevel%
echo.
echo [INFO] Exit code: %EXIT_CODE%
echo ============================
echo BACKTEST 90D FINISHED
echo ============================
pause
endlocal & exit /b %EXIT_CODE%
