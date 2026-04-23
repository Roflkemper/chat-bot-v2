from core.grid_action_engine import GridActionInput, build_grid_action


def make_input(**overrides):
    data = dict(
        price=71990.0,
        range_low=69000.0,
        range_high=73600.0,
        range_mid=71300.0,
        range_position_pct=56.0,
        range_width_pct=6.6,
        scalp_side='LONG',
        scalp_strength='MID',
        session_side='NEUTRAL',
        session_strength='LOW',
        midterm_side='LONG',
        midterm_strength='HIGH',
        consensus_side='LONG',
        consensus_strength='MID',
        down_impulse_pct=2.78,
        up_impulse_pct=1.75,
        down_target=70173.0,
        up_target=73438.0,
        down_layers=2,
        up_layers=1,
        hedge_arm_down=70173.0,
        hedge_arm_up=73438.0,
        hedge_state='ARM',
        repeated_upper_rejection=True,
        repeated_lower_rejection=False,
        upper_sweep=True,
        lower_sweep=False,
        distribution=True,
        accumulation=False,
        equal_highs=True,
        equal_lows=False,
        volume_rejection_up=True,
        volume_rejection_down=False,
        market_regime='RANGE',
        range_quality='GOOD',
        trend_pressure_side='NEUTRAL',
        trend_pressure_strength='LOW',
        forecast_conflict=False,
    )
    data.update(overrides)
    return GridActionInput(**data)


def test_priority_flips_short_when_downside_has_more_layers_and_structure():
    result = build_grid_action(make_input())
    assert result['priority_side'] == 'SHORT'
    assert result['long_action'] == 'REDUCE'
    assert result['short_action'] == 'BOOST'


def test_mid_range_neutral_stays_neutral():
    result = build_grid_action(make_input(
        range_position_pct=50.0,
        midterm_side='NEUTRAL',
        consensus_side='NEUTRAL',
        down_layers=1,
        up_layers=1,
        down_impulse_pct=1.55,
        up_impulse_pct=1.50,
        repeated_upper_rejection=False,
        upper_sweep=False,
        distribution=False,
        equal_highs=False,
        volume_rejection_up=False,
    ))
    assert result['priority_side'] == 'NEUTRAL'


def test_session_short_high_near_edge_blocks_long_boost():
    result = build_grid_action(make_input(
        priority_side='LONG' if False else 'LONG',
        midterm_side='LONG',
        session_side='SHORT',
        session_strength='HIGH',
        bias_score=-4,
        edge_distance_pct=5.0,
        up_layers=3,
        down_layers=0,
        repeated_upper_rejection=False,
        upper_sweep=False,
        distribution=False,
        equal_highs=False,
        volume_rejection_up=False,
        repeated_lower_rejection=False,
        lower_sweep=False,
        accumulation=False,
        equal_lows=False,
        volume_rejection_down=False,
    ))
    assert result['long_action'] in {'HOLD', 'REDUCE'}


def test_risk_lines_note_edge_pressure_without_absorption():
    result = build_grid_action(make_input(
        bars_at_edge=4,
        absorption_active=False,
    ))
    assert any('4+ баров у края без absorption' in line for line in result['risk_lines'])
