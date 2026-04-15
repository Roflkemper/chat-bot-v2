@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
title CHAT BOT V2 - PUSH + RELEASE

cd /d "%~dp0"

set "PROJECT_NAME=chat-bot-v2"
set "VERSION_FILE=VERSION.txt"
set "RELEASES_DIR=releases"
set "EXCLUDE_FILE=.releaseignore"

set "GIT_EXE=C:\Program Files\Git\cmd\git.exe"
if not exist "%GIT_EXE%" set "GIT_EXE=C:\Program Files (x86)\Git\cmd\git.exe"

if not exist "%GIT_EXE%" (
    echo [ERROR] Git not found.
    echo Checked:
    echo   C:\Program Files\Git\cmd\git.exe
    echo   C:\Program Files ^(x86^)\Git\cmd\git.exe
    pause
    exit /b 1
)

echo [OK] Git detected: "%GIT_EXE%"

"%GIT_EXE%" rev-parse --is-inside-work-tree >nul 2>nul
if errorlevel 1 (
    echo [ERROR] This folder is not a Git repository.
    pause
    exit /b 1
)

for /f "delims=" %%B in ('"%GIT_EXE%" rev-parse --abbrev-ref HEAD 2^>nul') do set "CURRENT_BRANCH=%%B"
if "%CURRENT_BRANCH%"=="" (
    echo [ERROR] Could not detect current branch.
    pause
    exit /b 1
)
if /I "%CURRENT_BRANCH%"=="HEAD" (
    echo [ERROR] Detached HEAD state detected.
    pause
    exit /b 1
)

echo [OK] Current branch: %CURRENT_BRANCH%

if exist ".git\rebase-merge" (
    echo [WARN] Unfinished rebase detected. Auto-abort...
    "%GIT_EXE%" rebase --abort
    if errorlevel 1 (
        echo [ERROR] Could not abort rebase.
        pause
        exit /b 1
    )
)
if exist ".git\rebase-apply" (
    echo [WARN] Unfinished rebase apply detected. Auto-abort...
    "%GIT_EXE%" rebase --abort
    if errorlevel 1 (
        echo [ERROR] Could not abort rebase apply.
        pause
        exit /b 1
    )
)
if exist ".git\MERGE_HEAD" (
    echo [WARN] Unfinished merge detected. Auto-abort...
    "%GIT_EXE%" merge --abort
    if errorlevel 1 (
        echo [ERROR] Could not abort merge.
        pause
        exit /b 1
    )
)

if not exist "%RELEASES_DIR%" mkdir "%RELEASES_DIR%"

set "VERSION_TAG="
if exist "%VERSION_FILE%" (
    set /p VERSION_TAG=<"%VERSION_FILE%"
)
if "%VERSION_TAG%"=="" (
    for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format ''yyyy.MM.dd-HHmmss''"') do set "VERSION_TAG=build-%%I"
)

echo [OK] Version tag: %VERSION_TAG%
echo [INFO] Repo mode: single-owner / local branch is source of truth
echo [INFO] Push mode: force-with-lease ^(no pull --rebase^)

set "COMMIT_MSG=%~1"
if "%COMMIT_MSG%"=="" set "COMMIT_MSG=%VERSION_TAG%"

echo.
echo [INFO] Commit message:
echo   %COMMIT_MSG%
echo.
echo [INFO] Running Regression Shield...
python -B -m pytest tests -q
if errorlevel 1 (
    echo [ERROR] Regression Shield failed. Push/release is blocked.
    pause
    exit /b 1
)

echo.
echo [INFO] Running live smoke test...
python -B tools\smoke_test.py --timeout 5
if errorlevel 1 (
    echo [ERROR] Smoke test failed. Push/release is blocked.
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
echo [INFO] Adding changed files...
"%GIT_EXE%" add -A
if errorlevel 1 (
    echo [ERROR] git add failed.
    pause
    exit /b 1
)

echo.
echo [INFO] Creating commit if needed...
"%GIT_EXE%" diff --cached --quiet
if errorlevel 1 (
    "%GIT_EXE%" commit -m "%COMMIT_MSG%"
    if errorlevel 1 (
        echo [ERROR] git commit failed.
        pause
        exit /b 1
    )
) else (
    echo [INFO] No staged changes to commit.
)

echo.
echo [INFO] Fetching origin for lease safety...
"%GIT_EXE%" fetch origin
if errorlevel 1 (
    echo [ERROR] git fetch failed.
    pause
    exit /b 1
)

for /f "delims=" %%A in ('"%GIT_EXE%" rev-parse HEAD 2^>nul') do set "LOCAL_HEAD=%%A"
for /f "delims=" %%A in ('"%GIT_EXE%" rev-parse origin/%CURRENT_BRANCH% 2^>nul') do set "REMOTE_HEAD=%%A"

echo [INFO] Local HEAD : %LOCAL_HEAD%
if not "%REMOTE_HEAD%"=="" (
    echo [INFO] Remote HEAD: %REMOTE_HEAD%
) else (
    echo [WARN] Remote branch origin/%CURRENT_BRANCH% not found yet. First push is OK.
)

echo.
echo [INFO] Pushing local branch to GitHub with force-with-lease...
"%GIT_EXE%" push --force-with-lease origin %CURRENT_BRANCH%
if errorlevel 1 (
    echo [ERROR] git push --force-with-lease failed.
    echo [ERROR] Remote changed after fetch. Run the script again.
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
echo [OK] GitHub synced: origin/%CURRENT_BRANCH%
echo [OK] Release ZIP: %ZIP_PATH%
pause
exit /b 0
