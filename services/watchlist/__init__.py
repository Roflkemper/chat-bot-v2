"""Watchlist — оператор задаёт условия, бот алертит когда они срабатывают.

Команды Telegram:
  /watch — показать активные правила
  /watch add <rule> — добавить
  /watch del <id> — удалить
  /watch on/off <id>

Поддерживаемые conditions (расширяемо):
  funding > 0.01           — funding выше 0.01%
  funding < -0.005
  long_pct > 60            — толпа в long выше 60%
  short_pct > 60
  taker_sell > 70          — taker sell volume выше 70%
  taker_buy > 70
  oi_spike > 2             — OI 15min change выше 2%
  premium > 0.1
  premium < -0.1
  cascade_long >= 5        — long-cascade 5 BTC за 5 мин (alias на B1)
  btc_d > 60               — BTC dominance выше 60%
  price > 85000            — BTC price выше 85k
  price < 80000

State: state/watchlist.json (rules + last fired timestamps for dedup).
"""
from .rules import (
    Rule, load_rules, save_rules, add_rule, remove_rule, toggle_rule,
    evaluate_rules, format_rule_summary,
)
from .loop import watchlist_loop

__all__ = [
    "Rule", "load_rules", "save_rules", "add_rule", "remove_rule",
    "toggle_rule", "evaluate_rules", "format_rule_summary", "watchlist_loop",
]
