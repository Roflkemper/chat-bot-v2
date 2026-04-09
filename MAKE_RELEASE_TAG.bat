@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo =====================================
echo CHAT BOT VERSION 2 - RELEASE TAG
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

set "TAG_NAME=v17.7.2"
if exist VERSION.txt (
  set /p RAW_TAG=<VERSION.txt
  if not "%RAW_TAG%"=="" set "TAG_NAME=%RAW_TAG%"
)

set "TAG_NAME=%TAG_NAME: =%"
for /f "tokens=1 delims=-" %%i in ("%TAG_NAME%") do set "TAG_NAME=%%~i"
if "%TAG_NAME%"=="" set "TAG_NAME=v17.7.2"

set /p TAG_INPUT=Release tag [%TAG_NAME%]: 
if not "%TAG_INPUT%"=="" set "TAG_NAME=%TAG_INPUT%"

echo [INFO] Adding files before tag...
git add .
if errorlevel 1 goto :fail

git diff --cached --quiet
if errorlevel 1 (
  echo [INFO] Creating commit before tag: %TAG_NAME%
  git commit -m "%TAG_NAME%"
  if errorlevel 1 goto :fail
)

git tag --list "%TAG_NAME%" | findstr /r /c:"^%TAG_NAME%$" >nul
if not errorlevel 1 (
  echo [WARN] Tag %TAG_NAME% already exists locally.
) else (
  echo [INFO] Creating tag %TAG_NAME%...
  git tag %TAG_NAME%
  if errorlevel 1 goto :fail
)

echo [INFO] Pushing branch and tag to GitHub...
git push
if errorlevel 1 goto :fail
git push origin %TAG_NAME%
if errorlevel 1 goto :fail

echo.
echo [OK] Tag %TAG_NAME% was pushed.
echo [OK] If release workflow is enabled, GitHub creates ZIP release automatically.
pause
exit /b 0

:fail
echo.
echo [ERROR] Release tag step failed.
pause
exit /b 1
