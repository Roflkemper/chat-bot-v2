from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from services.decision_log.models import CapturedEvent, EventSeverity, EventType, MarketContext, PortfolioContext


@pytest.fixture
def load_fixture() -> callable:
    base = Path(__file__).parent / "fixtures"

    def _loader(name: str) -> dict:
        return json.loads((base / name).read_text(encoding="utf-8"))

    return _loader


@pytest.fixture
def sample_market_context() -> MarketContext:
    return MarketContext(
        price_btc=76520.0,
        regime_label="trend_up",
        regime_modifiers=["ny_am_active"],
        rsi_1h=58.0,
        rsi_5m=61.0,
        price_change_5m_pct=0.6,
        price_change_1h_pct=2.3,
        atr_normalized=0.012,
        session_kz="NY_AM",
        nearest_liq_above=77000.0,
        nearest_liq_below=75800.0,
    )


@pytest.fixture
def sample_portfolio_context() -> PortfolioContext:
    return PortfolioContext(
        depo_total=15000.0,
        shorts_unrealized_usd=-420.0,
        longs_unrealized_usd=0.0,
        net_unrealized_usd=-420.0,
        free_margin_pct=28.0,
        drawdown_pct=8.3,
        shorts_position_btc=0.45,
        longs_position_usd=0.0,
    )


@pytest.fixture
def sample_event(sample_market_context: MarketContext, sample_portfolio_context: PortfolioContext) -> CapturedEvent:
    return CapturedEvent(
        event_id="evt-20260430-0001",
        ts=datetime(2026, 4, 30, 12, 0, tzinfo=timezone.utc),
        event_type=EventType.PARAM_CHANGE,
        severity=EventSeverity.WARNING,
        bot_id="TEST_2",
        summary="Изменение параметров бота TEST_2",
        payload={"field": "target", "old": "0.21", "new": "0.30"},
        market_context=sample_market_context,
        portfolio_context=sample_portfolio_context,
    )
