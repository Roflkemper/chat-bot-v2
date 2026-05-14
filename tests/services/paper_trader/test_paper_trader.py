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


def test_multi_symbol_prices_dict(tmp_path: Path) -> None:
    """Multi-symbol support 2026-05-08: update_open_trades accepts a dict of
    pair->price. Each trade is matched to its pair's price; trades for pairs
    missing from the dict are skipped (no false TP/SL)."""
    journal.JOURNAL_PATH = tmp_path / "j.jsonl"
    btc_setup = _make_long_setup(entry=80000, sl=79500, tp1=80500, tp2=81000)
    eth_setup = _make_long_setup(entry=3000, sl=2950, tp1=3050, tp2=3100)
    # Patch ETH setup pair (factory defaults to BTCUSDT)
    eth_setup_dict = eth_setup.__dict__
    eth_setup_dict["pair"] = "ETHUSDT"

    trader.open_paper_trade(btc_setup)
    trader.open_paper_trade(eth_setup)

    # Multi-symbol prices: BTC at TP1, ETH at SL.
    closes = trader.update_open_trades({"BTCUSDT": 80500.0, "ETHUSDT": 2950.0})
    actions = sorted(c["action"] for c in closes)
    assert actions == ["SL", "TP1"]
    # BTC trade hit TP1 -> +pnl; ETH trade hit SL -> -pnl.
    btc_close = next(c for c in closes if c["action"] == "TP1")
    eth_close = next(c for c in closes if c["action"] == "SL")
    assert btc_close["realized_pnl_usd"] > 0
    assert eth_close["realized_pnl_usd"] < 0


def test_multi_symbol_skips_missing_pair(tmp_path: Path) -> None:
    """Trade for pair not in price dict must NOT close (no false TP/SL)."""
    journal.JOURNAL_PATH = tmp_path / "j.jsonl"
    eth_setup = _make_long_setup(entry=3000, sl=2950, tp1=3050, tp2=3100)
    eth_setup.__dict__["pair"] = "ETHUSDT"
    trader.open_paper_trade(eth_setup)
    # Only BTC price provided — ETH trade should be left alone even if BTC
    # price would coincidentally hit ETH's TP1.
    closes = trader.update_open_trades({"BTCUSDT": 3050.0})
    assert closes == []


def test_tp1_does_not_re_emit_on_subsequent_polls(tmp_path: Path) -> None:
    """Regression: prod (2026-05-08) shipped 5 duplicate TP1 alerts in 5 minutes
    because journal.open_trades() left the trade in by_id after TP1 — so the
    next poll cycle saw it as still-open and emitted TP1 again. open_trades()
    must remove the trade on TP1 (v0.1 treats TP1 as full close)."""
    journal.JOURNAL_PATH = tmp_path / "j.jsonl"
    setup = _make_long_setup(entry=80000, sl=79500, tp1=80500, tp2=81000)
    trader.open_paper_trade(setup)
    first = trader.update_open_trades(80500.0)
    assert len(first) == 1
    assert first[0]["action"] == "TP1"

    # Second poll at the same TP1 price must not re-emit.
    second = trader.update_open_trades(80500.0)
    assert len(second) == 0, "TP1 should fire only once; trade is closed afterwards"

    # Third poll at a different price (TP2 territory) — also no re-emit.
    third = trader.update_open_trades(81000.0)
    assert len(third) == 0


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


def test_p15_trades_skipped_by_update_loop(tmp_path: Path) -> None:
    """Regression 2026-05-11: P-15 trades have no sl/tp1/tp2 (they're managed
    by P-15 state machine, not SL/TP levels). update_open_trades must skip
    them. Was throwing KeyError: 'sl' every loop tick."""
    journal.JOURNAL_PATH = tmp_path / "j.jsonl"
    # Write a P-15 trade record directly into the journal (the P-15 handler
    # uses a different open path).
    p15_record = {
        "ts": "2026-05-10T22:00:00Z",
        "trade_id": "p15-long-test",
        "strategy": "p15",
        "setup_type": "p15_long_open",
        "side": "long",
        "pair": "BTCUSDT",
        "action": "OPEN",
        "stage": "OPEN",
        "p15_layer": 1,
        "p15_avg_entry": 80000.0,
        # No sl / tp1 / tp2 / time_stop_at — would crash old code.
    }
    journal.JOURNAL_PATH.write_text(json.dumps(p15_record) + "\n", encoding="utf-8")

    # Should not raise.
    closes = trader.update_open_trades(80500.0)
    # Nothing closed — P-15 is managed elsewhere.
    assert closes == []
