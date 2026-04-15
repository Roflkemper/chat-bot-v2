@echo off
setlocal
cd /d "%~dp0"
chcp 65001 > nul

echo ============================
echo FREEZE BACKTEST 90D DATA
echo ============================

if exist .venv\Scripts\python.exe (
  echo [INFO] Using project venv python
  .venv\Scripts\python.exe freeze_backtest_data.py
) else (
  echo [WARN] venv python not found, using system python
  python freeze_backtest_data.py
)

set EXIT_CODE=%errorlevel%
echo.
echo [INFO] Exit code: %EXIT_CODE%
echo ============================
echo FREEZE FINISHED
echo ============================
pause
endlocal & exit /b %EXIT_CODE%
