"""TEST_3 TP-flat dry-run simulator.

Operator decision 2026-05-09 (after TZ-TP-AUTOUPDATE-BACKTEST 0..10 windows):
  grid-bag wins on PnL, but TP-flat wins on drawdown by 3-5×.
  → keep grid-bag as default, but A/B-test TP-flat on TEST_3 (worst SHORT bot
    by KPI) as risk-contained alternative.

This simulator is paper-only (does NOT touch GinArea):
  - polls BTCUSDT 1m every 60s
  - applies gate (EMA50/EMA200/close on 1h) — same as backtest script
  - opens virtual SHORT @ $1000 notional when SHORT-gate fires
  - closes whole leg at +$10 unrealized (TP-flat #1)
  - reentry IMMEDIATE (open at next bar close after TP)
  - dd_cap = 3% (force-close)
  - all events appended to state/test3_tpflat_paper.jsonl

After 7 days: tools/_test3_tpflat_report.py compares simulated vs real
TEST_3 PnL/DD/volume from operator_journal/decisions.parquet. Decision
to migrate live or not goes back to operator.
"""
from .loop import test3_tpflat_simulator_loop  # noqa: F401
