@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo =====================================
echo CHAT BOT VERSION 2 - ZERO CLICK INIT
echo =====================================
echo.

call "%~dp0_GITHUB_RUNTIME.bat"
if errorlevel 1 goto :fail

"%GIT_EXE%" rev-parse --is-inside-work-tree >nul 2>nul
if errorlevel 1 (
  echo [INFO] Initializing git repository...
  "%GIT_EXE%" init
  if errorlevel 1 goto :fail
) else (
  echo [INFO] Git repository already exists.
)

"%GIT_EXE%" branch -M %DEFAULT_BRANCH%
if errorlevel 1 goto :fail

"%GIT_EXE%" config user.name >nul 2>nul
if errorlevel 1 (
  echo [INFO] Setting default git identity for this repo...
  "%GIT_EXE%" config user.name "Roflkemper"
)
"%GIT_EXE%" config user.email >nul 2>nul
if errorlevel 1 (
  "%GIT_EXE%" config user.email "1activemarketing@gmail.com"
)

"%GIT_EXE%" remote get-url origin >nul 2>nul
if errorlevel 1 (
  echo [INFO] Adding origin remote...
  "%GIT_EXE%" remote add origin %REPO_URL%
  if errorlevel 1 goto :fail
) else (
  echo [INFO] Updating origin remote URL...
  "%GIT_EXE%" remote set-url origin %REPO_URL%
  if errorlevel 1 goto :fail
)

"%GIT_EXE%" rev-parse --verify HEAD >nul 2>nul
if errorlevel 1 (
  echo [INFO] Creating first commit...
  "%GIT_EXE%" add .
  if errorlevel 1 goto :fail
  "%GIT_EXE%" diff --cached --quiet
  if errorlevel 1 (
    "%GIT_EXE%" commit -m "Initial private repo import"
    if errorlevel 1 goto :fail
  ) else (
    echo [INFO] Nothing to commit before first push.
  )
) else (
  echo [INFO] First commit already exists.
)

if not "%GH_EXE%"=="" (
  "%GH_EXE%" auth status >nul 2>nul
  if errorlevel 1 (
    echo [INFO] Running GitHub browser login once...
    "%GH_EXE%" auth login --web --git-protocol https
    if errorlevel 1 echo [WARN] GitHub CLI login was skipped. Git may still open browser auth on push.
  ) else (
    echo [INFO] GitHub CLI already authenticated.
  )
)

echo.
echo [INFO] Running first push to private repo...
"%GIT_EXE%" push -u origin %DEFAULT_BRANCH%
if errorlevel 1 goto :fail

echo.
echo [OK] Repository is ready.
echo [OK] Next time use PUSH_UPDATE.bat only.
pause
exit /b 0

:fail
echo.
echo [ERROR] Zero click init failed.
pause
exit /b 1
