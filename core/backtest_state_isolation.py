from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterator
import shutil

from core import pattern_memory
from core import pipeline
from core.orchestrator.regime_classifier import RegimeStateStore
import storage.bot_manager_state as _bms_module
import storage.personal_bot_learning as _pbl_module
import storage.transition_alerts as _tra_module


_BASELINE_JSON_FILES = (
    "regime_state.json",
    "bot_manager_state.json",
    "personal_bot_learning.json",
    "transition_alert_state.json",
    "grid_portfolio.json",
)


@contextmanager
def backtest_state_isolation(
    state_root: str | Path = "state",
    baseline_root: str | Path | None = None,
) -> Iterator[Path]:
    """Run backtests against a temporary copy of state files."""
    source_root = Path(state_root)
    baseline = Path(baseline_root) if baseline_root is not None else (source_root / "baseline")
    with TemporaryDirectory(prefix="backtest-state-") as tmpdir:
        isolated_root = Path(tmpdir)
        isolated_root.mkdir(parents=True, exist_ok=True)

        for path in source_root.glob("pattern_memory_*.csv"):
            if path.is_file():
                shutil.copy2(path, isolated_root / path.name)

        for name in _BASELINE_JSON_FILES:
            src = baseline / name
            if src.exists():
                shutil.copy2(src, isolated_root / name)

        regime_dst = isolated_root / "regime_state.json"
        bms_dst = isolated_root / "bot_manager_state.json"
        pbl_dst = isolated_root / "personal_bot_learning.json"
        tra_dst = isolated_root / "transition_alert_state.json"

        original_cache_dir = pattern_memory.CACHE_DIR
        original_bms_path = _bms_module.BOT_MANAGER_STATE_FILE
        original_pbl_path = _pbl_module.PERSONAL_BOT_LEARNING_FILE
        original_tra_path = _tra_module.STATE_FILE

        # Some older code paths used pipeline._regime_store; keep backward compatibility
        # if the attribute exists, but prefer DI via pipeline.build_full_snapshot(state_dir=...).
        original_regime_store = getattr(pipeline, "_regime_store", None)
        if hasattr(pipeline, "_regime_store"):
            pipeline._regime_store = RegimeStateStore(str(regime_dst))
        pattern_memory.CACHE_DIR = isolated_root
        _bms_module.BOT_MANAGER_STATE_FILE = str(bms_dst)
        _pbl_module.PERSONAL_BOT_LEARNING_FILE = str(pbl_dst)
        _tra_module.STATE_FILE = str(tra_dst)
        try:
            yield isolated_root
        finally:
            if hasattr(pipeline, "_regime_store"):
                pipeline._regime_store = original_regime_store
            pattern_memory.CACHE_DIR = original_cache_dir
            _bms_module.BOT_MANAGER_STATE_FILE = original_bms_path
            _pbl_module.PERSONAL_BOT_LEARNING_FILE = original_pbl_path
            _tra_module.STATE_FILE = original_tra_path
