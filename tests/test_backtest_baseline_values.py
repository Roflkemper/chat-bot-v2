from __future__ import annotations

import json
from pathlib import Path

from core.backtest_engine import run_backtest_from_candles


ROOT = Path(__file__).resolve().parents[1]
FROZEN_DATASET = ROOT / "backtests" / "frozen" / "BTCUSDT_1h_180d_frozen.json"

EXPECTED = {
    "trades": 24,
    "winrate": 75.0,
    "pnl_pct": 14.3393,
    "max_drawdown_pct": 2.1542,
}


def test_baseline_values_match_canonical(tmp_path: Path):
    payload = json.loads(FROZEN_DATASET.read_text(encoding="utf-8"))
    candles = list(payload.get("candles") or payload)
    result = run_backtest_from_candles(
        candles,
        symbol="BTCUSDT",
        timeframe="1h",
        lookback_days=180,
        output_dir=tmp_path,
    )
    assert result["trades"] == EXPECTED["trades"]
    assert abs(result["winrate"] - EXPECTED["winrate"]) < 0.01
    assert abs(result["pnl_pct"] - EXPECTED["pnl_pct"]) < 0.001
    assert abs(result["max_drawdown_pct"] - EXPECTED["max_drawdown_pct"]) < 0.001
