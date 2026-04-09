@echo off
cd /d "%~dp0"
set LOGFILE=%~dp0run_log.txt
if not exist ".venv\Scripts\python.exe" python -m venv .venv >> "%LOGFILE%" 2>&1
".venv\Scripts\python.exe" -m pip install -r requirements.txt >> "%LOGFILE%" 2>&1
".venv\Scripts\python.exe" -u main.py >> "%LOGFILE%" 2>&1
echo Exit code: %errorlevel%>> "%LOGFILE%"
pause
