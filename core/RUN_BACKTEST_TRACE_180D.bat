@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
) else (
  set "PY=python"
)
echo ============================
echo BACKTEST TRACE 180D START
echo ============================
"%PY%" run_backtest.py --lookback-days 180 --mode frozen --data-file backtests/frozen/BTCUSDT_1h_180d_frozen.json --output-dir backtests
set "RC=%ERRORLEVEL%"
echo [INFO] Exit code: %RC%
echo ============================
echo BACKTEST TRACE 180D FINISHED
echo ============================
pause
exit /b %RC%
