"""Unit tests for services.pre_cascade_alert.loop."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from services.pre_cascade_alert import loop as pca


def _btc_data(*, oi_pct: float, funding: float, ls: float, taker_ratio: float = 1.0,
              top_ls: float = 1.0, mark: float = 80000.0) -> dict:
    return {
        "BTCUSDT": {
            "oi_change_1h_pct": oi_pct,
            "funding_rate_8h": funding,
            "global_ls_ratio": ls,
            "taker_buy_sell_ratio": taker_ratio,
            "top_trader_ls_ratio": top_ls,
            "mark_price": mark,
        }
    }


def test_evaluate_long_crowded_returns_short_cascade():
    sym_data = _btc_data(oi_pct=2.0, funding=0.001, ls=1.5)["BTCUSDT"]
    res = pca._evaluate("BTCUSDT", sym_data)
    assert res is not None
    direction, payload = res
    assert direction == "short"
    assert payload["symbol"] == "BTCUSDT"
    assert payload["expected_cascade_direction"] == "short"


def test_evaluate_short_crowded_returns_long_cascade():
    sym_data = _btc_data(oi_pct=2.0, funding=-0.001, ls=0.65)["BTCUSDT"]
    res = pca._evaluate("BTCUSDT", sym_data)
    assert res is not None
    direction, _ = res
    assert direction == "long"


def test_evaluate_returns_none_when_oi_low():
    sym_data = _btc_data(oi_pct=0.5, funding=0.001, ls=1.5)["BTCUSDT"]
    assert pca._evaluate("BTCUSDT", sym_data) is None


def test_evaluate_returns_none_when_funding_low():
    sym_data = _btc_data(oi_pct=2.0, funding=0.00001, ls=1.5)["BTCUSDT"]
    assert pca._evaluate("BTCUSDT", sym_data) is None


def test_evaluate_returns_none_when_no_crowding():
    sym_data = _btc_data(oi_pct=2.0, funding=0.001, ls=1.05)["BTCUSDT"]
    assert pca._evaluate("BTCUSDT", sym_data) is None


def test_evaluate_returns_none_when_funding_sign_disagrees():
    # LS says longs crowded but funding negative → no signal
    sym_data = _btc_data(oi_pct=2.0, funding=-0.001, ls=1.5)["BTCUSDT"]
    assert pca._evaluate("BTCUSDT", sym_data) is None


def test_evaluate_returns_none_when_missing_fields():
    assert pca._evaluate("BTCUSDT", {"oi_change_1h_pct": 2.0}) is None


def test_format_card_short_cascade():
    payload = {
        "symbol": "BTCUSDT",
        "expected_cascade_direction": "short",
        "oi_change_1h_pct": 2.0,
        "funding_rate_8h": 0.001,
        "global_ls_ratio": 1.5,
        "mark_price": 80000.0,
    }
    text = pca._format_card(payload)
    assert "BTCUSDT" in text
    assert "SHORT" in text
    assert "LONG-bags" in text  # SHORT cascade → close LONG-bags


def test_check_one_dedup_blocks_within_cooldown(monkeypatch, tmp_path):
    monkeypatch.setattr(pca, "JOURNAL_PATH", tmp_path / "j.jsonl")
    sent: list[str] = []
    now = datetime(2026, 5, 9, 12, 0, 0, tzinfo=timezone.utc)
    deriv = _btc_data(oi_pct=2.0, funding=0.001, ls=1.5)
    dedup = {"BTCUSDT_short": (now - timedelta(seconds=pca.COOLDOWN_SEC // 2))
             .strftime("%Y-%m-%dT%H:%M:%SZ")}
    pca._check_one("BTCUSDT", deriv, now, dedup, lambda t: sent.append(t))
    assert sent == []


def test_check_one_fires_after_cooldown(monkeypatch, tmp_path):
    monkeypatch.setattr(pca, "JOURNAL_PATH", tmp_path / "j.jsonl")
    sent: list[str] = []
    now = datetime(2026, 5, 9, 12, 0, 0, tzinfo=timezone.utc)
    deriv = _btc_data(oi_pct=2.0, funding=0.001, ls=1.5)
    dedup = {"BTCUSDT_short": (now - timedelta(seconds=pca.COOLDOWN_SEC + 60))
             .strftime("%Y-%m-%dT%H:%M:%SZ")}
    pca._check_one("BTCUSDT", deriv, now, dedup, lambda t: sent.append(t))
    assert len(sent) == 1


def test_check_one_writes_journal(monkeypatch, tmp_path):
    journal = tmp_path / "fires.jsonl"
    monkeypatch.setattr(pca, "JOURNAL_PATH", journal)
    sent: list[str] = []
    now = datetime(2026, 5, 9, 12, 0, 0, tzinfo=timezone.utc)
    deriv = _btc_data(oi_pct=2.0, funding=0.001, ls=1.5)
    pca._check_one("BTCUSDT", deriv, now, {}, lambda t: sent.append(t))
    assert journal.exists()
    rec = json.loads(journal.read_text(encoding="utf-8").strip())
    assert rec["event"] == "pre_cascade_fire"
    assert rec["symbol"] == "BTCUSDT"
    assert rec["expected_cascade_direction"] == "short"
