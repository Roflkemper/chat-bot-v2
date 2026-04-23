@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

for /f "delims=" %%H in ('git config --get core.hooksPath 2^>nul') do set "HOOKS_PATH=%%H"
if "%HOOKS_PATH%"=="" (
    echo [ERROR] core.hooksPath is not configured.
    pause
    exit /b 1
)

echo [OK] core.hooksPath=%HOOKS_PATH%
if /I not "%HOOKS_PATH%"==".githooks" (
    echo [ERROR] Expected .githooks but got %HOOKS_PATH%
    pause
    exit /b 1
)

echo [OK] Git hooks are configured correctly.
pause
exit /b 0
