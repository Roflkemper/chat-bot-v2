@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo =====================================
echo CLEAN RUNTIME STATE FROM GIT
echo =====================================
echo.

where git >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Git not found in PATH.
  pause
  exit /b 1
)

git rm --cached --ignore-unmatch storage\market_state.json
git rm --cached --ignore-unmatch storage\position_state.json
git rm --cached --ignore-unmatch -r storage\journal
git rm --cached --ignore-unmatch logs\*.log
git add .gitignore

echo.
echo [OK] Runtime state files were removed from Git index.
echo [INFO] Now run PUSH_UPDATE.bat
pause
exit /b 0
