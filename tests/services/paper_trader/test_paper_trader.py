"""Tests for paper_trader: journal + open/update + sizing + dedup."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from services.paper_trader import journal, trader
from services.setup_detector.models import SetupBasis, SetupType, make_setup


def _make_long_setup(*, conf=75.0, entry=80000, sl=79500, tp1=80500, tp2=81000):
    return make_setup(
        setup_type=SetupType.LONG_DOUBLE_BOTTOM,
        pair="BTCUSDT",
        current_price=entry,
        regime_label="RANGE",
        session_label="ny_am",
        entry_price=entry,
        stop_price=sl,
        tp1_price=tp1,
        tp2_price=tp2,
        risk_reward=1.0,
        strength=8,
        confidence_pct=conf,
        basis=(SetupBasis("test_label", 1.0, 0.5),),
        cancel_conditions=("test_cancel",),
    )


def _make_short_setup(*, conf=75.0, entry=80000, sl=80500, tp1=79500, tp2=79000):
    return make_setup(
        setup_type=SetupType.SHORT_DOUBLE_TOP,
        pair="BTCUSDT",
        current_price=entry,
        regime_label="RANGE",
        session_label="ny_am",
        entry_price=entry,
        stop_price=sl,
        tp1_price=tp1,
        tp2_price=tp2,
        risk_reward=1.0,
        strength=8,
        confidence_pct=conf,
        basis=(SetupBasis("test_label", 1.0, 0.5),),
        cancel_conditions=("test_cancel",),
    )


def test_open_paper_trade_long_above_threshold(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    journal.JOURNAL_PATH = tmp_path / "j.jsonl"
    setup = _make_long_setup(conf=75.0)
    record = trader.open_paper_trade(setup)
    assert record is not None
    assert record["side"] == "long"
    assert record["size_usd"] == 10000.0
    assert record["size_btc"] == round(10000 / 80000, 6)
    assert record["confidence_pct"] == 75.0
    # Journal has the OPEN event
    events = journal.read_all(path=tmp_path / "j.jsonl")
    assert len(events) == 1
    assert events[0]["action"] == "OPEN"


def test_open_paper_trade_below_threshold_filtered(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    journal.JOURNAL_PATH = tmp_path / "j.jsonl"
    setup = _make_long_setup(conf=55.0)
    assert trader.open_paper_trade(setup) is None


def test_grid_setup_not_papered(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    journal.JOURNAL_PATH = tmp_path / "j.jsonl"
    setup = make_setup(
        setup_type=SetupType.GRID_RAISE_BOUNDARY,
        pair="BTCUSDT", current_price=80000, regime_label="RANGE", session_label="ny_am",
        entry_price=80000, stop_price=79000, tp1_price=81000, tp2_price=82000,
        risk_reward=1.0, strength=8, confidence_pct=75.0,
        basis=(), cancel_conditions=(),
    )
    assert trader.open_paper_trade(setup) is None


def test_long_tp1_close(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    journal.JOURNAL_PATH = tmp_path / "j.jsonl"
    setup = _make_long_setup(entry=80000, sl=79500, tp1=80500, tp2=81000)
    trader.open_paper_trade(setup)
    closes = trader.update_open_trades(80500.0)
    assert len(closes) == 1
    assert closes[0]["action"] == "TP1"
    assert closes[0]["realized_pnl_usd"] > 0


def test_long_sl_close(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    journal.JOURNAL_PATH = tmp_path / "j.jsonl"
    setup = _make_long_setup(entry=80000, sl=79500, tp1=80500, tp2=81000)
    trader.open_paper_trade(setup)
    closes = trader.update_open_trades(79500.0)
    assert closes[0]["action"] == "SL"
    assert closes[0]["realized_pnl_usd"] < 0


def test_short_tp_close(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    journal.JOURNAL_PATH = tmp_path / "j.jsonl"
    setup = _make_short_setup(entry=80000, sl=80500, tp1=79500, tp2=79000)
    trader.open_paper_trade(setup)
    closes = trader.update_open_trades(79500.0)
    assert closes[0]["action"] == "TP1"
    assert closes[0]["realized_pnl_usd"] > 0


def test_short_sl_close(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    journal.JOURNAL_PATH = tmp_path / "j.jsonl"
    setup = _make_short_setup(entry=80000, sl=80500, tp1=79500, tp2=79000)
    trader.open_paper_trade(setup)
    closes = trader.update_open_trades(80500.0)
    assert closes[0]["action"] == "SL"
    assert closes[0]["realized_pnl_usd"] < 0


def test_time_stop_24h(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    journal.JOURNAL_PATH = tmp_path / "j.jsonl"
    setup = _make_long_setup(entry=80000, sl=79500, tp1=80500, tp2=81000)
    trader.open_paper_trade(setup)
    # Force time-stop check 25h later, price unchanged
    future = datetime.now(timezone.utc) + timedelta(hours=25)
    closes = trader.update_open_trades(80000.0, now=future)
    assert closes[0]["action"] == "EXPIRE"


def test_no_close_if_price_in_range(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    journal.JOURNAL_PATH = tmp_path / "j.jsonl"
    setup = _make_long_setup(entry=80000, sl=79500, tp1=80500, tp2=81000)
    trader.open_paper_trade(setup)
    closes = trader.update_open_trades(80100.0)
    assert closes == []


def test_daily_summary_stats(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    journal.JOURNAL_PATH = tmp_path / "j.jsonl"
    setup1 = _make_long_setup(entry=80000, sl=79500, tp1=80500, tp2=81000)
    setup2 = _make_long_setup(entry=80100, sl=79600, tp1=80600, tp2=81100)
    trader.open_paper_trade(setup1)
    trader.open_paper_trade(setup2)
    trader.update_open_trades(80500.0)  # first hits TP1
    trader.update_open_trades(79600.0)  # second hits SL

    summary = trader.daily_summary(days_back=1)
    assert summary["n_opens"] == 2
    assert summary["n_closes"] == 2
    assert summary["n_wins"] == 1
    assert summary["n_losses"] == 1
    assert summary["net_pnl_usd"] != 0
