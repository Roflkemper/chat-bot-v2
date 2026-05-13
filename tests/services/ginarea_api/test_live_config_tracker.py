"""Tests for live_config_tracker."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from services.ginarea_api.live_config_tracker import (
    LiveConfig,
    active_configs,
    add_config,
    days_since,
    expected_so_far_usd,
    mark_stopped,
)


def _mk(bot_id: str = "b1") -> LiveConfig:
    return LiveConfig(
        bot_id=bot_id, name="test", side="long",
        gs=0.04, thresh=1.5, td=0.85, mult=1.2, tp="off", max_size="100/300",
        started_at=datetime.now(timezone.utc).isoformat(),
        expected_profit_3mo_usd=22_000.0,
        expected_vol_3mo_musd=4.5,
        expected_peak_usd=70_000.0,
    )


def test_add_and_read(tmp_path: Path) -> None:
    p = tmp_path / "s.json"
    cfg = _mk("b1")
    add_config(cfg, path=p)
    rows = active_configs(path=p)
    assert len(rows) == 1
    assert rows[0]["bot_id"] == "b1"


def test_mark_stopped_filters_active(tmp_path: Path) -> None:
    p = tmp_path / "s.json"
    add_config(_mk("b1"), path=p)
    add_config(_mk("b2"), path=p)
    assert mark_stopped("b1", path=p) is True
    active = active_configs(path=p)
    assert len(active) == 1
    assert active[0]["bot_id"] == "b2"


def test_days_since_zero_for_now() -> None:
    now = datetime.now(timezone.utc).isoformat()
    assert days_since(now) < 0.01


def test_days_since_handles_bad_input() -> None:
    assert days_since("garbage") == 0.0
    assert days_since("") == 0.0


def test_expected_so_far_linear() -> None:
    started = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    cfg_dict = {
        "started_at": started,
        "expected_profit_3mo_usd": 22_500.0,
    }
    val = expected_so_far_usd(cfg_dict)
    # 30 days / 90 days × 22500 = 7500 (±tolerance)
    assert 7_400 < val < 7_600


def test_mark_stopped_returns_false_for_unknown(tmp_path: Path) -> None:
    p = tmp_path / "s.json"
    add_config(_mk("b1"), path=p)
    assert mark_stopped("nope", path=p) is False
