"""Integration tests for /portfolio command with mock data source."""
from __future__ import annotations

import csv
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from telegram_ui.portfolio.command import handle_portfolio_command
from telegram_ui.portfolio.data_source import BotData, _infer_side, _parse_ts, load_portfolio_data


# ── fixtures ──────────────────────────────────────────────────────────────────

def _make_csv(tmp_path: Path, rows: list[dict]) -> Path:
    """Write rows to a snapshots.csv file and return its path."""
    if not rows:
        return tmp_path / "snapshots.csv"
    fieldnames = list(rows[0].keys())
    p = tmp_path / "snapshots.csv"
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    return p


def _row(
    ts_utc: str,
    bot_id: str = "1",
    bot_name: str = "BOT",
    alias: str = "",
    status: str = "",
    position: str = "0",
    profit: str = "100.0",
    current_profit: str = "5.0",
    in_filled_count: str = "10",
    in_filled_qty: str = "",
    out_filled_count: str = "5",
    out_filled_qty: str = "",
    trigger_count: str = "0",
    trigger_qty: str = "",
    average_price: str = "0",
    trade_volume: str = "50000",
    balance: str = "10000",
    liquidation_price: str = "0",
    stat_updated_at: str = "",
    schema_version: str = "2",
) -> dict:
    return {
        "ts_utc": ts_utc,
        "bot_id": bot_id,
        "bot_name": bot_name,
        "alias": alias,
        "status": status,
        "position": position,
        "profit": profit,
        "current_profit": current_profit,
        "in_filled_count": in_filled_count,
        "in_filled_qty": in_filled_qty,
        "out_filled_count": out_filled_count,
        "out_filled_qty": out_filled_qty,
        "trigger_count": trigger_count,
        "trigger_qty": trigger_qty,
        "average_price": average_price,
        "trade_volume": trade_volume,
        "balance": balance,
        "liquidation_price": liquidation_price,
        "stat_updated_at": stat_updated_at,
        "schema_version": schema_version,
    }


# ── data_source tests ─────────────────────────────────────────────────────────

class TestLoadFromCsv:
    def test_returns_bots_from_fresh_csv(self, tmp_path):
        now = datetime.now(timezone.utc)
        ts = now.isoformat(timespec="seconds")
        ts_old = (now - timedelta(hours=25)).isoformat(timespec="seconds")

        csv_path = _make_csv(tmp_path, [
            _row(ts_old, bot_id="1", bot_name="BOT_A", profit="80.0", trade_volume="40000"),
            _row(ts, bot_id="1", bot_name="BOT_A", profit="100.0", trade_volume="50000"),
        ])

        with patch("telegram_ui.portfolio.data_source.SNAPSHOTS_CSV", csv_path), \
             patch("telegram_ui.portfolio.data_source.BOT_ALIASES_JSON", tmp_path / "aliases.json"):
            bots = load_portfolio_data()

        assert len(bots) == 1
        assert bots[0].bot_id == "1"
        assert bots[0].profit_now == pytest.approx(100.0)

    def test_pnl_24h_delta_computed(self, tmp_path):
        now = datetime.now(timezone.utc)
        ts_now = now.isoformat(timespec="seconds")
        ts_24h = (now - timedelta(hours=24)).isoformat(timespec="seconds")

        csv_path = _make_csv(tmp_path, [
            _row(ts_24h, bot_id="1", profit="80.0", trade_volume="40000"),
            _row(ts_now, bot_id="1", profit="100.0", trade_volume="50000"),
        ])

        with patch("telegram_ui.portfolio.data_source.SNAPSHOTS_CSV", csv_path), \
             patch("telegram_ui.portfolio.data_source.BOT_ALIASES_JSON", tmp_path / "aliases.json"):
            bots = load_portfolio_data()

        assert bots[0].profit_24h_ago == pytest.approx(80.0)
        pnl = bots[0].profit_now - bots[0].profit_24h_ago
        assert pnl == pytest.approx(20.0)

    def test_volume_24h_delta_computed(self, tmp_path):
        now = datetime.now(timezone.utc)
        ts_now = now.isoformat(timespec="seconds")
        ts_24h = (now - timedelta(hours=24)).isoformat(timespec="seconds")

        csv_path = _make_csv(tmp_path, [
            _row(ts_24h, bot_id="1", trade_volume="40000"),
            _row(ts_now, bot_id="1", trade_volume="50000"),
        ])

        with patch("telegram_ui.portfolio.data_source.SNAPSHOTS_CSV", csv_path), \
             patch("telegram_ui.portfolio.data_source.BOT_ALIASES_JSON", tmp_path / "aliases.json"):
            bots = load_portfolio_data()

        vol_delta = bots[0].trade_volume - bots[0].trade_volume_24h_ago
        assert vol_delta == pytest.approx(10000.0)

    def test_stale_csv_returns_none(self, tmp_path):
        old_ts = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(timespec="seconds")
        csv_path = _make_csv(tmp_path, [_row(old_ts, bot_id="1")])

        with patch("telegram_ui.portfolio.data_source.SNAPSHOTS_CSV", csv_path), \
             patch("telegram_ui.portfolio.data_source.BOT_ALIASES_JSON", tmp_path / "aliases.json"), \
             patch("telegram_ui.portfolio.data_source._load_from_api", return_value=[]) as mock_api:
            bots = load_portfolio_data()

        mock_api.assert_called_once()

    def test_missing_csv_falls_back_to_api(self, tmp_path):
        missing = tmp_path / "no_such_file.csv"
        with patch("telegram_ui.portfolio.data_source.SNAPSHOTS_CSV", missing), \
             patch("telegram_ui.portfolio.data_source._load_from_api", return_value=[]) as mock_api:
            load_portfolio_data()

        mock_api.assert_called_once()

    def test_multiple_bots(self, tmp_path):
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        csv_path = _make_csv(tmp_path, [
            _row(now, bot_id="1", bot_name="BOT_A"),
            _row(now, bot_id="2", bot_name="BOT_B"),
            _row(now, bot_id="3", bot_name="BOT_C"),
        ])

        with patch("telegram_ui.portfolio.data_source.SNAPSHOTS_CSV", csv_path), \
             patch("telegram_ui.portfolio.data_source.BOT_ALIASES_JSON", tmp_path / "aliases.json"):
            bots = load_portfolio_data()

        assert len(bots) == 3

    def test_alias_applied_from_json(self, tmp_path):
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        csv_path = _make_csv(tmp_path, [_row(now, bot_id="42", bot_name="RAW_NAME")])
        aliases_path = tmp_path / "aliases.json"
        aliases_path.write_text(json.dumps({"42": "NICE_ALIAS"}), encoding="utf-8")

        with patch("telegram_ui.portfolio.data_source.SNAPSHOTS_CSV", csv_path), \
             patch("telegram_ui.portfolio.data_source.BOT_ALIASES_JSON", aliases_path):
            bots = load_portfolio_data()

        assert bots[0].alias == "NICE_ALIAS"

    def test_side_inferred_short_from_position(self, tmp_path):
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        csv_path = _make_csv(tmp_path, [_row(now, bot_id="1", position="-0.5")])

        with patch("telegram_ui.portfolio.data_source.SNAPSHOTS_CSV", csv_path), \
             patch("telegram_ui.portfolio.data_source.BOT_ALIASES_JSON", tmp_path / "aliases.json"):
            bots = load_portfolio_data()

        assert bots[0].side == "SHORT"

    def test_side_inferred_long_from_position(self, tmp_path):
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        csv_path = _make_csv(tmp_path, [_row(now, bot_id="1", position="0.5")])

        with patch("telegram_ui.portfolio.data_source.SNAPSHOTS_CSV", csv_path), \
             patch("telegram_ui.portfolio.data_source.BOT_ALIASES_JSON", tmp_path / "aliases.json"):
            bots = load_portfolio_data()

        assert bots[0].side == "LONG"


class TestInferSide:
    def test_negative_position_is_short(self):
        assert _infer_side(-0.5, "BOT") == "SHORT"

    def test_positive_position_is_long(self):
        assert _infer_side(0.5, "BOT") == "LONG"

    def test_zero_position_short_name(self):
        assert _infer_side(0.0, "BTC-SHORT-BOT") == "SHORT"

    def test_zero_position_long_name(self):
        assert _infer_side(0.0, "BTC-LONG-BOT") == "LONG"

    def test_zero_position_cyrillic_short(self):
        assert _infer_side(0.0, "XRP ШОРТ") == "SHORT"

    def test_zero_position_cyrillic_long(self):
        assert _infer_side(0.0, "BTC ЛОНГ") == "LONG"

    def test_zero_position_unknown(self):
        assert _infer_side(0.0, "SOME_BOT") == "?"


class TestParseTs:
    def test_iso_with_offset(self):
        ts = _parse_ts("2026-04-23T23:03:36+00:00")
        assert ts is not None
        assert ts.year == 2026
        assert ts.month == 4
        assert ts.tzinfo is not None

    def test_empty_string_returns_none(self):
        assert _parse_ts("") is None

    def test_invalid_returns_none(self):
        assert _parse_ts("not-a-date") is None


# ── command integration ───────────────────────────────────────────────────────

class TestHandlePortfolioCommand:
    def test_returns_string(self):
        mock_bots = [
            BotData(
                bot_id="1", name="BOT_A", alias="BOT_A", status="",
                side="SHORT", position=-0.5,
                profit_now=100.0, profit_24h_ago=80.0,
                current_profit=5.0,
                in_filled_count=10, in_filled_count_6h_ago=8,
                trade_volume=50000.0, trade_volume_24h_ago=30000.0,
                balance=10000.0, balance_24h_ago=9800.0,
                average_price=70000.0, liquidation_price=85000.0,
                ts_latest=datetime.now(timezone.utc),
                source="csv",
            )
        ]
        with patch("telegram_ui.portfolio.command.load_portfolio_data", return_value=mock_bots):
            result = handle_portfolio_command()

        assert isinstance(result, str)
        assert len(result) > 0

    def test_contains_bot_name(self):
        mock_bots = [
            BotData(
                bot_id="1", name="MYBOT", alias="MY_ALIAS", status="",
                side="LONG", position=0.5,
                profit_now=100.0, profit_24h_ago=80.0,
                current_profit=5.0,
                in_filled_count=10, in_filled_count_6h_ago=8,
                trade_volume=50000.0, trade_volume_24h_ago=30000.0,
                balance=10000.0, balance_24h_ago=9800.0,
                average_price=70000.0, liquidation_price=55000.0,
                ts_latest=datetime.now(timezone.utc),
                source="csv",
            )
        ]
        with patch("telegram_ui.portfolio.command.load_portfolio_data", return_value=mock_bots):
            result = handle_portfolio_command()

        assert "MY_ALIAS" in result

    def test_empty_bots_returns_warning(self):
        with patch("telegram_ui.portfolio.command.load_portfolio_data", return_value=[]):
            result = handle_portfolio_command()

        assert "⚠️" in result

    def test_exception_returns_error_message(self):
        with patch("telegram_ui.portfolio.command.load_portfolio_data", side_effect=RuntimeError("boom")):
            result = handle_portfolio_command()

        assert "❌" in result

    def test_portfolio_header_present(self):
        mock_bots = [
            BotData(
                bot_id="1", name="BOT", alias="BOT", status="",
                side="?", position=0.0,
                profit_now=0.0, profit_24h_ago=0.0,
                current_profit=0.0,
                in_filled_count=0, in_filled_count_6h_ago=0,
                trade_volume=0.0, trade_volume_24h_ago=0.0,
                balance=0.0, balance_24h_ago=0.0,
                average_price=0.0, liquidation_price=0.0,
                ts_latest=datetime.now(timezone.utc),
                source="csv",
            )
        ]
        with patch("telegram_ui.portfolio.command.load_portfolio_data", return_value=mock_bots):
            result = handle_portfolio_command()

        assert "ПОРТФЕЛЬ GINAREA" in result
