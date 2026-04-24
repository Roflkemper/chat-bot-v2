"""Unit tests for portfolio alert rules."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from telegram_ui.portfolio.alerts import compute_alerts, liq_distance_pct
from telegram_ui.portfolio.data_source import BotData


def _bot(
    *,
    bot_id: str = "1",
    name: str = "BOT",
    alias: str = "BOT",
    status: str = "",
    side: str = "LONG",
    position: float = 0.0,
    profit_now: float = 0.0,
    profit_24h_ago: float = 0.0,
    current_profit: float = 0.0,
    in_filled_count: int = 10,
    in_filled_count_6h_ago: int = 5,
    trade_volume: float = 100.0,
    trade_volume_24h_ago: float = 0.0,
    balance: float = 1000.0,
    balance_24h_ago: float = 1000.0,
    average_price: float = 0.0,
    liquidation_price: float = 0.0,
    source: str = "csv",
) -> BotData:
    return BotData(
        bot_id=bot_id,
        name=name,
        alias=alias,
        status=status,
        side=side,
        position=position,
        profit_now=profit_now,
        profit_24h_ago=profit_24h_ago,
        current_profit=current_profit,
        in_filled_count=in_filled_count,
        in_filled_count_6h_ago=in_filled_count_6h_ago,
        trade_volume=trade_volume,
        trade_volume_24h_ago=trade_volume_24h_ago,
        balance=balance,
        balance_24h_ago=balance_24h_ago,
        average_price=average_price,
        liquidation_price=liquidation_price,
        ts_latest=datetime(2026, 4, 24, 12, 0, tzinfo=timezone.utc),
        source=source,
    )


class TestIdleAlert:
    def test_idle_when_fills_unchanged(self):
        b = _bot(in_filled_count=10, in_filled_count_6h_ago=10, source="csv")
        alerts = compute_alerts([b])
        assert any("Без сработок" in a for a in alerts)

    def test_not_idle_when_fills_grew(self):
        b = _bot(in_filled_count=15, in_filled_count_6h_ago=10, source="csv")
        alerts = compute_alerts([b])
        assert not any("Без сработок" in a for a in alerts)

    def test_idle_uses_alias_in_message(self):
        b = _bot(in_filled_count=10, in_filled_count_6h_ago=10, alias="MY_BOT")
        alerts = compute_alerts([b])
        assert any("MY_BOT" in a for a in alerts)

    def test_idle_not_checked_for_api_source(self):
        b = _bot(in_filled_count=10, in_filled_count_6h_ago=10, source="api")
        alerts = compute_alerts([b])
        assert not any("Без сработок" in a for a in alerts)


class TestDDAlert:
    def test_dd_above_threshold(self):
        b = _bot(balance=1000.0, current_profit=-40.0)  # 4% > 3.5%
        alerts = compute_alerts([b])
        assert any("DD" in a for a in alerts)

    def test_dd_well_below_threshold(self):
        b = _bot(balance=1000.0, current_profit=-30.0)  # 3% < 3.5%
        alerts = compute_alerts([b])
        assert not any("DD" in a for a in alerts)

    def test_dd_below_threshold_not_triggered(self):
        b = _bot(balance=1000.0, current_profit=-34.0)  # 3.4% < 3.5%
        alerts = compute_alerts([b])
        assert not any("DD" in a for a in alerts)

    def test_dd_positive_profit_no_alert(self):
        b = _bot(balance=1000.0, current_profit=50.0)
        alerts = compute_alerts([b])
        assert not any("DD" in a for a in alerts)

    def test_dd_zero_balance_no_alert(self):
        b = _bot(balance=0.0, current_profit=-100.0)
        alerts = compute_alerts([b])
        assert not any("DD" in a for a in alerts)


class TestLiquidationAlert:
    def test_liq_close_triggers_alert(self):
        # 10% distance — below 25% threshold
        b = _bot(position=-0.5, average_price=70000.0, liquidation_price=77000.0, side="SHORT")
        alerts = compute_alerts([b])
        assert any("ликвидации" in a for a in alerts)

    def test_liq_far_no_alert(self):
        # 30% distance — above 25% threshold
        b = _bot(position=-0.5, average_price=70000.0, liquidation_price=91000.0, side="SHORT")
        alerts = compute_alerts([b])
        assert not any("ликвидации" in a for a in alerts)

    def test_no_liq_when_position_zero(self):
        b = _bot(position=0.0, average_price=0.0, liquidation_price=93000.0)
        alerts = compute_alerts([b])
        assert not any("ликвидации" in a for a in alerts)

    def test_no_liq_when_liq_price_zero(self):
        b = _bot(position=-0.5, average_price=70000.0, liquidation_price=0.0)
        alerts = compute_alerts([b])
        assert not any("ликвидации" in a for a in alerts)


class TestFailedAlert:
    def test_failed_status_triggers_alert(self):
        b = _bot(status="failed")
        alerts = compute_alerts([b])
        assert any("Failed" in a for a in alerts)

    def test_error_status_triggers_alert(self):
        b = _bot(status="error")
        alerts = compute_alerts([b])
        assert any("Failed" in a for a in alerts)

    def test_active_status_no_alert(self):
        b = _bot(status="active")
        alerts = compute_alerts([b])
        assert not any("Failed" in a for a in alerts)

    def test_empty_status_no_failed_alert(self):
        b = _bot(status="")
        alerts = compute_alerts([b])
        assert not any("Failed" in a for a in alerts)


class TestNoAlerts:
    def test_clean_bot_no_alerts(self):
        b = _bot(
            in_filled_count=15,
            in_filled_count_6h_ago=10,
            balance=1000.0,
            current_profit=5.0,
            position=0.0,
            status="active",
        )
        alerts = compute_alerts([b])
        assert alerts == []

    def test_empty_bot_list(self):
        alerts = compute_alerts([])
        assert alerts == []


class TestLiqDistancePct:
    def test_short_position_correct(self):
        b = _bot(position=-0.5, average_price=70000.0, liquidation_price=84000.0)
        dist = liq_distance_pct(b)
        assert dist == pytest.approx(20.0, rel=1e-3)

    def test_long_position_correct(self):
        b = _bot(position=0.5, average_price=70000.0, liquidation_price=56000.0)
        dist = liq_distance_pct(b)
        assert dist == pytest.approx(20.0, rel=1e-3)

    def test_none_when_position_zero(self):
        b = _bot(position=0.0)
        assert liq_distance_pct(b) is None

    def test_none_when_avg_price_zero(self):
        b = _bot(position=-0.5, average_price=0.0, liquidation_price=90000.0)
        assert liq_distance_pct(b) is None

    def test_none_when_liq_price_zero(self):
        b = _bot(position=-0.5, average_price=70000.0, liquidation_price=0.0)
        assert liq_distance_pct(b) is None
