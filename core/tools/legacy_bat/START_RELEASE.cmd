@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\release_runner.ps1"
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
    echo.
    echo [ERROR] Release failed. Check logs\release_automation.log
    pause
    exit /b %EXIT_CODE%
)
echo.
echo [OK] Release completed successfully.
if exist "%~dp0releases" start "" "%~dp0releases"
pause
exit /b 0
