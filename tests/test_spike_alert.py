"""Unit tests for services.spike_alert.

Tests the trigger logic in `_check_one_symbol`:
  - upspike fires when move>=1.5%, taker_buy>=75%, OI>=0
  - downspike fires when move<=-1.5%, taker_sell>=75%, OI>=0
  - all three conditions required (each suppresses individually)
  - dedup cooldown blocks repeat fires
  - no fire when deriv_live missing fields
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pandas as pd
import pytest

from services.spike_alert import loop as spike_loop


def _ohlcv(prices: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"close": prices, "open": prices, "high": prices, "low": prices})


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 5, 9, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def base_deriv() -> dict:
    return {
        "BTCUSDT": {
            "taker_buy_pct": 80.0,
            "taker_sell_pct": 20.0,
            "oi_change_1h_pct": 1.5,
        },
    }


def test_upspike_fires(now, base_deriv):
    sent: list[str] = []

    def send_fn(text: str) -> None:
        sent.append(text)

    # 1m closes: 6 bars where last is +2% over [-6]
    prices = [80000.0] * 6 + [81600.0]  # +2% in 5 bars
    with patch("core.data_loader.load_klines", return_value=_ohlcv(prices)):
        dedup: dict = {}
        spike_loop._check_one_symbol("BTCUSDT", base_deriv, now, dedup, send_fn)

    assert len(sent) == 1
    assert "UP" in sent[0]
    assert "SHORT-bags" in sent[0]
    assert "BTCUSDT_up" in dedup


def test_downspike_fires(now):
    sent: list[str] = []
    deriv = {
        "BTCUSDT": {"taker_buy_pct": 20.0, "taker_sell_pct": 80.0, "oi_change_1h_pct": 1.0},
    }
    prices = [80000.0] * 6 + [78000.0]  # -2.5%
    with patch("core.data_loader.load_klines", return_value=_ohlcv(prices)):
        dedup: dict = {}
        spike_loop._check_one_symbol("BTCUSDT", deriv, now, dedup, lambda t: sent.append(t))

    assert len(sent) == 1
    assert "DOWN" in sent[0]
    assert "LONG-bags" in sent[0]


def test_no_fire_when_move_under_threshold(now, base_deriv):
    sent: list[str] = []
    prices = [80000.0] * 6 + [80800.0]  # +1.0%, below 1.5
    with patch("core.data_loader.load_klines", return_value=_ohlcv(prices)):
        spike_loop._check_one_symbol("BTCUSDT", base_deriv, now, {}, lambda t: sent.append(t))
    assert sent == []


def test_no_fire_when_taker_under_threshold(now):
    sent: list[str] = []
    deriv = {
        "BTCUSDT": {"taker_buy_pct": 65.0, "taker_sell_pct": 35.0, "oi_change_1h_pct": 1.0},
    }
    prices = [80000.0] * 6 + [82000.0]  # +2.5%
    with patch("core.data_loader.load_klines", return_value=_ohlcv(prices)):
        spike_loop._check_one_symbol("BTCUSDT", deriv, now, {}, lambda t: sent.append(t))
    assert sent == []


def test_no_fire_when_oi_bleeding(now):
    sent: list[str] = []
    deriv = {
        "BTCUSDT": {"taker_buy_pct": 80.0, "taker_sell_pct": 20.0, "oi_change_1h_pct": -1.0},
    }
    prices = [80000.0] * 6 + [82000.0]
    with patch("core.data_loader.load_klines", return_value=_ohlcv(prices)):
        spike_loop._check_one_symbol("BTCUSDT", deriv, now, {}, lambda t: sent.append(t))
    assert sent == []


def test_dedup_blocks_within_cooldown(now, base_deriv):
    sent: list[str] = []
    prices = [80000.0] * 6 + [82000.0]
    dedup = {"BTCUSDT_up": (now - timedelta(seconds=spike_loop.COOLDOWN_SEC // 2)).strftime("%Y-%m-%dT%H:%M:%SZ")}
    with patch("core.data_loader.load_klines", return_value=_ohlcv(prices)):
        spike_loop._check_one_symbol("BTCUSDT", base_deriv, now, dedup, lambda t: sent.append(t))
    assert sent == []


def test_dedup_clears_after_cooldown(now, base_deriv):
    sent: list[str] = []
    prices = [80000.0] * 6 + [82000.0]
    dedup = {"BTCUSDT_up": (now - timedelta(seconds=spike_loop.COOLDOWN_SEC + 60)).strftime("%Y-%m-%dT%H:%M:%SZ")}
    with patch("core.data_loader.load_klines", return_value=_ohlcv(prices)):
        spike_loop._check_one_symbol("BTCUSDT", base_deriv, now, dedup, lambda t: sent.append(t))
    assert len(sent) == 1


def test_no_fire_when_deriv_missing(now):
    sent: list[str] = []
    prices = [80000.0] * 6 + [82000.0]
    with patch("core.data_loader.load_klines", return_value=_ohlcv(prices)):
        # missing taker_buy_pct
        spike_loop._check_one_symbol("BTCUSDT", {"BTCUSDT": {"oi_change_1h_pct": 1.0}}, now, {}, lambda t: sent.append(t))
    assert sent == []


def test_no_fire_when_klines_unavailable(now, base_deriv):
    sent: list[str] = []
    with patch("core.data_loader.load_klines", side_effect=RuntimeError("network")):
        spike_loop._check_one_symbol("BTCUSDT", base_deriv, now, {}, lambda t: sent.append(t))
    assert sent == []
