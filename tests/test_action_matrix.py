from __future__ import annotations

from core.orchestrator.action_matrix import decide_category_action
from core.orchestrator.portfolio_state import Category


def _cat(key: str, asset: str, side: str) -> Category:
    return Category(key=key, asset=asset, side=side, contract_type="linear", label_ru=key)


def test_btc_range_short_l1_runs():
    result = decide_category_action("RANGE", [], _cat("btc_short", "BTC", "SHORT"))
    assert result.action == "RUN"


def test_btc_range_long_l1_runs():
    result = decide_category_action("RANGE", [], _cat("btc_long", "BTC", "LONG"))
    assert result.action == "RUN"


def test_btc_range_long_l2_arms():
    result = decide_category_action("RANGE", [], _cat("btc_long_l2", "BTC", "LONG"))
    assert result.action == "ARM"


def test_btc_trend_up_short_reduces():
    result = decide_category_action("TREND_UP", [], _cat("btc_short", "BTC", "SHORT"))
    assert result.action == "REDUCE"
    assert result.reduce_size_pct == 50


def test_btc_trend_up_long_runs():
    result = decide_category_action("TREND_UP", [], _cat("btc_long", "BTC", "LONG"))
    assert result.action == "RUN"


def test_btc_trend_down_short_runs():
    result = decide_category_action("TREND_DOWN", [], _cat("btc_short", "BTC", "SHORT"))
    assert result.action == "RUN"


def test_btc_trend_down_long_pauses():
    result = decide_category_action("TREND_DOWN", [], _cat("btc_long", "BTC", "LONG"))
    assert result.action == "PAUSE"


def test_btc_cascade_down_long_stops():
    result = decide_category_action("CASCADE_DOWN", [], _cat("btc_long", "BTC", "LONG"))
    assert result.action == "STOP"


def test_btc_cascade_up_short_pauses():
    result = decide_category_action("CASCADE_UP", [], _cat("btc_short", "BTC", "SHORT"))
    assert result.action == "PAUSE"


def test_unknown_category_uses_universal_fallback():
    result = decide_category_action("RANGE", [], _cat("eth_short", "ETH", "SHORT"))
    assert result.action == "RUN"
    assert result.reason == "Боковик — шорт работает"


def test_eth_short_l1_in_trend_up_reduces():
    result = decide_category_action("TREND_UP", [], _cat("eth_short", "ETH", "SHORT"))
    assert result.action == "REDUCE"


def test_news_blackout_overrides_everything():
    result = decide_category_action("RANGE", ["NEWS_BLACKOUT"], _cat("btc_long", "BTC", "LONG"))
    assert result.action == "STOP"


def test_huge_down_gap_forces_long_pause():
    result = decide_category_action("TREND_UP", ["HUGE_DOWN_GAP"], _cat("btc_long", "BTC", "LONG"))
    assert result.action == "PAUSE"


def test_trend_up_suspected_cancels_short_reduce():
    result = decide_category_action("TREND_UP", ["TREND_UP_SUSPECTED"], _cat("btc_short", "BTC", "SHORT"))
    assert result.action == "RUN"


def test_trend_down_suspected_cancels_long_pause():
    result = decide_category_action("TREND_DOWN", ["TREND_DOWN_SUSPECTED"], _cat("btc_long", "BTC", "LONG"))
    assert result.action == "RUN"


def test_weekend_low_vol_stops_l2():
    result = decide_category_action("RANGE", ["WEEKEND_LOW_VOL"], _cat("btc_long_l2", "BTC", "LONG"))
    assert result.action == "STOP"


def test_post_funding_holds_l2():
    result = decide_category_action("RANGE", ["POST_FUNDING_HOUR"], _cat("btc_long_l2", "BTC", "LONG"))
    assert result.action == "PAUSE"
