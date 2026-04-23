from features.grid_context import build_grid_context
from renderers.renderer import render_full_report


def _bar(opn, high, low, close, volume=100.0):
    return {"open": opn, "high": high, "low": low, "close": close, "volume": volume}



def test_grid_priority_neutral_in_mid_range_with_neutral_bias():
    snapshot = {
        "price": 71679.0,
        "state": "MID_RANGE",
        "consensus_direction": "NEUTRAL",
        "range_position_pct": 53.0,
    }
    candles = [
        _bar(71800, 73120, 71450, 71690, 110),
        _bar(71750, 73160, 71510, 71680, 120),
        _bar(71690, 73090, 71573, 71679, 115),
        _bar(71680, 72980, 71590, 71670, 90),
        _bar(71670, 73040, 71610, 71660, 95),
        _bar(71660, 72880, 71620, 71670, 80),
        _bar(71670, 72910, 71630, 71675, 80),
        _bar(71675, 72850, 71640, 71679, 82),
    ]
    grid = build_grid_context(snapshot, candles)
    assert grid["priority_side"] == "NEUTRAL"



def test_grid_impulse_uses_hedge_arm_targets_when_available():
    snapshot = {
        "price": 71990.0,
        "state": "MID_RANGE",
        "consensus_direction": "NEUTRAL",
        "range_position_pct": 56.0,
        "hedge_arm_up": 73438.0,
        "hedge_arm_down": 70173.0,
    }
    candles = [
        _bar(71950, 72267.89, 71903.69, 71990, 110),
        _bar(71940, 72210, 71920, 71960, 120),
        _bar(71960, 72180, 71940, 71980, 115),
        _bar(71980, 72200, 71950, 71970, 90),
        _bar(71970, 72150, 71955, 71960, 95),
        _bar(71960, 72120, 71958, 71970, 80),
        _bar(71970, 72090, 71961, 71975, 80),
        _bar(71975, 72080, 71965, 71990, 82),
    ]
    grid = build_grid_context(snapshot, candles)
    expected_down = round(abs(snapshot["hedge_arm_down"] - snapshot["price"]) / snapshot["price"] * 100.0, 2)
    expected_up = round(abs(snapshot["hedge_arm_up"] - snapshot["price"]) / snapshot["price"] * 100.0, 2)
    assert grid["liquidity_below"] == snapshot["hedge_arm_down"]
    assert grid["liquidity_above"] == snapshot["hedge_arm_up"]
    assert grid["down_impulse_pct"] == expected_down
    assert grid["up_impulse_pct"] == expected_up
    assert grid["down_impulse_pct"] > 2.0



def test_grid_layers_are_rendered_explicitly():
    snapshot = {
        "symbol": "BTCUSDT",
        "tf": "1h",
        "timestamp": "12:40",
        "forecast": {
            "short": {"direction": "NEUTRAL", "strength": "LOW", "note": "n/a"},
            "session": {"direction": "NEUTRAL", "strength": "LOW", "note": "n/a"},
            "medium": {"direction": "NEUTRAL", "strength": "LOW", "phase": "RANGE", "note": "n/a"},
        },
        "state": "MID_RANGE",
        "active_block": "LONG",
        "execution_side": "LONG",
        "block_depth_pct": 40.0,
        "depth_label": "WORK",
        "range_position_pct": 53.0,
        "distance_to_lower_edge": 100.0,
        "distance_to_upper_edge": 120.0,
        "edge_distance_pct": 10.0,
        "trigger_type": None,
        "trigger_note": "нет",
        "action": "WAIT",
        "entry_type": None,
        "context_label": "WEAK",
        "context_score": 1,
        "consensus_direction": "NEUTRAL",
        "consensus_confidence": "LOW",
        "consensus_votes": "1/3",
        "warnings": [],
        "trade_plan_active": False,
        "trade_plan_mode": "GRID MONITORING",
        "hedge_state": "OFF",
        "hedge_arm_up": 73000,
        "hedge_arm_down": 70000,
        "ginarea": {"long_grid": "WORK", "short_grid": "WORK", "aggression": "LOW", "lifecycle": "WAIT_GRID"},
        "grid_context": {
            "status": "MID_RANGE",
            "bias": "NEUTRAL",
            "priority_side": "NEUTRAL",
            "down_impulse_pct": 1.92,
            "liquidity_below": 70303,
            "down_layers": [
                {"layer": 1, "threshold_pct": 1.3, "active": True},
                {"layer": 2, "threshold_pct": 2.2, "active": False},
                {"layer": 3, "threshold_pct": 2.9, "active": False},
            ],
            "up_impulse_pct": 1.73,
            "liquidity_above": 72919,
            "up_layers": [
                {"layer": 1, "threshold_pct": 1.3, "active": True},
                {"layer": 2, "threshold_pct": 2.2, "active": False},
                {"layer": 3, "threshold_pct": 2.9, "active": False},
            ],
        },
    }
    text = render_full_report(snapshot, mode="GRID")
    assert "PRIORITY SIDE: NEUTRAL" in text
    assert "→ сетка 1 (1.3%): ✅" in text
    assert "→ сетка 2 (2.2%): ❌" in text
    assert "→ сетка 3 (2.9%): ❌" in text


def test_grid_view_marks_directional_bias_as_medium_term_when_local_priority_is_neutral():
    snapshot = {
        "symbol": "BTCUSDT",
        "tf": "1h",
        "timestamp": "13:06",
        "forecast": {
            "short": {"direction": "LONG", "strength": "MID", "note": "n/a"},
            "session": {"direction": "NEUTRAL", "strength": "LOW", "note": "n/a"},
            "medium": {"direction": "LONG", "strength": "HIGH", "phase": "MARKUP", "note": "n/a"},
        },
        "state": "MID_RANGE",
        "active_block": "SHORT",
        "execution_side": "SHORT",
        "block_depth_pct": 12.0,
        "depth_label": "EARLY",
        "range_position_pct": 56.0,
        "distance_to_lower_edge": 1500.0,
        "distance_to_upper_edge": 1178.0,
        "edge_distance_pct": 88.0,
        "trigger_type": None,
        "trigger_note": "нет",
        "action": "WAIT",
        "entry_type": None,
        "context_label": "WEAK",
        "context_score": 1,
        "consensus_direction": "LONG",
        "consensus_confidence": "MID",
        "consensus_votes": "2/3",
        "warnings": [],
        "trade_plan_active": False,
        "trade_plan_mode": "GRID MONITORING",
        "hedge_state": "OFF",
        "hedge_arm_up": 73438.0,
        "hedge_arm_down": 70173.0,
        "ginarea": {"long_grid": "WORK", "short_grid": "REDUCE", "aggression": "LOW", "lifecycle": "WAIT_GRID"},
        "grid_context": {
            "status": "MID_RANGE",
            "bias": "LONG",
            "priority_side": "NEUTRAL",
            "down_impulse_pct": 2.52,
            "liquidity_below": 70173.0,
            "down_layers": [
                {"layer": 1, "threshold_pct": 1.3, "active": True},
                {"layer": 2, "threshold_pct": 2.2, "active": True},
                {"layer": 3, "threshold_pct": 2.9, "active": False},
            ],
            "up_impulse_pct": 2.01,
            "liquidity_above": 73438.0,
            "up_layers": [
                {"layer": 1, "threshold_pct": 1.3, "active": True},
                {"layer": 2, "threshold_pct": 2.2, "active": False},
                {"layer": 3, "threshold_pct": 2.9, "active": False},
            ],
        },
    }
    text = render_full_report(snapshot, mode="GRID")
    assert "BIAS: LONG (среднесрочный)" in text
    assert "⚠️ локально нейтрально — сетки обе рабочие" in text
