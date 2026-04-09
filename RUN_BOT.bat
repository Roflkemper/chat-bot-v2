@echo off
setlocal
title CHAT BOT VERSION 2 - FINAL
if not exist .venv (
    py -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install -r requirements.txt
python main.py
pause
