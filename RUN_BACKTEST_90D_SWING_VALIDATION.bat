@echo off
setlocal
cd /d %~dp0

echo ============================
echo BACKTEST 90D START [SWING VALIDATION]
echo ============================

if exist .venv\Scripts\python.exe (
  echo [INFO] Using project venv python
  .venv\Scripts\python.exe run_backtest.py --mode auto --lookback-days 90 --timeframe 1h
  set EXIT_CODE=%ERRORLEVEL%
) else (
  echo [INFO] Using system python
  python run_backtest.py --mode auto --lookback-days 90 --timeframe 1h
  set EXIT_CODE=%ERRORLEVEL%
)

echo.
echo [INFO] Exit code: %EXIT_CODE%
echo ============================
echo BACKTEST 90D FINISHED
echo ============================
pause
exit /b %EXIT_CODE%
