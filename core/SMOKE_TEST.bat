@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

echo [INFO] Running live smoke test...
python -B tools\smoke_test.py --timeout 5
if errorlevel 1 (
    echo [ERROR] Smoke test failed.
    pause
    exit /b 1
)

echo [OK] Smoke test passed.
pause
exit /b 0
