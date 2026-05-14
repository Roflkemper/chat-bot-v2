from __future__ import annotations

from datetime import datetime, timezone

import pytest

from services.setup_detector.models import SetupBasis, SetupType, make_setup
from services.setup_detector.telegram_card import format_telegram_card, format_outcome_card


def _make_long_setup() -> object:
    return make_setup(
        setup_type=SetupType.LONG_DUMP_REVERSAL,
        pair="BTCUSDT",
        current_price=80000.0,
        regime_label="consolidation",
        session_label="NY_AM",
        entry_price=79760.0,
        stop_price=79000.0,
        tp1_price=80520.0,
        tp2_price=81280.0,
        risk_reward=1.0,
        strength=8,
        confidence_pct=72.0,
        basis=(
            SetupBasis("Дамп -3.1% за 4ч", -3.1, 1.0),
            SetupBasis("RSI 1h = 29 (перепродан)", 29.0, 1.0),
            SetupBasis("Разворотные свечи (4/10 pin bars)", 4, 0.8),
        ),
        cancel_conditions=("RSI 1h > 50", "Новый минимум ниже стопа"),
        window_minutes=120,
        portfolio_impact_note="P-7: добавляет к лонгам",
        recommended_size_btc=0.05,
        detected_at=datetime(2026, 4, 30, 10, 0, 0, tzinfo=timezone.utc),
    )


def _make_grid_setup() -> object:
    return make_setup(
        setup_type=SetupType.GRID_BOOSTER_ACTIVATE,
        pair="BTCUSDT",
        current_price=80000.0,
        regime_label="range_wide",
        session_label="NONE",
        grid_action="activate_booster",
        grid_target_bots=("Bot 6399265299",),
        strength=7,
        confidence_pct=68.0,
        basis=(SetupBasis("RSI 1h = 31", 31.0, 1.0),),
        cancel_conditions=("Режим сменился",),
        window_minutes=90,
        portfolio_impact_note="P-16: буст-бот",
        recommended_size_btc=0.0,
        detected_at=datetime(2026, 4, 30, 10, 0, 0, tzinfo=timezone.utc),
    )


def test_long_card_format() -> None:
    setup = _make_long_setup()
    card = format_telegram_card(setup)  # type: ignore[arg-type]
    assert "LONG" in card
    assert "BTCUSDT" in card
    assert "Сила:" in card
    assert "ВХОД:" in card
    assert "СТОП:" in card
    assert "ЦЕЛИ:" in card


def test_short_card_format() -> None:
    setup = make_setup(
        setup_type=SetupType.SHORT_RALLY_FADE,
        pair="BTCUSDT",
        current_price=82000.0,
        regime_label="consolidation",
        session_label="LONDON",
        entry_price=82246.0,
        stop_price=82820.0,
        tp1_price=81672.0,
        tp2_price=81098.0,
        risk_reward=1.0,
        strength=7,
        confidence_pct=65.0,
        basis=(SetupBasis("Ралли +3%", 3.0, 1.0),),
        cancel_conditions=("RSI < 50",),
        window_minutes=120,
        portfolio_impact_note="P-1: шорт",
        recommended_size_btc=0.05,
        detected_at=datetime(2026, 4, 30, 10, 0, 0, tzinfo=timezone.utc),
    )
    card = format_telegram_card(setup)
    assert "SHORT" in card
    assert "BTCUSDT" in card


def test_grid_card_format() -> None:
    setup = _make_grid_setup()
    card = format_telegram_card(setup)  # type: ignore[arg-type]
    assert "GRID" in card
    assert "Bot 6399265299" in card
    assert "activate_booster" in card


def test_card_under_25_lines() -> None:
    setup = _make_long_setup()
    card = format_telegram_card(setup)  # type: ignore[arg-type]
    lines = card.strip().split("\n")
    assert len(lines) <= 25, f"Card has {len(lines)} lines, expected ≤25:\n{card}"


def test_outcome_card_tp1_format() -> None:
    setup = _make_long_setup()
    card = format_outcome_card(
        setup,  # type: ignore[arg-type]
        new_status="tp1_hit",
        current_price=80520.0,
        hypothetical_pnl_usd=38.0,
        time_to_outcome_min=47,
    )
    assert "TP1 HIT" in card
    assert "+38" in card or "38" in card
    assert "47" in card
