@echo off
setlocal
cd /d "%~dp0"
chcp 65001 > nul

echo ============================
echo EXPORT CURRENT SETTINGS
echo ============================

if exist .venv\Scripts\python.exe (
  echo [INFO] Using project venv python
  .venv\Scripts\python.exe export_bot_settings.py
) else (
  echo [WARN] venv python not found, using system python
  python export_bot_settings.py
)

set EXIT_CODE=%errorlevel%
echo.
echo [INFO] Exit code: %EXIT_CODE%
echo ============================
echo EXPORT FINISHED
echo ============================
pause
endlocal & exit /b %EXIT_CODE%
