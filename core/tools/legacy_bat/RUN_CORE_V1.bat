@echo off
cd /d %~dp0
if not exist .venv (
    python -m venv .venv
)
call .venv\Scriptsctivate
pip install -r requirements.txt
python appootstrap.py
pause
