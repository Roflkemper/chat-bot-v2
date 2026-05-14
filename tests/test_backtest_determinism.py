from __future__ import annotations

import json
from hashlib import md5
from pathlib import Path

from core.backtest_engine import run_backtest_from_candles


ROOT = Path(__file__).resolve().parents[1]
FROZEN_DATASET = ROOT / "backtests" / "frozen" / "BTCUSDT_1h_180d_frozen.json"
REGIME_STATE = ROOT / "state" / "regime_state.json"
KEYS = ("trades", "winrate", "pnl_pct", "max_drawdown_pct")


def _load_frozen_candles() -> list[dict]:
    payload = json.loads(FROZEN_DATASET.read_text(encoding="utf-8"))
    return list(payload.get("candles") or payload)


def _file_md5(path: Path) -> str | None:
    if not path.exists():
        return None
    return md5(path.read_bytes()).hexdigest()


def _metrics(result: dict) -> dict:
    return {key: result[key] for key in KEYS}


def test_backtest_is_deterministic_on_frozen_dataset(tmp_path: Path):
    candles = _load_frozen_candles()
    before_regime_hash = _file_md5(REGIME_STATE)

    results = []
    for _ in range(3):
        results.append(
            run_backtest_from_candles(
                candles,
                symbol="BTCUSDT",
                timeframe="1h",
                lookback_days=180,
                output_dir=tmp_path,
            )
        )

    metrics = [_metrics(item) for item in results]
    assert metrics[0] == metrics[1] == metrics[2]

    after_regime_hash = _file_md5(REGIME_STATE)
    assert after_regime_hash == before_regime_hash
