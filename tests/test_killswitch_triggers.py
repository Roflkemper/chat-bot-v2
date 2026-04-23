from __future__ import annotations

from core.orchestrator.killswitch_triggers import (
    check_cascade_trigger,
    check_flash_move_trigger,
    check_margin_drawdown_trigger,
)
from core.orchestrator.portfolio_state import Bot, PortfolioStore


def test_margin_drawdown_trigger_calls_killswitch(tmp_path, monkeypatch):
    store = PortfolioStore(str(tmp_path / "state" / "grid_portfolio.json"))
    store.add_bot(Bot(key="btc_long_a", category="btc_long", label="a", strategy_type="GRID_L1", stage="LIVE", balance_usd=8200))
    monkeypatch.setattr(PortfolioStore, "_instance", store)
    called = {}
    monkeypatch.setattr("core.orchestrator.killswitch_triggers.trigger_killswitch", lambda reason, reason_value: called.update(reason=reason, reason_value=reason_value))
    check_margin_drawdown_trigger(initial_balance_usd=10_000, threshold_pct=15.0)
    assert called["reason"] == "MARGIN_DRAWDOWN"


def test_margin_drawdown_trigger_skips_zero_balance(tmp_path, monkeypatch):
    store = PortfolioStore(str(tmp_path / "state" / "grid_portfolio.json"))
    monkeypatch.setattr(PortfolioStore, "_instance", store)
    called = {}
    monkeypatch.setattr("core.orchestrator.killswitch_triggers.trigger_killswitch", lambda reason, reason_value: called.update(reason=reason))
    check_margin_drawdown_trigger(initial_balance_usd=10_000, threshold_pct=15.0)
    assert called == {}


def test_cascade_trigger_calls_killswitch(monkeypatch):
    monkeypatch.setattr(
        "core.orchestrator.killswitch_triggers.build_full_snapshot",
        lambda symbol="BTCUSDT": {"regime": {"primary": "CASCADE_DOWN", "modifiers": ["LIQUIDATION_CASCADE", "X"]}},
    )
    called = {}
    monkeypatch.setattr("core.orchestrator.killswitch_triggers.trigger_killswitch", lambda reason, reason_value: called.update(reason=reason, reason_value=reason_value))
    check_cascade_trigger()
    assert called["reason"] == "LIQUIDATION_CASCADE"
    assert called["reason_value"] == "CASCADE_DOWN"


def test_flash_move_trigger_calls_killswitch(monkeypatch):
    called = {}
    monkeypatch.setattr("core.orchestrator.killswitch_triggers.trigger_killswitch", lambda reason, reason_value: called.update(reason=reason, reason_value=reason_value))
    check_flash_move_trigger(price_now=95, price_1m_ago=100, threshold_pct=5.0)
    assert called["reason"] == "FLASH_MOVE"


def test_flash_move_trigger_skips_zero_reference(monkeypatch):
    called = {}
    monkeypatch.setattr("core.orchestrator.killswitch_triggers.trigger_killswitch", lambda reason, reason_value: called.update(reason=reason))
    check_flash_move_trigger(price_now=95, price_1m_ago=0, threshold_pct=5.0)
    assert called == {}
