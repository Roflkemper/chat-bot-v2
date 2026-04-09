@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo =====================================
echo CHAT BOT VERSION 2 - GITHUB INIT
echo =====================================
echo.

where git >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Git was not found in PATH.
  echo Install Git for Windows and run this file again.
  pause
  exit /b 1
)

set "REPO_URL=https://github.com/Roflkemper/chat-bot-v2.git"
set "DEFAULT_BRANCH=main"

if not exist ".git" (
  echo [INFO] Initializing git repository...
  git init
  if errorlevel 1 goto :fail
) else (
  echo [INFO] Git repository already exists.
)

git branch -M %DEFAULT_BRANCH%
if errorlevel 1 goto :fail

git remote get-url origin >nul 2>nul
if errorlevel 1 (
  echo [INFO] Adding origin remote...
  git remote add origin %REPO_URL%
  if errorlevel 1 goto :fail
) else (
  echo [INFO] Updating origin remote URL...
  git remote set-url origin %REPO_URL%
  if errorlevel 1 goto :fail
)

git rev-parse --verify HEAD >nul 2>nul
if errorlevel 1 (
  echo [INFO] Creating first commit...
  git add .
  git commit -m "Initial private repo import"
  if errorlevel 1 goto :fail
) else (
  echo [INFO] First commit already exists.
)

echo.
echo [INFO] Running first push to private repo...
echo [INFO] GitHub may ask you to sign in in your browser.
git push -u origin %DEFAULT_BRANCH%
if errorlevel 1 goto :fail

echo.
echo [OK] Repository was linked and pushed to GitHub.
echo [OK] Use PUSH_UPDATE.bat for future updates.
pause
exit /b 0

:fail
echo.
echo [ERROR] GitHub init failed.
pause
exit /b 1
