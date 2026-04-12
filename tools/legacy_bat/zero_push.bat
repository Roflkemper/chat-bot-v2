@echo off
chcp 65001 >nul

echo =====================================
echo CHAT BOT VERSION 2 - ZERO CLICK PUSH
echo =====================================

REM Проверка git
where git >nul 2>&1
if %errorlevel% neq 0 (
echo [ERROR] Git not found
pause
exit /b
)

echo [OK] Git detected

REM Добавляем файлы
echo [INFO] Adding changed files...
git add .

REM Коммит
echo [INFO] Creating commit...
git commit -m "AUTO PUSH UPDATE" 2>nul

REM Подтягиваем изменения с GitHub
echo [INFO] Syncing with remote (rebase)...
git pull --rebase origin main

if %errorlevel% neq 0 (
echo [ERROR] Rebase failed. Resolve conflicts manually.
pause
exit /b
)

REM Пуш
echo [INFO] Pushing to GitHub...
git push origin main

if %errorlevel% neq 0 (
echo [ERROR] Push failed.
pause
exit /b
)

echo [SUCCESS] Push completed!
pause
