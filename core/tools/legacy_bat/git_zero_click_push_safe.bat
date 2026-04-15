@echo off
setlocal ENABLEDELAYEDEXPANSION
chcp 65001 >nul

title Git Zero Click Push Safe

echo [INFO] Git Zero Click Push Safe
echo.

REM --- checks ---
where git >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Git not found in PATH.
    echo Install Git and reopen terminal.
    pause
    exit /b 1
)

git rev-parse --is-inside-work-tree >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Current folder is not a git repository.
    pause
    exit /b 1
)

for /f %%i in ('git branch --show-current') do set CURRENT_BRANCH=%%i
if not defined CURRENT_BRANCH set CURRENT_BRANCH=main

echo [INFO] Branch: %CURRENT_BRANCH%
echo [INFO] Fetching remote changes...
git fetch origin %CURRENT_BRANCH%
if errorlevel 1 (
    echo [ERROR] Fetch failed.
    pause
    exit /b 1
)

echo [INFO] Checking local changes...
git diff --quiet
set HAS_WORKTREE_CHANGES=%errorlevel%
git diff --cached --quiet
set HAS_STAGED_CHANGES=%errorlevel%

if "%HAS_WORKTREE_CHANGES%"=="1" (
    echo [INFO] Uncommitted changes detected.
) else (
    if "%HAS_STAGED_CHANGES%"=="1" (
        echo [INFO] Staged changes detected.
    )
)

REM --- auto commit if there is anything to commit ---
if "%HAS_WORKTREE_CHANGES%"=="1" goto do_commit
if "%HAS_STAGED_CHANGES%"=="1" goto do_commit
goto skip_commit

:do_commit
echo [INFO] Adding changes...
git add -A
if errorlevel 1 (
    echo [ERROR] git add failed.
    pause
    exit /b 1
)

for /f %%t in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HH-mm-ss"') do set NOW=%%t
set COMMIT_MSG=auto update %NOW%

echo [INFO] Creating commit: !COMMIT_MSG!
git commit -m "!COMMIT_MSG!" >nul 2>nul
if errorlevel 1 (
    echo [INFO] Nothing new to commit, continuing...
) else (
    echo [OK] Commit created.
)

:skip_commit
echo [INFO] Rebasing on origin/%CURRENT_BRANCH%...
git pull --rebase origin %CURRENT_BRANCH%
if errorlevel 1 goto rebase_failed

echo [INFO] Pushing changes to GitHub...
git push origin %CURRENT_BRANCH%
if errorlevel 1 goto push_failed

echo.
echo [OK] Push completed successfully.
pause
exit /b 0

:rebase_failed
echo.
echo [ERROR] Rebase failed. Most likely a merge conflict.
echo.
echo What to do now:
echo   1. Run: git status
echo   2. Open conflicted files and keep the correct code
echo   3. Run: git add .
echo   4. Run: git rebase --continue
echo   5. Run this BAT again
echo.
echo If you want to cancel the rebase:
echo   git rebase --abort
echo.
pause
exit /b 1

:push_failed
echo.
echo [ERROR] Push failed even after rebase.
echo.
echo Check:
echo   - remote permissions
echo   - branch protection rules
echo   - GitHub authentication
echo.
echo Helpful commands:
echo   git status
echo   git remote -v
echo   git log --oneline --graph --decorate -20
echo.
pause
exit /b 1