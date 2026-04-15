@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
) else (
  set "PY=python"
)
echo ============================
echo BACKTEST TRACE 90D START
echo ============================
"%PY%" run_backtest.py
set "RC=%ERRORLEVEL%"
echo [INFO] Exit code: %RC%
echo ============================
echo BACKTEST TRACE 90D FINISHED
echo ============================
pause
exit /b %RC%
