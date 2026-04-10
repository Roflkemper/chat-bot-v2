@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "CURRENT_BRANCH="

echo =====================================
echo CHAT BOT VERSION 2 - ZERO CLICK PUSH
echo =====================================
echo.

call "%~dp0_GITHUB_RUNTIME.bat"
if errorlevel 1 goto :fail

if not exist ".git" (
  echo [INFO] Repo was not initialized yet. Running auto-init...
  call "%~dp0INIT_GITHUB_PRIVATE_REPO.bat"
  if errorlevel 1 goto :fail
)

call :prepare_git_state
if errorlevel 1 goto :fail

"%GIT_EXE%" remote get-url origin >nul 2>nul
if errorlevel 1 (
  echo [INFO] Origin was missing. Restoring...
  "%GIT_EXE%" remote add origin %REPO_URL%
  if errorlevel 1 goto :fail
)

echo [INFO] Adding changed files...
"%GIT_EXE%" add .
if errorlevel 1 goto :fail

"%GIT_EXE%" diff --cached --quiet
if errorlevel 1 (
  echo [INFO] Creating commit: %AUTO_COMMIT_MSG%
  "%GIT_EXE%" commit -m "%AUTO_COMMIT_MSG%"
  if errorlevel 1 goto :fail
  echo [INFO] Pushing changes to GitHub...
  "%GIT_EXE%" push -u origin %DEFAULT_BRANCH%
  if errorlevel 1 goto :fail
  echo.
  echo [OK] Changes were pushed to GitHub.
  echo [OK] GitHub Actions should build ZIP automatically.
  pause
  exit /b 0
) else (
  echo [INFO] No new changes were found. Nothing to push.
  pause
  exit /b 0
)

:prepare_git_state
if exist ".git\rebase-merge" (
  echo [WARN] Found unfinished rebase. Trying to abort it...
  "%GIT_EXE%" rebase --abort >nul 2>nul
)
if exist ".git\rebase-apply" (
  echo [WARN] Found unfinished apply/rebase. Trying to abort it...
  "%GIT_EXE%" rebase --abort >nul 2>nul
)
if exist ".git\MERGE_HEAD" (
  echo [WARN] Found unfinished merge. Trying to abort it...
  "%GIT_EXE%" merge --abort >nul 2>nul
)

for /f "delims=" %%i in ('"%GIT_EXE%" symbolic-ref --quiet --short HEAD 2^>nul') do set "CURRENT_BRANCH=%%i"
if defined CURRENT_BRANCH goto :ensure_default_branch

echo [WARN] Detached HEAD detected. Restoring working branch %DEFAULT_BRANCH%...
"%GIT_EXE%" rev-parse --verify HEAD >nul 2>nul
if errorlevel 1 (
  "%GIT_EXE%" checkout --orphan %DEFAULT_BRANCH%
) else (
  "%GIT_EXE%" checkout -B %DEFAULT_BRANCH%
)
if errorlevel 1 exit /b 1
set "CURRENT_BRANCH=%DEFAULT_BRANCH%"

:ensure_default_branch
if /I not "%CURRENT_BRANCH%"=="%DEFAULT_BRANCH%" (
  echo [INFO] Switching branch %CURRENT_BRANCH% ^> %DEFAULT_BRANCH%...
  "%GIT_EXE%" branch -M %DEFAULT_BRANCH%
  if errorlevel 1 exit /b 1
)
exit /b 0

:fail
echo.
echo [ERROR] Zero click push failed.
pause
exit /b 1
