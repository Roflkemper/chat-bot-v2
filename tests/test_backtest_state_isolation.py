from __future__ import annotations

import json
from hashlib import md5
from pathlib import Path

import pytest

try:
    from core.backtest_engine import run_backtest_from_candles
except ModuleNotFoundError as exc:
    # In some dev environments a top-level "features" package is not present,
    # which makes core.pipeline unimportable. Don't turn that into a new
    # collection error; skip these tests until the environment is complete.
    if "features.trigger_detection" not in str(exc):
        raise
    run_backtest_from_candles = None  # type: ignore[assignment]


ROOT = Path(__file__).resolve().parents[1]
FROZEN_DATASET = ROOT / "backtests" / "frozen" / "BTCUSDT_1h_180d_frozen.json"
REGIME_STATE = ROOT / "state" / "regime_state.json"


def _load_frozen_candles() -> list[dict]:
    payload = json.loads(FROZEN_DATASET.read_text(encoding="utf-8"))
    return list(payload.get("candles") or payload)


def _file_md5(path: Path) -> str | None:
    if not path.exists():
        return None
    return md5(path.read_bytes()).hexdigest()


def test_backtest_does_not_modify_live_state(tmp_path: Path):
    if run_backtest_from_candles is None:
        pytest.skip("core.pipeline import blocked (missing features package)")
    candles = _load_frozen_candles()
    before_hash = _file_md5(REGIME_STATE)
    before_mtime = REGIME_STATE.stat().st_mtime if REGIME_STATE.exists() else None

    run_backtest_from_candles(
        candles,
        symbol="BTCUSDT",
        timeframe="1h",
        lookback_days=180,
        output_dir=tmp_path / "run1",
    )

    after_hash = _file_md5(REGIME_STATE)
    after_mtime = REGIME_STATE.stat().st_mtime if REGIME_STATE.exists() else None
    assert after_hash == before_hash
    assert after_mtime == before_mtime


def test_two_backtest_runs_independent(tmp_path: Path):
    if run_backtest_from_candles is None:
        pytest.skip("core.pipeline import blocked (missing features package)")
    candles = _load_frozen_candles()
    before_hash = _file_md5(REGIME_STATE)

    a = run_backtest_from_candles(
        candles,
        symbol="BTCUSDT",
        timeframe="1h",
        lookback_days=180,
        output_dir=tmp_path / "a",
    )
    b = run_backtest_from_candles(
        candles,
        symbol="BTCUSDT",
        timeframe="1h",
        lookback_days=180,
        output_dir=tmp_path / "b",
    )

    keys = ("trades", "winrate", "pnl_pct", "max_drawdown_pct")
    assert {k: a[k] for k in keys} == {k: b[k] for k in keys}
    assert _file_md5(REGIME_STATE) == before_hash

