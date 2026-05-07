"""Momentum check — intraday trader assistant.

Аггрегирует:
- Текущая сессия (Asia/London/NY) + dominant side
- Character движения 15m / 1h (impulse / fade / chop / exhaustion)
- Volume в последние свечи (растёт / падает)
- RSI divergence detection
- Recent liquidations (5/15/60 min) + сторона
- OI / funding live (state/deriv_live.json)
- Premium pct (mark vs index)

Returns dict ready для /momentum_check Telegram command.
"""
from .check import build_momentum_check, format_momentum_check

__all__ = ["build_momentum_check", "format_momentum_check"]
