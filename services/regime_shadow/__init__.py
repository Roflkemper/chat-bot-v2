"""Stage B3 — ML-based regime classifier shadow mode.

Runs services.regime_red_green's sklearn DT (77.5% train accuracy) alongside
the production Classifier A, every 5 min on BTCUSDT 1h data. Both verdicts
written to state/regime_shadow.jsonl for offline comparison after 30 days
of parallel operation.

Decision (handoff 2026-05-09 Stage B3):
  if B (DT) catches regime-shift earlier than A → switch DL R-* rules to use B.
  Until 30 days of comparison data exist, B is observation-only; production
  signals remain on A.
"""
from .loop import regime_shadow_loop  # noqa: F401
