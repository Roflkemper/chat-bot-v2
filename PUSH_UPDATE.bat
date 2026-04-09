@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo =====================================
echo CHAT BOT VERSION 2 - ONE CLICK PUSH
echo =====================================
echo.

where git >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Git was not found in PATH.
  pause
  exit /b 1
)

if not exist ".git" (
  echo [ERROR] This folder is not a git repository yet.
  echo Run INIT_GITHUB_PRIVATE_REPO.bat first.
  pause
  exit /b 1
)

set "COMMIT_MSG=Project update"
if exist VERSION.txt (
  set /p FIRST_LINE=<VERSION.txt
  if not "%FIRST_LINE%"=="" set "COMMIT_MSG=%FIRST_LINE%"
)

echo [INFO] Adding changed files...
git add .
if errorlevel 1 goto :fail

git diff --cached --quiet
if errorlevel 1 (
  echo [INFO] Creating commit: %COMMIT_MSG%
  git commit -m "%COMMIT_MSG%"
  if errorlevel 1 goto :fail

  echo [INFO] Pushing changes to GitHub...
  git push
  if errorlevel 1 goto :fail

  echo.
  echo [OK] Changes were pushed to GitHub.
  echo [OK] If GitHub Actions is enabled, ZIP build starts automatically.
  pause
  exit /b 0
) else (
  echo [INFO] No new changes were found. Nothing to push.
  pause
  exit /b 0
)

:fail
echo.
echo [ERROR] Push failed.
pause
exit /b 1
