"""TEST_3 TP-flat dry-run B variant — TP=$5 immediate dd=3%.

Operator's secondary candidate from TZ-TP-AUTOUPDATE backtest analysis:
  Higher trade frequency than TP=$10 but typically lower per-trade PnL.
  A/B-tested alongside the primary TP=$10 variant; the comparison tool
  in tools/_test3_tpflat_compare.py can read both journals.
"""
from .loop import test3_tpflat_b_simulator_loop  # noqa: F401
