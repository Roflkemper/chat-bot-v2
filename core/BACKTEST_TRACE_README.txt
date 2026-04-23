BACKTEST TRACE RELEASE

После запуска RUN_BACKTEST_TRACE_90D.bat будут созданы:
- backtests/backtest_90d_report.json
- backtests/backtest_90d_trace.json
- backtests/backtest_90d_loss_focus.json

Что смотреть:
1) backtest_90d_loss_focus.json
   Показывает только убыточные PRESSURE_FLIP_ARM SHORT с полным snapshot входа.
2) backtest_90d_trace.json
   Показывает все ENTRY_REJECTED / ENTRY_EXECUTED / TRADE_CLOSED события.

Цель:
Найти, почему именно entry 120 / 141 / 681 проходят gate и входят в рынок.
