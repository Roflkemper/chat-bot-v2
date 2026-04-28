@echo off
:: bot7 auto-start — используется Task Scheduler для запуска при входе в систему
:: Задача: "bot7-supervisor"
cd /d C:\bot7
call .venv\Scripts\activate.bat
python -m bot7 start
