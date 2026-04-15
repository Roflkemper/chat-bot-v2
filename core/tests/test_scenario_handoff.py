from core.scenario_handoff import compute_scenario_weights


def test_edge_pressure_without_absorption_increases_break_probability():
    snapshot = {
        'block_pressure': 'AGAINST',
        'block_pressure_strength': 'HIGH',
        'consensus_direction': 'SHORT',
        'active_block': 'LONG',
        'consensus_alignment_count': 3,
        'depth_label': 'EARLY',
        'block_depth_pct': 8.0,
        'range_position_pct': 3.0,
        'forecast': {'medium': {'phase': 'MARKDOWN'}, 'short': {'direction': 'SHORT'}},
        'hedge_state': 'ARM',
        'trigger_type': 'RECLAIM',
        'flip_prep_status': 'IDLE',
        'absorption': {'bars_at_edge': 4, 'is_active': False},
    }
    base_prob, alt_prob, _, alt_reasons = compute_scenario_weights(snapshot)
    assert alt_prob > 50
    assert any('4+ баров у края без absorption' in x for x in alt_reasons)
