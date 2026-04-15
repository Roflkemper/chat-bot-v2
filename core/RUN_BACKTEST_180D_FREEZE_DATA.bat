@echo off
setlocal
cd /d "%~dp0"
chcp 65001 > nul

echo ============================
echo BACKTEST 180D START [FREEZE DATA]
echo ============================

if exist .venv\Scripts\python.exe (
  echo [INFO] Using project venv python
  set "PY=.venv\Scripts\python.exe"
) else (
  echo [WARN] venv python not found, using system python
  set "PY=python"
)

echo.
echo [INFO] Freezing 180d data...
"%PY%" freeze_backtest_data_180d.py
if errorlevel 1 goto :fail

echo.
echo [INFO] Running 180d frozen backtest...
"%PY%" run_backtest.py --lookback-days 180 --mode frozen --data-file backtests/frozen/BTCUSDT_1h_180d_frozen.json --output-dir backtests
set EXIT_CODE=%errorlevel%

echo.
echo [INFO] Exit code: %EXIT_CODE%
echo ============================
echo BACKTEST 180D FINISHED
echo ============================
pause
endlocal & exit /b %EXIT_CODE%

:fail
set EXIT_CODE=%errorlevel%
echo.
echo [ERROR] 180d freeze failed. Exit code: %EXIT_CODE%
pause
endlocal & exit /b %EXIT_CODE%
