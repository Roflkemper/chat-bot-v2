"""Spike-defensive alert service.

Watches for sharp price spikes that threaten short-bag positions on GinArea bots.
When |move 5m| > 1.5% AND taker buy/sell skew > 75% AND OI rising, emits a
TG card warning the operator: "spike! close SHORT-bags". Does NOT trade.

Goal (operator request 2026-05-09): preserve $4-7k drawdown that hits 3 SHORT
bots simultaneously when BTC spikes +3% in minutes.

Implementation:
  - 60s poll loop on BTC/ETH/XRP
  - reads recent 1m klines via core.data_loader.load_klines (cached)
  - reads taker_buy_pct + oi_change_1h_pct from state/deriv_live.json
  - computes 5-bar (5min) absolute return on close
  - dedup: 30min cooldown per (symbol, direction)

Tunables (services/spike_alert/loop.py):
  PRICE_MOVE_THRESHOLD_PCT = 1.5
  TAKER_DOMINANT_PCT = 75.0
  OI_RISING_THRESHOLD_PCT = 0.0
  WINDOW_MINUTES = 5
  COOLDOWN_SEC = 1800
"""
from .loop import spike_alert_loop  # noqa: F401
