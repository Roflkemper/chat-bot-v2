from __future__ import annotations

from datetime import date, datetime, timezone

from core.orchestrator.calibration_log import CalibrationLog
from core.orchestrator.killswitch import KillswitchStore, trigger_killswitch
from core.orchestrator.portfolio_state import PortfolioStore


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()


def _ks(tmp_path):
    return KillswitchStore(str(tmp_path / "state" / "killswitch_state.json"))


def test_killswitch_store_defaults(tmp_path):
    store = _ks(tmp_path)
    assert store.is_active() is False
    assert store.get_current_event() is None


def test_killswitch_trigger_sets_active_state(tmp_path):
    store = _ks(tmp_path)
    store.trigger("MARGIN_DRAWDOWN", 18.5)
    event = store.get_current_event()
    assert store.is_active() is True
    assert event["reason"] == "MARGIN_DRAWDOWN"
    assert event["reason_value"] == 18.5


def test_killswitch_disable_moves_event_to_history(tmp_path):
    store = _ks(tmp_path)
    store.trigger("MANUAL", "operator")
    store.disable(operator="tester")
    assert store.is_active() is False
    history = store.get_history()
    assert len(history) == 1
    assert history[0]["disabled_by"] == "tester"


def test_killswitch_singleton_instance(tmp_path, monkeypatch):
    monkeypatch.setattr(KillswitchStore, "_instance", None)
    first = KillswitchStore.instance(tmp_path / "state" / "killswitch_state.json")
    second = KillswitchStore.instance(tmp_path / "state" / "killswitch_state.json")
    assert first is second


def test_trigger_killswitch_sets_all_categories(tmp_path, monkeypatch):
    portfolio = PortfolioStore(str(tmp_path / "state" / "grid_portfolio.json"))
    monkeypatch.setattr(PortfolioStore, "_instance", portfolio)
    monkeypatch.setattr(KillswitchStore, "_instance", KillswitchStore(tmp_path / "state" / "killswitch_state.json"))
    monkeypatch.setattr(CalibrationLog, "_instance", None)
    CalibrationLog.instance(tmp_path / "state" / "calibration")
    text = trigger_killswitch("LIQUIDATION_CASCADE", "CASCADE_DOWN")
    snapshot = portfolio.get_snapshot()
    events = CalibrationLog.instance().read_events(_utc_today())
    assert "KILLSWITCH" in text
    assert all(cat.orchestrator_action == "KILLSWITCH" for cat in snapshot.categories.values())
    assert any(event["event_type"] == "KILLSWITCH_TRIGGER" for event in events)
