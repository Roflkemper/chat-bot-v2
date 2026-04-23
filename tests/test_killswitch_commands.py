from __future__ import annotations

from handlers.command_actions import CommandActionContext, CommandActions
from core.orchestrator.killswitch import KillswitchStore
from core.orchestrator.portfolio_state import PortfolioStore


def _ctx(command: str) -> CommandActionContext:
    return CommandActionContext(command=command, timeframe="1h", snapshot_loader=lambda tf: None)


def test_killswitch_on_activates_manual(tmp_path, monkeypatch):
    monkeypatch.setattr(PortfolioStore, "_instance", PortfolioStore(str(tmp_path / "state" / "grid_portfolio.json")))
    monkeypatch.setattr(KillswitchStore, "_instance", KillswitchStore(tmp_path / "state" / "killswitch_state.json"))
    payload = CommandActions(_ctx("/killswitch on test")).killswitch()
    assert "KILLSWITCH" in payload.text
    assert KillswitchStore.instance().is_active() is True


def test_killswitch_off_disables_active(tmp_path, monkeypatch):
    monkeypatch.setattr(PortfolioStore, "_instance", PortfolioStore(str(tmp_path / "state" / "grid_portfolio.json")))
    monkeypatch.setattr(KillswitchStore, "_instance", KillswitchStore(tmp_path / "state" / "killswitch_state.json"))
    CommandActions(_ctx("/killswitch on test")).killswitch()
    payload = CommandActions(_ctx("/killswitch off")).killswitch()
    assert "ОТКЛЮЧЁН" in payload.text
    assert KillswitchStore.instance().is_active() is False


def test_killswitch_status_shows_history(tmp_path, monkeypatch):
    monkeypatch.setattr(KillswitchStore, "_instance", KillswitchStore(tmp_path / "state" / "killswitch_state.json"))
    store = KillswitchStore.instance()
    store.trigger("MANUAL", "operator")
    store.disable(operator="tester")
    payload = CommandActions(_ctx("/killswitch status")).killswitch_status()
    assert "История" in payload.text


def test_apply_blocked_when_killswitch_active(tmp_path, monkeypatch):
    monkeypatch.setattr(PortfolioStore, "_instance", PortfolioStore(str(tmp_path / "state" / "grid_portfolio.json")))
    monkeypatch.setattr(KillswitchStore, "_instance", KillswitchStore(tmp_path / "state" / "killswitch_state.json"))
    KillswitchStore.instance().trigger("MANUAL", "operator")
    payload = CommandActions(_ctx("/apply")).apply()
    assert "KILLSWITCH АКТИВЕН" in payload.text
