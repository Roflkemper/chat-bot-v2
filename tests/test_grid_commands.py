from __future__ import annotations

from models.responses import BotResponsePayload
from handlers.command_actions import CommandActionContext, CommandActions
from core.orchestrator.portfolio_state import PortfolioStore


def _ctx(command: str) -> CommandActionContext:
    return CommandActionContext(
        command=command,
        timeframe="1h",
        snapshot_loader=lambda tf: None,
    )


def _fake_regime_snapshot():
    return {
        "regime": {
            "primary": "RANGE",
            "modifiers": [],
            "age_bars": 50,
            "bias_score": 24,
            "session": "US",
            "metrics": {
                "atr_pct_1h": 0.9,
                "atr_pct_4h": 1.2,
                "atr_pct_5m": 0.15,
                "adx_1h": 18,
                "bb_width_pct_1h": 1.2,
                "dist_to_ema200_pct": 0.3,
                "ema_stack_1h": 1,
                "last_move_pct_5m": 0.02,
                "last_move_pct_15m": -0.08,
                "last_move_pct_1h": 0.15,
                "last_move_pct_4h": -0.30,
                "volume_ratio_24h": 1.15,
                "funding_rate": 0.008,
            },
        }
    }


def test_cmd_portfolio_returns_text(tmp_path, monkeypatch):
    store = PortfolioStore(str(tmp_path / "state" / "grid_portfolio.json"))
    monkeypatch.setattr(PortfolioStore, "_instance", store)
    monkeypatch.setattr("core.pipeline.build_full_snapshot", lambda symbol="BTCUSDT": _fake_regime_snapshot())
    payload = CommandActions(_ctx("/portfolio")).portfolio()
    assert isinstance(payload, BotResponsePayload)
    assert "ПОРТФЕЛЬ" in payload.text


def test_cmd_regime_returns_text(monkeypatch):
    monkeypatch.setattr("core.pipeline.build_full_snapshot", lambda symbol="BTCUSDT": _fake_regime_snapshot())
    payload = CommandActions(_ctx("/regime")).regime()
    assert "РЕЖИМ РЫНКА BTC" in payload.text


def test_cmd_category_valid_key(tmp_path, monkeypatch):
    store = PortfolioStore(str(tmp_path / "state" / "grid_portfolio.json"))
    monkeypatch.setattr(PortfolioStore, "_instance", store)
    payload = CommandActions(_ctx("/category btc_short")).category()
    assert "BTC ШОРТ" in payload.text


def test_cmd_category_invalid_key_returns_list(tmp_path, monkeypatch):
    store = PortfolioStore(str(tmp_path / "state" / "grid_portfolio.json"))
    monkeypatch.setattr(PortfolioStore, "_instance", store)
    payload = CommandActions(_ctx("/category missing")).category()
    assert "Доступные" in payload.text
    assert "btc_short" in payload.text


def test_cmd_category_missing_arg():
    payload = CommandActions(_ctx("/category")).category()
    assert "Использование" in payload.text


def test_cmd_bot_valid_key(tmp_path, monkeypatch):
    store = PortfolioStore(str(tmp_path / "state" / "grid_portfolio.json"))
    monkeypatch.setattr(PortfolioStore, "_instance", store)
    payload = CommandActions(_ctx("/bot btc_short_l1")).bot()
    assert "btc_short_l1" in payload.text


def test_cmd_bot_invalid_key(tmp_path, monkeypatch):
    store = PortfolioStore(str(tmp_path / "state" / "grid_portfolio.json"))
    monkeypatch.setattr(PortfolioStore, "_instance", store)
    payload = CommandActions(_ctx("/bot missing")).bot()
    assert "Доступные" in payload.text
    assert "btc_short_l1" in payload.text


def test_cmd_bot_missing_arg():
    payload = CommandActions(_ctx("/bot")).bot()
    assert "Использование" in payload.text
