from core.state_machine_depth import RangeLevels, evaluate_state, ExecutionState


def test_mid_range_none_side():
    levels = RangeLevels(low=68000, mid=70500, high=72857)
    result = evaluate_state(price=70500, levels=levels)
    assert result.state == ExecutionState.MID_RANGE
    assert result.active_side == "NONE"


def test_search_trigger_inside_short_block():
    levels = RangeLevels(low=68358.10, mid=70607.55, high=72857.00)
    result = evaluate_state(price=72487.90, levels=levels)
    assert result.active_side == "SHORT"
    assert result.state in {ExecutionState.SEARCH_TRIGGER, ExecutionState.PRE_ACTIVATION, ExecutionState.OVERRUN}
    assert result.depth_pct > 0


def test_overrun_blocks_entry():
    levels = RangeLevels(low=68358.10, mid=70607.55, high=72857.00)
    result = evaluate_state(price=72840.00, levels=levels)
    assert result.state == ExecutionState.OVERRUN
    assert result.entry_blocked is True
