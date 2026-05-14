# Stable Baseline

Date fixed: 2026-04-19
Baseline source: `state/baseline/*.json` (canonical snapshot from TZ-011)

Dataset:
- `backtests/frozen/BTCUSDT_1h_180d_frozen.json`

Deterministic baseline:
- Trades: `24`
- Winrate: `75.0%`
- Avg RR: `0.3446`
- PnL: `+14.3393%`
- Max DD: `-2.1542%`

Verification:
- `tests/test_backtest_determinism.py`: 3 in-process runs returned identical metrics.
- `tests/test_backtest_baseline_values.py`: canonical metric values match the fixed baseline.
- `RUN_TESTS.bat`: passes with the TZ-011 canonical baseline in place.

Notes:
- Before TZ-011, baseline drifted because backtests started from live `state/*.json`.
- TZ-011 fixes this by routing backtest isolation to `state/baseline/*.json`.
- If baseline is intentionally re-frozen after logic changes, update `state/baseline/*.json` and this file together.
