@echo off
REM Prepare bot7 data transfer package for Mac.
REM Creates 3 tar.gz archives in C:\bot7-transfer\
REM Run: scripts\prepare_mac_transfer.bat

setlocal EnableDelayedExpansion

set REPO=C:\bot7
set OUT=C:\bot7-transfer
for /f %%a in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set STAMP=%%a

if not exist "%REPO%\app_runner.py" (
    echo ERROR: %REPO%\app_runner.py not found
    exit /b 1
)

if not exist "%OUT%" mkdir "%OUT%"
cd /d "%REPO%"

echo.
echo Pack 1 of 3: state (journals, dedup, KPI history)
tar --exclude=state/_archive --exclude=state/calibration -czf "%OUT%\bot7_state_%STAMP%.tar.gz" state
if errorlevel 1 (echo FAILED pack 1 & exit /b 1)
for %%I in ("%OUT%\bot7_state_%STAMP%.tar.gz") do echo   -^> bot7_state_%STAMP%.tar.gz (%%~zI bytes)

echo.
echo Pack 2 of 3: ginarea_live (bot snapshots)
tar --exclude=ginarea_live/snapshots_backup_2026-05-02.csv --exclude=ginarea_live/tracker.log -czf "%OUT%\bot7_ginarea_live_%STAMP%.tar.gz" ginarea_live
if errorlevel 1 (echo FAILED pack 2 & exit /b 1)
for %%I in ("%OUT%\bot7_ginarea_live_%STAMP%.tar.gz") do echo   -^> bot7_ginarea_live_%STAMP%.tar.gz (%%~zI bytes)

echo.
echo Pack 3 of 3: market_live (CSV only, no orderbook)
tar --exclude=market_live/orderbook --exclude=market_live/liquidations --exclude=market_live/collector.log --exclude=market_live/collector.log.1 --exclude=market_live/collector.log.2 --exclude=market_live/collector.log.3 --exclude=market_live/liquidations.csv.pre-okx-normalize.bak -czf "%OUT%\bot7_market_live_%STAMP%.tar.gz" market_live
if errorlevel 1 (echo FAILED pack 3 & exit /b 1)
for %%I in ("%OUT%\bot7_market_live_%STAMP%.tar.gz") do echo   -^> bot7_market_live_%STAMP%.tar.gz (%%~zI bytes)

echo.
echo Secrets: build secrets.txt (with .env.local + system env)
set SECRETS=%OUT%\bot7_secrets_%STAMP%.txt
echo # bot7 secrets snapshot - %STAMP% > "%SECRETS%"
echo # SECRETS! Use 1Password / AirDrop / encrypted ZIP only. >> "%SECRETS%"
echo. >> "%SECRETS%"
echo # === .env.local content === >> "%SECRETS%"
if exist "%REPO%\.env.local" type "%REPO%\.env.local" >> "%SECRETS%"
echo. >> "%SECRETS%"
echo # === System env (Windows User scope) === >> "%SECRETS%"
echo BOT_TOKEN=%BOT_TOKEN% >> "%SECRETS%"
echo CHAT_ID=%CHAT_ID% >> "%SECRETS%"
echo. >> "%SECRETS%"
echo # === Mac setup === >> "%SECRETS%"
echo # 1. Copy .env.local section above to ~/code/bot7/.env.local >> "%SECRETS%"
echo # 2. Add BOT_TOKEN and CHAT_ID there too >> "%SECRETS%"
echo # 3. See docs/MAC_NIGHT_MIRROR.md steps 1-2 >> "%SECRETS%"
echo   -^> bot7_secrets_%STAMP%.txt

echo.
echo TOTAL
echo Folder: %OUT%
dir /b /o-s "%OUT%\bot7_*_%STAMP%.*"

echo.
echo Next: transfer 3 tar.gz to Mac (AirDrop / USB / scp).
echo See docs/MAC_NIGHT_MIRROR.md step 4.
