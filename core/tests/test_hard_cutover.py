from core.execution_snapshot import build_execution_snapshot


def test_inside_upper_block_forces_search_trigger():
    snap = build_execution_snapshot({
        'price': 71856.46,
        'range_low': 68358.10,
        'range_mid': 70607.55,
        'range_high': 72857.00,
        'upper_block_low': 70607.55,
        'upper_block_high': 72857.00,
        'lower_block_low': 68358.10,
        'lower_block_high': 70607.55,
        'pattern_avg_move_pct': 0.17,
        'pattern_direction': 'NEUTRAL',
    })
    assert snap['state'] == 'SEARCH_TRIGGER'
    assert snap['side'] == 'SHORT'
    assert snap['consensus_direction'] == 'SHORT'
    assert snap['consensus_confidence'] == 'LOW'
    assert snap['pattern_visible'] is False


def test_overrun_blocks_entry():
    snap = build_execution_snapshot({
        'price': 72790.00,
        'range_low': 68358.10,
        'range_mid': 70607.55,
        'range_high': 72857.00,
        'upper_block_low': 70607.55,
        'upper_block_high': 72857.00,
        'lower_block_low': 68358.10,
        'lower_block_high': 70607.55,
    })
    assert snap['state'] == 'OVERRUN'
    assert snap['block_depth_pct'] >= 85.0
