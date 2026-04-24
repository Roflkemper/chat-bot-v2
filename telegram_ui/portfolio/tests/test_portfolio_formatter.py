"""Unit tests for portfolio formatter."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from telegram_ui.portfolio.data_source import BotData
from telegram_ui.portfolio.formatter import (
    _format_bot,
    _format_summary,
    _split_messages,
    format_portfolio,
)


def _bot(
    *,
    bot_id: str = "1",
    name: str = "BOT_NAME",
    alias: str = "",
    status: str = "",
    side: str = "LONG",
    position: float = 0.0,
    profit_now: float = 0.0,
    profit_24h_ago: float = 0.0,
    current_profit: float = 0.0,
    in_filled_count: int = 0,
    in_filled_count_6h_ago: int = 0,
    trade_volume: float = 0.0,
    trade_volume_24h_ago: float = 0.0,
    balance: float = 1000.0,
    balance_24h_ago: float = 990.0,
    average_price: float = 0.0,
    liquidation_price: float = 0.0,
    ts_latest: datetime | None = None,
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
        ts_latest=ts_latest or datetime(2026, 4, 24, 12, 0, tzinfo=timezone.utc),
        source=source,
    )


class TestFormatBot:
    def test_shows_alias_when_set(self):
        b = _bot(name="VERY_LONG_BOT_NAME_HERE", alias="MY_ALIAS")
        lines = _format_bot(b)
        assert "MY_ALIAS" in lines[0]
        assert "VERY_LONG_BOT_NAME_HERE" not in lines[0]

    def test_truncates_name_to_20_chars(self):
        b = _bot(name="A" * 30, alias="")
        lines = _format_bot(b)
        assert "A" * 30 not in lines[0]
        assert "A" * 20 in lines[0]

    def test_shows_side(self):
        b = _bot(side="SHORT")
        lines = _format_bot(b)
        assert "SHORT" in lines[0]

    def test_active_status_emoji(self):
        b = _bot(status="active")
        lines = _format_bot(b)
        assert "✅" in lines[0]

    def test_paused_status_emoji(self):
        b = _bot(status="paused")
        lines = _format_bot(b)
        assert "⏸" in lines[0]

    def test_unknown_status_shows_dash(self):
        b = _bot(status="")
        lines = _format_bot(b)
        assert "—" in lines[0]

    def test_pnl_positive(self):
        b = _bot(profit_now=100.0, profit_24h_ago=80.0)
        lines = _format_bot(b)
        assert "+$20.00" in lines[1]

    def test_pnl_negative(self):
        b = _bot(profit_now=80.0, profit_24h_ago=100.0)
        lines = _format_bot(b)
        # Negative PnL formatted as -$20.00 (minus before dollar sign)
        assert "-$20.00" in lines[1]

    def test_volume_24h(self):
        b = _bot(trade_volume=10000.0, trade_volume_24h_ago=6000.0)
        lines = _format_bot(b)
        assert "4,000" in lines[1]

    def test_position_open_shows_entry(self):
        b = _bot(position=-0.5, average_price=70000.0, side="SHORT")
        lines = _format_bot(b)
        assert "70,000" in "\n".join(lines)

    def test_position_zero_shows_no_position(self):
        b = _bot(position=0.0)
        lines = _format_bot(b)
        assert "нет позиции" in "\n".join(lines)

    def test_liquidation_distance_shown_when_applicable(self):
        b = _bot(position=-0.5, average_price=70000.0, liquidation_price=84000.0, side="SHORT")
        lines = _format_bot(b)
        assert "Liq" in "\n".join(lines)
        assert "20.0%" in "\n".join(lines)

    def test_liquidation_warning_emoji_when_close(self):
        b = _bot(position=-0.5, average_price=70000.0, liquidation_price=77000.0, side="SHORT")
        lines = _format_bot(b)
        full = "\n".join(lines)
        assert "🚨" in full

    def test_no_liquidation_when_position_zero(self):
        b = _bot(position=0.0, average_price=0.0, liquidation_price=93000.0)
        lines = _format_bot(b)
        assert "Liq" not in "\n".join(lines)


class TestFormatSummary:
    def test_balance_shown(self):
        bots = [_bot(balance=10000.0, balance_24h_ago=9000.0)]
        lines = _format_summary(bots)
        text = "\n".join(lines)
        assert "10,000" in text

    def test_balance_delta_positive(self):
        bots = [_bot(balance=10000.0, balance_24h_ago=9000.0)]
        lines = _format_summary(bots)
        text = "\n".join(lines)
        assert "+$1,000" in text

    def test_unrealized_shown(self):
        bots = [_bot(position=1.0, current_profit=50.0)]
        lines = _format_summary(bots)
        assert "+$50.00" in "\n".join(lines)

    def test_active_count(self):
        bots = [
            _bot(bot_id="1", position=1.0),
            _bot(bot_id="2", position=0.0),
            _bot(bot_id="3", position=-0.5),
        ]
        lines = _format_summary(bots)
        assert "2 / 3" in "\n".join(lines)

    def test_btc_balance_shown_separately(self):
        bots = [
            _bot(bot_id="1", balance=10000.0),
            _bot(bot_id="2", balance=0.05),
        ]
        lines = _format_summary(bots)
        text = "\n".join(lines)
        assert "BTC" in text


class TestSplitMessages:
    def test_short_text_not_split(self):
        text = "Hello world"
        parts = _split_messages(text, limit=100)
        assert len(parts) == 1
        assert parts[0] == text

    def test_long_text_split_at_newline(self):
        line = "A" * 50
        text = "\n".join([line] * 20)
        parts = _split_messages(text, limit=200)
        assert len(parts) > 1
        for part in parts:
            assert len(part) <= 200

    def test_all_content_preserved(self):
        line = "X" * 40
        text = "\n".join([line] * 30)
        parts = _split_messages(text, limit=200)
        rejoined = "\n".join(parts)
        for chunk in text.split("\n"):
            assert chunk in rejoined


class TestFormatPortfolio:
    def test_returns_list_of_strings(self):
        bots = [_bot()]
        result = format_portfolio(bots, [])
        assert isinstance(result, list)
        assert all(isinstance(s, str) for s in result)

    def test_header_present(self):
        bots = [_bot()]
        result = format_portfolio(bots, [])
        full = "\n".join(result)
        assert "ПОРТФЕЛЬ GINAREA" in full

    def test_alerts_shown(self):
        bots = [_bot()]
        alerts = ["  • Без сработок >6ч: BOT1"]
        result = format_portfolio(bots, alerts)
        full = "\n".join(result)
        assert "ВНИМАНИЕ" in full
        assert "BOT1" in full

    def test_no_alert_block_when_empty(self):
        bots = [_bot()]
        result = format_portfolio(bots, [])
        full = "\n".join(result)
        assert "ВНИМАНИЕ" not in full

    def test_bots_sorted_by_volume_desc(self):
        b1 = _bot(bot_id="1", alias="LOW_VOL", trade_volume=1000.0, trade_volume_24h_ago=0.0)
        b2 = _bot(bot_id="2", alias="HIGH_VOL", trade_volume=9000.0, trade_volume_24h_ago=0.0)
        result = format_portfolio([b1, b2], [])
        full = "\n".join(result)
        assert full.index("HIGH_VOL") < full.index("LOW_VOL")

    def test_timestamp_in_header(self):
        ts = datetime(2026, 4, 24, 12, 34, tzinfo=timezone.utc)
        bots = [_bot()]
        result = format_portfolio(bots, [], ts=ts)
        full = "\n".join(result)
        assert "24.04 12:34 UTC" in full
