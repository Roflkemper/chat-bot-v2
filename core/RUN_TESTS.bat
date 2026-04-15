@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

echo [INFO] Running regression shield tests...
python -B -m pytest tests -q
if errorlevel 1 (
    echo.
    echo [ERROR] Regression Shield failed. Release is blocked.
    pause
    exit /b 1
)

echo.
echo [OK] Regression Shield passed.
pause
exit /b 0
