from __future__ import annotations

from datetime import date, datetime, timezone

from core.orchestrator.calibration_log import CalibrationLog
from core.orchestrator.command_dispatcher import dispatch_orchestrator_decisions
from core.orchestrator.killswitch import KillswitchStore
from core.orchestrator.portfolio_state import Bot, PortfolioStore


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()


def _store(tmp_path):
    return PortfolioStore(str(tmp_path / "state" / "grid_portfolio.json"))


def _regime(primary: str, modifiers: list[str] | None = None):
    return {
        "primary": primary,
        "modifiers": modifiers or [],
        "bias_score": 12,
        "metrics": {"adx_1h": 28},
    }


def test_dispatch_no_changes_when_aligned(tmp_path):
    store = _store(tmp_path)
    result = dispatch_orchestrator_decisions(store, _regime("RANGE"))
    assert not result.changed
    assert set(result.unchanged) == {"btc_short", "btc_long", "btc_long_l2"}


def test_dispatch_detects_regime_change(tmp_path):
    store = _store(tmp_path)
    result = dispatch_orchestrator_decisions(store, _regime("TREND_DOWN"))
    assert any(change.category_key == "btc_long" for change in result.changed)


def test_dispatch_updates_store_correctly(tmp_path):
    store = _store(tmp_path)
    dispatch_orchestrator_decisions(store, _regime("TREND_DOWN"))
    assert store.get_category("btc_long").orchestrator_action == "PAUSE"


def test_dispatch_preserves_paused_manual(tmp_path):
    store = _store(tmp_path)
    store.add_bot(Bot(key="btc_long_manual", category="btc_long", label="manual", strategy_type="GRID_L1", stage="LIVE", state="PAUSED_MANUAL"))
    dispatch_orchestrator_decisions(store, _regime("TREND_DOWN"))
    assert store.get_bot("btc_long_manual").state == "PAUSED_MANUAL"


def test_dispatch_generates_alerts_for_changes(tmp_path):
    store = _store(tmp_path)
    result = dispatch_orchestrator_decisions(store, _regime("TREND_DOWN"))
    assert result.alerts


def test_dispatch_alert_kind_action_required_for_pause(tmp_path):
    store = _store(tmp_path)
    result = dispatch_orchestrator_decisions(store, _regime("TREND_DOWN"))
    alert = next(item for item in result.alerts if item.category_key == "btc_long")
    assert alert.kind == "ACTION_REQUIRED"


def test_dispatch_alert_kind_regime_change_for_run(tmp_path):
    store = _store(tmp_path)
    store.set_category_action("btc_short", "PAUSE", "manual")
    result = dispatch_orchestrator_decisions(store, _regime("TREND_DOWN"))
    alert = next(item for item in result.alerts if item.category_key == "btc_short")
    assert alert.kind == "REGIME_CHANGE"


def test_dispatch_with_blackout_all_stopped(tmp_path):
    store = _store(tmp_path)
    result = dispatch_orchestrator_decisions(store, _regime("RANGE", ["NEWS_BLACKOUT"]))
    assert result.changed
    assert all(store.get_category(key).orchestrator_action == "STOP" for key in ("btc_short", "btc_long", "btc_long_l2"))


def test_dispatch_empty_portfolio(tmp_path):
    store = _store(tmp_path)
    store._state = {
        "version": 3,
        "updated_at": None,
        "categories": {},
        "bots": {},
        "portfolio_state": {"mode": "NORMAL", "daily_pnl_usd": 0, "margin_used_pct": 0},
    }
    result = dispatch_orchestrator_decisions(store, _regime("RANGE"))
    assert result.changed == []
    assert result.unchanged == []


def test_dispatch_disabled_category_skipped(tmp_path):
    store = _store(tmp_path)
    state = store._ensure_loaded()
    state["categories"]["btc_long"]["enabled"] = False
    result = dispatch_orchestrator_decisions(store, _regime("TREND_DOWN"))
    assert "btc_long" in result.unchanged
    assert store.get_category("btc_long").orchestrator_action == "RUN"


def test_dispatch_noop_when_killswitch_active(tmp_path, monkeypatch):
    monkeypatch.setattr(KillswitchStore, "_instance", KillswitchStore(tmp_path / "state" / "killswitch_state.json"))
    KillswitchStore.instance().trigger("MANUAL", "operator")
    store = _store(tmp_path)
    result = dispatch_orchestrator_decisions(store, _regime("TREND_DOWN"))
    assert result.changed == []


def test_dispatch_logs_calibration_events(tmp_path, monkeypatch):
    monkeypatch.setattr(KillswitchStore, "_instance", KillswitchStore(tmp_path / "state" / "killswitch_state.json"))
    monkeypatch.setattr(CalibrationLog, "_instance", None)
    CalibrationLog.instance(tmp_path / "state" / "calibration")
    store = _store(tmp_path)
    dispatch_orchestrator_decisions(store, _regime("TREND_DOWN"))
    events = CalibrationLog.instance().read_events(_utc_today())
    assert any(event["event_type"] == "REGIME_SHIFT" for event in events)
    assert any(event["event_type"] == "ACTION_CHANGE" for event in events)
