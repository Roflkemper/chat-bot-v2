DETERMINISTIC BACKTEST MODE
===========================

Что добавлено:
1) RUN_BACKTEST_90D.bat
   - теперь режим AUTO
   - если есть frozen-файл backtests/frozen/BTCUSDT_1h_90d_frozen.json,
     бектест идёт по нему
   - если frozen-файла нет, идёт live-загрузка

2) RUN_BACKTEST_90D_FREEZE_DATA.bat
   - один раз сохраняет текущий набор свечей в frozen-файл
   - после этого следующие прогоны через RUN_BACKTEST_90D.bat будут детерминированными

3) RUN_BACKTEST_90D_LIVE.bat
   - всегда живой прогон с биржи, без frozen-режима

4) SHOW_CURRENT_SETTINGS.bat
   - выгружает текущие настройки в reports/current_bot_settings.txt и .json

Как пользоваться:
Шаг 1. Запусти RUN_BACKTEST_90D_FREEZE_DATA.bat
Шаг 2. Запусти RUN_BACKTEST_90D.bat
Шаг 3. Для всех следующих сравнений версий используй тот же frozen-файл

Важно:
- если хочешь сравнивать релизы честно, не перезаписывай frozen-файл перед каждым запуском
- новый frozen-файл делай только тогда, когда сознательно хочешь новый эталон рынка
