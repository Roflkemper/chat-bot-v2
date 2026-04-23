from core.pipeline_integration_fix import build_pipeline_fields, normalize_pattern_visibility


def test_pattern_hidden_below_threshold():
    result = normalize_pattern_visibility(
        {"avg_move_pct": -0.08, "sample_count": 12},
        min_abs_avg_move_pct=0.20,
        min_samples=10,
    )
    assert result["visible"] is False
    assert result["hidden_reason"] == "avg_move_below_threshold"


def test_force_search_trigger_inside_block():
    result = build_pipeline_fields(
        price=71844.29,
        existing_state="MID_RANGE",
        execution_side="SHORT",
        state_machine_snapshot={
            "state": "MID_RANGE",
            "active_block_side": "SHORT",
            "active_block_low": 70607.55,
            "active_block_high": 72857.00,
            "block_depth_pct": 55.0,
            "distance_to_active_edge": 1012.71,
            "distance_to_upper_edge": 1012.71,
            "distance_to_lower_edge": 3486.19,
            "overrun_flag": False,
        },
        pattern_snapshot={"avg_move_pct": -0.08, "sample_count": 12},
        consensus_snapshot={"direction": "NEUTRAL", "confidence": None},
    )
    assert result.state == "SEARCH_TRIGGER"
    assert result.consensus_direction == "SHORT"
    assert result.consensus_label == "SHORT | LOW"
    assert result.pattern_visible is False
