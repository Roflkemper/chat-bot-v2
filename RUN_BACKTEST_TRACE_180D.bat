@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
) else (
  set "PY=python"
)

set "OUTPUT_DIR=backtests"
set "REPORT=%OUTPUT_DIR%\backtest_180d_report.json"
set "TRACE=%OUTPUT_DIR%\backtest_180d_trace.json"

if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%"

echo ============================
echo BACKTEST TRACE 180D START
echo ============================
echo [INFO] Project root: %CD%
echo [INFO] Python: %PY%
echo [INFO] Output dir: %CD%\%OUTPUT_DIR%
echo [INFO] Report path: %CD%\%REPORT%
echo [INFO] Trace path: %CD%\%TRACE%

if not exist "run_backtest.py" (
  echo [ERROR] run_backtest.py not found in %CD%
  pause
  exit /b 1
)

"%PY%" run_backtest.py --lookback-days 180 --mode frozen --data-file backtests/frozen/BTCUSDT_1h_180d_frozen.json --output-dir "%OUTPUT_DIR%"
set "RC=%ERRORLEVEL%"

echo.
if exist "%REPORT%" (
  echo [OK] Report found: %CD%\%REPORT%
) else (
  echo [WARN] Report not found: %CD%\%REPORT%
)
if exist "%TRACE%" (
  echo [OK] Trace found: %CD%\%TRACE%
) else (
  echo [WARN] Trace not found: %CD%\%TRACE%
)

echo.
dir /b "%OUTPUT_DIR%\*.json" 2>nul

echo.
echo [INFO] Exit code: %RC%
echo ============================
echo BACKTEST TRACE 180D FINISHED
echo ============================
pause
exit /b %RC%
