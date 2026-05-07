"""BitMEX read-only account poller — auto-update margin.

Каждые 60 секунд опрашиваем BitMEX REST:
- /api/v1/user/margin (current margin balance, available, used)
- /api/v1/position (current positions + liquidation prices)

Записываем в state/margin_automated.jsonl (формат MarginRecord, тот же что
от operator /margin command). read_latest_margin() автоматически выберет
более свежий источник между manual override и автоматическим polling.

API ключ читается из .env.local (gitignored):
  BITMEX_API_KEY=...
  BITMEX_API_SECRET=...

Permission: only Order:none / Read-only. Никакого withdraw / trading.

Если ключ отсутствует или ошибка авторизации — loop завершается с warning,
не крашит app_runner.
"""
from .poller import bitmex_poll_loop, fetch_account_snapshot

__all__ = ["bitmex_poll_loop", "fetch_account_snapshot"]
