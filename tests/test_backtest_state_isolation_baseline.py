from __future__ import annotations

import json
from pathlib import Path

import storage.bot_manager_state as bms
import storage.personal_bot_learning as pbl
import storage.transition_alerts as tra
from core.backtest_state_isolation import backtest_state_isolation
from core.backtest_engine import run_backtest_from_candles


BASELINE_FILES = {
    "regime_state.json": {"marker": "CANONICAL_REGIME"},
    "bot_manager_state.json": {"marker": "CANONICAL_BMS"},
    "personal_bot_learning.json": {"marker": "CANONICAL_PBL"},
    "transition_alert_state.json": {"marker": "CANONICAL_TRA"},
    "grid_portfolio.json": {"marker": "CANONICAL_GRID"},
}


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _prepare_state_tree(tmp_path: Path) -> Path:
    state_root = tmp_path / "state"
    baseline_root = state_root / "baseline"
    state_root.mkdir()
    baseline_root.mkdir()
    (state_root / "pattern_memory_BTCUSDT_1h_2026.csv").write_text("col\nvalue\n", encoding="utf-8")
    for name, payload in BASELINE_FILES.items():
        _write_json(baseline_root / name, payload)
    _write_json(state_root / "regime_state.json", {"marker": "LIVE_REGIME"})
    _write_json(state_root / "bot_manager_state.json", {"marker": "LIVE_BMS"})
    return state_root


def test_isolation_copies_from_baseline_not_live(tmp_path: Path):
    state_root = _prepare_state_tree(tmp_path)

    with backtest_state_isolation(state_root=state_root) as isolated:
        data = json.loads((isolated / "regime_state.json").read_text(encoding="utf-8"))
        assert data["marker"] == "CANONICAL_REGIME"


def test_isolation_copies_all_four_state_files(tmp_path: Path):
    state_root = _prepare_state_tree(tmp_path)

    with backtest_state_isolation(state_root=state_root) as isolated:
        assert (isolated / "regime_state.json").exists()
        assert (isolated / "bot_manager_state.json").exists()
        assert (isolated / "personal_bot_learning.json").exists()
        assert (isolated / "transition_alert_state.json").exists()
        assert (isolated / "grid_portfolio.json").exists()


def test_isolation_restores_constants_after_context(tmp_path: Path):
    state_root = _prepare_state_tree(tmp_path)
    original_bms = bms.BOT_MANAGER_STATE_FILE
    original_pbl = pbl.PERSONAL_BOT_LEARNING_FILE
    original_tra = tra.STATE_FILE

    with backtest_state_isolation(state_root=state_root) as isolated:
        assert bms.BOT_MANAGER_STATE_FILE == str(isolated / "bot_manager_state.json")
        assert pbl.PERSONAL_BOT_LEARNING_FILE == str(isolated / "personal_bot_learning.json")
        assert tra.STATE_FILE == str(isolated / "transition_alert_state.json")

    assert bms.BOT_MANAGER_STATE_FILE == original_bms
    assert pbl.PERSONAL_BOT_LEARNING_FILE == original_pbl
    assert tra.STATE_FILE == original_tra


def test_baseline_files_exist():
    root = Path(__file__).resolve().parents[1] / "state" / "baseline"
    for name in BASELINE_FILES:
        path = root / name
        assert path.exists()
        json.loads(path.read_text(encoding="utf-8"))


def test_backtest_deterministic_across_live_mutations(tmp_path: Path):
    state_root = _prepare_state_tree(tmp_path)
    repo_root = Path(__file__).resolve().parents[1]
    dataset = repo_root / "backtests" / "frozen" / "BTCUSDT_1h_180d_frozen.json"
    payload = json.loads(dataset.read_text(encoding="utf-8"))
    candles = list(payload.get("candles") or payload)

    from core import backtest_engine

    original_isolation = backtest_engine.backtest_state_isolation

    def _isolated_for_tmp_state():
        return original_isolation(state_root=state_root)

    backtest_engine.backtest_state_isolation = _isolated_for_tmp_state
    try:
        result_a = run_backtest_from_candles(
            candles,
            symbol="BTCUSDT",
            timeframe="1h",
            lookback_days=180,
            output_dir=tmp_path / "run_a",
        )

        _write_json(state_root / "regime_state.json", {"marker": "LIVE_GARBAGE"})
        _write_json(state_root / "bot_manager_state.json", {"marker": "LIVE_GARBAGE"})

        result_b = run_backtest_from_candles(
            candles,
            symbol="BTCUSDT",
            timeframe="1h",
            lookback_days=180,
            output_dir=tmp_path / "run_b",
        )
    finally:
        backtest_engine.backtest_state_isolation = original_isolation

    keys = ("trades", "winrate", "pnl_pct", "max_drawdown_pct")
    assert {key: result_a[key] for key in keys} == {key: result_b[key] for key in keys}
