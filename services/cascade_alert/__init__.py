"""Live cascade alert — активация post-cascade edge.

Backtest найден: long-cascade >=5 BTC за 5 минут → 73% случаев цена выше через 12h,
средний рост +1.14%. См. docs/ANALYSIS/POST_LIQUIDATION_CASCADE_2026-05-07.md.

Этот модуль каждые 60 секунд читает market_live/liquidations.csv и проверяет:
- сумма long_liq за последние 5 мин >= 5 BTC → push 'CASCADE LONG' в Telegram
- сумма short_liq за последние 5 мин >= 5 BTC → push 'CASCADE SHORT' в Telegram

Дедуп: один alert per cascade event (cooldown 30 мин на side).
"""
from .loop import cascade_alert_loop

__all__ = ["cascade_alert_loop"]
