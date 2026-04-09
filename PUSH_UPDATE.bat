@echo off
setlocal EnableExtensions
cd /d "%~dp0"

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

"%GIT_EXE%" remote get-url origin >nul 2>nul
if errorlevel 1 (
  echo [INFO] Origin was missing. Restoring...
  "%GIT_EXE%" remote add origin %REPO_URL%
  if errorlevel 1 goto :fail
)

"%GIT_EXE%" branch -M %DEFAULT_BRANCH%
if errorlevel 1 goto :fail

echo [INFO] Adding changed files...
"%GIT_EXE%" add .
if errorlevel 1 goto :fail

"%GIT_EXE%" diff --cached --quiet
if errorlevel 1 (
  echo [INFO] Creating commit: %AUTO_COMMIT_MSG%
  "%GIT_EXE%" commit -m "%AUTO_COMMIT_MSG%"
  if errorlevel 1 goto :fail
  echo [INFO] Pushing changes to GitHub...
  "%GIT_EXE%" push
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

:fail
echo.
echo [ERROR] Zero click push failed.
pause
exit /b 1
