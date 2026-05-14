from __future__ import annotations

from datetime import datetime, timezone

from core.orchestrator.portfolio_state import PortfolioStore
from renderers.grid_renderer import (
    render_bot,
    render_category,
    render_portfolio,
    render_regime_details,
)


def _portfolio(tmp_path):
    return PortfolioStore(str(tmp_path / "state" / "grid_portfolio.json")).get_snapshot()


def _regime():
    return {
        "primary": "RANGE",
        "modifiers": [],
        "age_bars": 50,
        "bias_score": 24,
        "session": "US",
        "ts": datetime(2026, 4, 17, 14, 23, tzinfo=timezone.utc),
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


def test_render_portfolio_no_crash(tmp_path):
    text = render_portfolio(_portfolio(tmp_path), _regime())
    assert text


def test_render_portfolio_shows_category_names(tmp_path):
    text = render_portfolio(_portfolio(tmp_path), _regime())
    assert "BTC ШОРТ" in text
    assert "BTC ЛОНГ" in text


def test_render_portfolio_shows_bot_states(tmp_path):
    text = render_portfolio(_portfolio(tmp_path), _regime())
    assert "btc_short_l1" in text
    assert "🟢 работает" in text


def test_render_portfolio_includes_regime_block(tmp_path):
    text = render_portfolio(_portfolio(tmp_path), _regime())
    assert "РЫНОК BTC" in text
    assert "Биас:" in text
    assert "━━━━━" in text


def test_render_regime_details_all_metrics_present():
    text = render_regime_details(_regime())
    assert "ATR 1ч" in text
    assert "BB ширина" in text
    assert "EMA-СТЕК" in text


def test_render_regime_details_with_modifiers():
    regime = _regime()
    regime["modifiers"] = ["WEEKEND_LOW_VOL"]
    text = render_regime_details(regime)
    assert "ВЫХОДНЫЕ" in text


def test_render_category_with_bots(tmp_path):
    store = PortfolioStore(str(tmp_path / "state" / "grid_portfolio.json"))
    category = store.get_category("btc_short")
    bots = store.get_bots_in_category("btc_short")
    text = render_category(category, bots)
    assert "БОТЫ В КАТЕГОРИИ (1)" in text
    assert "GRID_L1" in text


def test_render_category_empty(tmp_path):
    store = PortfolioStore(str(tmp_path / "state" / "grid_portfolio.json"))
    category = store.get_category("btc_long")
    text = render_category(category, [])
    assert "(боты не настроены)" in text


def test_render_bot_complete(tmp_path):
    store = PortfolioStore(str(tmp_path / "state" / "grid_portfolio.json"))
    bot = store.get_bot("btc_short_l1")
    category = store.get_category(bot.category)
    text = render_bot(bot, category)
    assert "ДЕЙСТВИЕ КАТЕГОРИИ" in text
    assert "Kill-switch:" in text


def test_render_escapes_russian_correctly(tmp_path):
    text = render_portfolio(_portfolio(tmp_path), _regime())
    assert "ПОРТФЕЛЬ" in text
    assert "Маржа:" in text
    assert "░" in text or "█" in text
