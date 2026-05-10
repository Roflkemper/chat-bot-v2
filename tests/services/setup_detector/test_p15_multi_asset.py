"""Tests for P-15 multi-asset extensions: per-pair sizing + cross-asset cap."""
from __future__ import annotations

from services.setup_detector import p15_rolling


class _Leg:
    def __init__(self, direction: str, in_pos: bool):
        self.direction = direction
        self.in_pos = in_pos


def test_resolve_base_size_pair_factor():
    """BTC should get full size, ETH half, XRP 30%."""
    # Use fixed fallback (no config) so we test pure factor scaling.
    btc = p15_rolling._resolve_base_size_usd("BTCUSDT")
    eth = p15_rolling._resolve_base_size_usd("ETHUSDT")
    xrp = p15_rolling._resolve_base_size_usd("XRPUSDT")
    # Without ADVISOR_DEPO_TOTAL the function falls back to P15_BASE_SIZE_USD × factor
    assert btc > eth > xrp
    # BTC is the reference (factor 1.0).
    assert eth == btc * 0.5
    assert abs(xrp - btc * 0.3) < 1e-6


def test_resolve_base_size_unknown_pair():
    """Unknown pair gets default 0.5x factor (conservative)."""
    size = p15_rolling._resolve_base_size_usd("DOGEUSDT")
    btc = p15_rolling._resolve_base_size_usd("BTCUSDT")
    assert size == btc * 0.5


def test_count_same_direction_open_legs_empty():
    assert p15_rolling._count_same_direction_open_legs({}, "long") == 0


def test_count_same_direction_open_legs_mixed():
    state = {
        "BTCUSDT:long":  _Leg("long",  True),
        "BTCUSDT:short": _Leg("short", False),
        "ETHUSDT:long":  _Leg("long",  True),
        "XRPUSDT:long":  _Leg("long",  False),
        "XRPUSDT:short": _Leg("short", True),
    }
    # 2 longs open (BTC + ETH); XRP long not in pos.
    assert p15_rolling._count_same_direction_open_legs(state, "long") == 2
    # 1 short open (XRP).
    assert p15_rolling._count_same_direction_open_legs(state, "short") == 1


def test_count_same_direction_excludes_pair():
    state = {
        "BTCUSDT:long": _Leg("long", True),
        "ETHUSDT:long": _Leg("long", True),
        "XRPUSDT:long": _Leg("long", True),
    }
    # Excluding XRP, only BTC + ETH count.
    assert p15_rolling._count_same_direction_open_legs(
        state, "long", except_pair="XRPUSDT"
    ) == 2


def test_pair_factor_constants_sane():
    """Pair factors must sum to <=3 (3 pairs) and be in (0, 1]."""
    factors = p15_rolling.P15_PAIR_SIZE_FACTOR.values()
    assert all(0 < f <= 1.0 for f in factors)
    # BTC must be the strongest factor (validated as primary edge).
    assert p15_rolling.P15_PAIR_SIZE_FACTOR["BTCUSDT"] == max(factors)


def test_max_same_direction_legs_is_2():
    """Cap of 2 means 3rd correlated leg gets refused."""
    assert p15_rolling.P15_MAX_SAME_DIRECTION_LEGS == 2
