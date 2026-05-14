from core.live_decision_authority import evaluate_live_decision


def _base_snapshot(**overrides):
    snap = {
        "action": "WAIT",
        "execution_side": "LONG",
        "consensus_direction": "SHORT",
        "structural_context": {"bias": "SHORT"},
        "context_score": 1,
        "depth_label": "RISK",
        "bias_score": -4,
        "danger_to_active_side": True,
        "near_breakout": True,
        "absorption": {"is_active": False},
        "flip_prep_status": "WATCHING",
        "entry_quality": "NO_TRADE",
        "execution_profile": "NO_ENTRY",
        "partial_entry_allowed": False,
        "scale_in_allowed": False,
        "range_low": 71017.0,
        "range_high": 74083.0,
        "price": 71226.67,
        "grid_action": {"long_action": "HOLD", "short_action": "ENABLE"},
    }
    snap.update(overrides)
    return snap


def test_danger_wait_is_no_trade_and_defensive():
    result = evaluate_live_decision(_base_snapshot())
    assert result["live_state"] == "OBSERVE"
    assert result["execution_grade_live"] == "NO_TRADE"
    assert result["manual_action_now"] == "DEFEND LONG"
    assert result["urgency_label_live"] in {"HIGH", "IMMEDIATE"}
    assert result["bad_location"] is True


def test_prepare_with_alignment_gets_trade_grade():
    result = evaluate_live_decision(_base_snapshot(
        action="PREPARE",
        execution_side="SHORT",
        consensus_direction="SHORT",
        structural_context={"bias": "SHORT"},
        context_score=3,
        depth_label="WORK",
        bias_score=-6,
        danger_to_active_side=False,
        near_breakout=False,
        entry_quality="A",
        execution_profile="STANDARD",
        price=73500.0,
        absorption={"is_active": True},
        grid_action={"long_action": "PAUSE", "short_action": "BOOST"},
    ))
    assert result["live_state"] == "PREPARE"
    assert result["execution_grade_live"] in {"A", "B"}
    assert result["manual_action_now"] == "PREPARE SHORT"
    assert result["bot_action_now"] == "BOOST SHORT / PAUSE LONG"
    assert result["tp1_live"] is not None


def test_enter_quality_a_allows_enter_label():
    result = evaluate_live_decision(_base_snapshot(
        action="ENTER",
        execution_side="LONG",
        consensus_direction="LONG",
        structural_context={"bias": "LONG"},
        context_score=3,
        depth_label="WORK",
        bias_score=7,
        danger_to_active_side=False,
        near_breakout=False,
        entry_quality="A",
        execution_profile="AGGRESSIVE",
        absorption={"is_active": True},
        price=72000.0,
        partial_entry_allowed=True,
        scale_in_allowed=True,
        grid_action={"long_action": "BOOST", "short_action": "PAUSE"},
    ))
    assert result["live_state"] == "ENTER"
    assert result["execution_grade_live"] == "A"
    assert result["manual_action_now"] == "ENTER LONG"
    assert result["management_mode"] == "ACTIVE"
