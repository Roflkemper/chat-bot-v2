@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
) else (
  set "PY=python"
)
set "OUTPUT_DIR=%CD%\backtests"
set "REPORT_PATH=%OUTPUT_DIR%\backtest_multi_180d_report.json"
set "TRACE_PATH=%OUTPUT_DIR%\backtest_multi_180d_trace.json"
echo ============================
echo BACKTEST MULTI TRACE START
echo ============================
echo [INFO] Project root: %CD%
echo [INFO] Python: %PY%
echo [INFO] Output dir: %OUTPUT_DIR%
echo [INFO] Report path: %REPORT_PATH%
echo [INFO] Trace path: %TRACE_PATH%
"%PY%" run_backtest.py --mode multi --lookback-days 180 --output-dir backtests
set "RC=%ERRORLEVEL%"
if exist "%REPORT_PATH%" (
  echo [OK] Report found: %REPORT_PATH%
) else (
  echo [WARN] Report missing: %REPORT_PATH%
)
if exist "%TRACE_PATH%" (
  echo [OK] Trace found: %TRACE_PATH%
) else (
  echo [WARN] Trace missing: %TRACE_PATH%
)
if exist "backtests\*.json" dir /b "backtests\*.json"
echo [INFO] Exit code: %RC%
echo ============================
echo BACKTEST MULTI TRACE FINISHED
echo ============================
pause
exit /b %RC%
