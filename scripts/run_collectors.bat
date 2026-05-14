@echo off
REM Start collectors in background. Output goes to logs/collectors.log
REM Usage: run_collectors.bat

cd /d %~dp0..
if not exist logs mkdir logs

echo Starting collectors...
start /B "" .venv\Scripts\python.exe -m collectors.main >> logs\collectors.log 2>&1
echo PID written to run\collectors.pid
echo Logs: logs\collectors.log
