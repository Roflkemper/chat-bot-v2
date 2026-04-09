@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo =====================================
echo CHAT BOT VERSION 2 - ZERO CLICK RELEASE
echo =====================================
echo.

call "%~dp0_GITHUB_RUNTIME.bat"
if errorlevel 1 goto :fail

if not exist ".git" (
  echo [INFO] Repo was not initialized yet. Running auto-init...
  call "%~dp0INIT_GITHUB_PRIVATE_REPO.bat"
  if errorlevel 1 goto :fail
)

"%GIT_EXE%" add .
if errorlevel 1 goto :fail

"%GIT_EXE%" diff --cached --quiet
if errorlevel 1 (
  echo [INFO] Creating commit before tag: %AUTO_TAG_NAME%
  "%GIT_EXE%" commit -m "%AUTO_TAG_NAME%"
  if errorlevel 1 goto :fail
)

"%GIT_EXE%" tag --list "%AUTO_TAG_NAME%" | findstr /r /c:"^%AUTO_TAG_NAME%$" >nul
if not errorlevel 1 (
  echo [WARN] Tag %AUTO_TAG_NAME% already exists locally.
) else (
  echo [INFO] Creating tag %AUTO_TAG_NAME%...
  "%GIT_EXE%" tag %AUTO_TAG_NAME%
  if errorlevel 1 goto :fail
)

echo [INFO] Pushing branch and tag...
"%GIT_EXE%" push
if errorlevel 1 goto :fail
"%GIT_EXE%" push origin %AUTO_TAG_NAME%
if errorlevel 1 goto :fail

echo.
echo [OK] Tag %AUTO_TAG_NAME% was pushed.
echo [OK] GitHub Release should be created automatically.
pause
exit /b 0

:fail
echo.
echo [ERROR] Zero click release failed.
pause
exit /b 1
