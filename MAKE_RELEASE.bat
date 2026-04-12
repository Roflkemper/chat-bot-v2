@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
title CHAT BOT V2 - MAKE RELEASE ONLY

cd /d "%~dp0"

set "PROJECT_NAME=chat-bot-v2"
set "VERSION_FILE=VERSION.txt"
set "RELEASES_DIR=releases"
set "EXCLUDE_FILE=.releaseignore"

if not exist "%RELEASES_DIR%" mkdir "%RELEASES_DIR%"

set "VERSION_TAG="
if exist "%VERSION_FILE%" (
    set /p VERSION_TAG=<"%VERSION_FILE%"
)

if "%VERSION_TAG%"=="" (
    for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format ''yyyy.MM.dd-HHmmss''"') do set "VERSION_TAG=build-%%I"
)

echo [OK] Version tag: %VERSION_TAG%

echo.
echo [INFO] Running Regression Shield...
python -B -m pytest tests -q
if errorlevel 1 (
    echo [ERROR] Regression Shield failed. Release build is blocked.
    pause
    exit /b 1
)

set "ZIP_NAME=%PROJECT_NAME%-%VERSION_TAG%.zip"
set "ZIP_PATH=%CD%\%RELEASES_DIR%\%ZIP_NAME%"

if exist "%ZIP_PATH%" del /f /q "%ZIP_PATH%" >nul 2>nul

if not exist "%EXCLUDE_FILE%" (
    > "%EXCLUDE_FILE%" echo .git
    >>"%EXCLUDE_FILE%" echo .venv
    >>"%EXCLUDE_FILE%" echo __pycache__
    >>"%EXCLUDE_FILE%" echo .pytest_cache
    >>"%EXCLUDE_FILE%" echo releases
    >>"%EXCLUDE_FILE%" echo *.pyc
    >>"%EXCLUDE_FILE%" echo *.pyo
    >>"%EXCLUDE_FILE%" echo *.log
    >>"%EXCLUDE_FILE%" echo .DS_Store
    >>"%EXCLUDE_FILE%" echo Thumbs.db
)

echo.
echo [INFO] Running live smoke test...
python -B tools\smoke_test.py --timeout 5
if errorlevel 1 (
    echo [ERROR] Smoke test failed. Release build is blocked.
    pause
    exit /b 1
)

echo.
echo [INFO] Rebuilding PROJECT_MANIFEST.md...
call build_manifest.bat
if errorlevel 1 (
    echo [ERROR] Manifest rebuild failed.
    pause
    exit /b 1
)

if not exist PROJECT_MANIFEST.md (
    echo [ERROR] PROJECT_MANIFEST.md not found after rebuild.
    pause
    exit /b 1
)

echo.
echo [INFO] Building release ZIP...
powershell -NoProfile -ExecutionPolicy Bypass -File "tools\build_release_zip.ps1" -ProjectRoot "%CD%" -ZipPath "%ZIP_PATH%" -ProjectName "%PROJECT_NAME%" -ExcludeFile "%EXCLUDE_FILE%"
if errorlevel 1 (
    echo [ERROR] ZIP build failed.
    pause
    exit /b 1
)

echo.
echo [INFO] Verifying ZIP...
powershell -NoProfile -ExecutionPolicy Bypass -File "tools\verify_release_zip.ps1" -ZipPath "%ZIP_PATH%"

if errorlevel 1 (
    echo [ERROR] ZIP verification failed.
    pause
    exit /b 1
)

echo.
echo [OK] DONE
echo [OK] Release ZIP: %ZIP_PATH%
pause
exit /b 0
