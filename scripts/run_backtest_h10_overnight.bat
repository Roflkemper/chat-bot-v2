@echo off
setlocal

set TIMESTAMP=%date:~6,4%%date:~3,2%%date:~0,2%_%time:~0,2%%time:~3,2%
set TIMESTAMP=%TIMESTAMP: =0%
set LOGFILE=logs\backtest_overnight_%TIMESTAMP%.log

if not exist logs mkdir logs

echo === H10 Backtest Overnight === > %LOGFILE%
echo Started: %date% %time% >> %LOGFILE%
echo Command: python -m scripts.backtest_h10 --start 2024-04-28 --end 2026-04-24 >> %LOGFILE%
echo. >> %LOGFILE%

python -m scripts.backtest_h10 --start 2024-04-28 --end 2026-04-24 >> %LOGFILE% 2>&1

echo. >> %LOGFILE%
echo Finished: %date% %time% >> %LOGFILE%
echo === END === >> %LOGFILE%

endlocal
