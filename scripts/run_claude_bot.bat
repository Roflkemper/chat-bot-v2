@echo off
REM Run Claude Telegram bot
REM Requires CLAUDE_BOT_TOKEN and ANTHROPIC_API_KEY in .env

cd /d %~dp0..
call venv\Scripts\activate.bat 2>nul || call .venv\Scripts\activate.bat 2>nul

echo Starting Claude bot...
python -m services.claude_bot.bot
