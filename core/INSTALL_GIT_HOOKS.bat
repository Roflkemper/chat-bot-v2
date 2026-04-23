@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"

echo [INFO] Installing Git hooks...
powershell -NoProfile -ExecutionPolicy Bypass -File "tools\install_git_hooks.ps1" -ProjectRoot "%CD%"
if errorlevel 1 (
    echo.
    echo [ERROR] Git hooks installation failed.
    pause
    exit /b 1
)

for /f "delims=" %%H in ('git config --get core.hooksPath 2^>nul') do set "HOOKS_PATH=%%H"
if /I not "%HOOKS_PATH%"==".githooks" (
    echo.
    echo [ERROR] Git hooks installed, but core.hooksPath is unexpected: %HOOKS_PATH%
    pause
    exit /b 1
)

echo.
echo [OK] Git hooks installed and verified.
echo [OK] Commit and push are now blocked automatically if Regression Shield fails.
pause
exit /b 0
