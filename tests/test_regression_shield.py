from core import pipeline
from core.grid_action_engine import GridActionInput, build_grid_action
from renderers.renderer import render_full_report


def _c(o, h, l, c, v=100):
    return {"open": o, "high": h, "low": l, "close": c, "volume": v}


def _patch_pipeline(monkeypatch, *, trigger=False, trigger_type='RECLAIM', trigger_note='нет сигнала'):
    candles = [_c(100, 101, 99, 100.8), _c(100.8, 101.1, 100.2, 100.9), _c(100.9, 101.2, 100.4, 101.0), _c(101.0, 101.1, 98.9, 99.0, 180)] * 50
    monkeypatch.setattr(pipeline, 'get_price', lambda symbol: 99.0)
    monkeypatch.setattr(pipeline, 'get_klines', lambda symbol, interval, limit: candles)
    monkeypatch.setattr(pipeline, 'aggregate_to_4h', lambda x: x[-20:])
    monkeypatch.setattr(pipeline, 'aggregate_to_1d', lambda x: x[-20:])
    monkeypatch.setattr(pipeline, 'detect_trigger', lambda *args, **kwargs: (trigger, trigger_type if trigger else None, trigger_note))
    monkeypatch.setattr(pipeline, 'short_term_forecast', lambda x: {'direction': 'LONG', 'strength': 'HIGH', 'note': 'n'})
    monkeypatch.setattr(pipeline, 'session_forecast', lambda x: {'direction': 'LONG', 'strength': 'MID', 'note': 'n'})
    monkeypatch.setattr(pipeline, 'medium_forecast', lambda x: {'direction': 'LONG', 'strength': 'MID', 'phase': 'MARKUP', 'note': 'n'})
    monkeypatch.setattr(pipeline, 'build_consensus', lambda a, b, c: ('LONG', 'HIGH', '3/3', 3))
    monkeypatch.setattr(pipeline, 'compute_block_pressure', lambda *args, **kwargs: ('WITH', 'LOW', False, ''))
    monkeypatch.setattr(pipeline, 'analyze_structural_context', lambda x: {'bias': 'LONG', 'strength': 'LOW'})
    monkeypatch.setattr(pipeline, 'detect_liquidity_structure', lambda x: {})
    monkeypatch.setattr(pipeline, 'load_market_state', lambda: {})
    monkeypatch.setattr(pipeline, 'load_position_state', lambda: {'active': False})
    monkeypatch.setattr(pipeline, 'save_market_state', lambda x: None)
    monkeypatch.setattr(pipeline, 'update_flip_prep', lambda prev, base: {'flip_prep_status': 'IDLE'})
    monkeypatch.setattr(pipeline, 'compute_scenario_weights', lambda base: (55, 45, [], []))


def _make_grid_input(**overrides):
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
        down_impulse_pct=0.9,
        up_impulse_pct=2.8,
        down_target=70173.0,
        up_target=73438.0,
        down_layers=0,
        up_layers=3,
        hedge_arm_down=70173.0,
        hedge_arm_up=73438.0,
        hedge_state='ARM',
        repeated_upper_rejection=False,
        repeated_lower_rejection=False,
        upper_sweep=False,
        lower_sweep=False,
        distribution=False,
        accumulation=False,
        equal_highs=False,
        equal_lows=False,
        volume_rejection_up=False,
        volume_rejection_down=False,
        market_regime='RANGE',
        range_quality='GOOD',
        trend_pressure_side='NEUTRAL',
        trend_pressure_strength='LOW',
        forecast_conflict=False,
    )
    data.update(overrides)
    return GridActionInput(**data)


def test_prepare_requires_real_trigger(monkeypatch):
    _patch_pipeline(monkeypatch, trigger=False, trigger_note='подтверждения нет')
    snap = pipeline.build_full_snapshot('BTCUSDT')
    assert snap['action'] == 'WAIT'
    assert snap['entry_type'] is None


def test_prepare_allowed_only_after_trigger(monkeypatch):
    _patch_pipeline(monkeypatch, trigger=True, trigger_type='RECLAIM', trigger_note='есть reclaim')
    snap = pipeline.build_full_snapshot('BTCUSDT')
    assert snap['action'] in {'PREPARE', 'ENTER'}


def test_no_long_boost_when_bias_is_minus_three_or_worse():
    result = build_grid_action(_make_grid_input(
        priority_side='LONG',
        session_side='SHORT',
        session_strength='HIGH',
        bias_score=-3,
        edge_distance_pct=5.0,
    ))
    assert result['long_action'] != 'BOOST'


def test_no_long_boost_when_edge_pressure_is_high():
    result = build_grid_action(_make_grid_input(
        priority_side='LONG',
        bars_at_edge=5,
        absorption_active=False,
    ))
    assert result['long_action'] != 'BOOST'


def test_exit_strategy_updates_on_neutral_momentum_for_long_side():
    lines = pipeline._build_exit_strategy({
        'active_block': 'SHORT',
        'forecast': {
            'short': {'direction': 'NEUTRAL', 'strength': 'LOW'},
            'session': {'direction': 'NEUTRAL', 'strength': 'LOW'},
        },
        'hedge_arm_down': 70100.0,
        'hedge_arm_up': 73400.0,
        'break_level': 73400.0,
        'absorption': {'is_active': False, 'bars_at_edge': 5},
        'bias_score': -4,
        'volatility': {'atr_ratio': 0.7},
    })
    text = '\n'.join(lines)
    assert 'momentum иссяк' in text
    assert 'лонг частями' in text


def test_no_duplicated_action_plan_in_telegram_output():
    snapshot = {
        'symbol': 'BTCUSDT', 'tf': '1h', 'timestamp': '13:55',
        'forecast': {
            'short': {'direction': 'SHORT', 'strength': 'HIGH', 'note': 'n/a'},
            'session': {'direction': 'SHORT', 'strength': 'HIGH', 'note': 'n/a'},
            'medium': {'direction': 'LONG', 'strength': 'HIGH', 'phase': 'MARKUP', 'note': 'n/a'},
        },
        'state': 'SEARCH_TRIGGER', 'active_block': 'LONG', 'execution_side': 'LONG',
        'block_depth_pct': 10.0, 'depth_label': 'WORK', 'range_position_pct': 8.0,
        'distance_to_lower_edge': 210.0, 'distance_to_upper_edge': 2270.0, 'edge_distance_pct': 16.0,
        'trigger_type': 'RECLAIM', 'trigger_note': 'касание нижнего края', 'trigger_blocked': False,
        'action': 'WAIT', 'entry_type': None, 'context_label': 'WEAK', 'context_score': 1,
        'consensus_direction': 'SHORT', 'consensus_confidence': 'MID', 'consensus_votes': '2/3',
        'warnings': [], 'trade_plan_active': False, 'trade_plan_mode': 'GRID MONITORING',
        'hedge_state': 'ARM', 'hedge_arm_up': 74083.0, 'hedge_arm_down': 71017.0,
        'grid_action': {'grid_regime': 'DANGER', 'bias_side': 'LONG', 'structural_side': 'SHORT', 'priority_side': 'LONG', 'down_target': 71017.0, 'up_target': 74083.0, 'down_impulse_pct': 0.7, 'up_impulse_pct': 3.58, 'down_layers': 0, 'up_layers': 3, 'long_action': 'ENABLE', 'short_action': 'HOLD'},
        'bias_score': -4, 'bias_label': 'медвежье давление', 'absorption': {'label': 'нет данных', 'bars_at_edge': 1},
        'top_signal': '⏸️ WAIT',
        'current_action_lines': ['• руками: не входить — ждать подтверждение'],
        'manual_action_lines': ['• действие: не входить — ждать подтверждение'],
        'grid_action_lines': ['• LONG grid: ENABLE', '• SHORT grid: HOLD'],
        'position_control': {'status': 'FLAT', 'source': 'none', 'entry_price': None, 'pnl_pct': 0.0, 'recommended_action': 'WAIT'},
        'risk_authority': {'lines': ['• MODE: LOCKDOWN', '• ADD: NO_ADD']},
        'if_then_plan': [],
        'trade_plan': {},
    }
    text = render_full_report(snapshot)
    assert text.count('• руками: не входить — ждать подтверждение') == 1


def test_no_position_control_block_without_real_position_state():
    snapshot = {
        'symbol': 'BTCUSDT', 'tf': '1h', 'timestamp': '13:55',
        'forecast': {
            'short': {'direction': 'SHORT', 'strength': 'HIGH', 'note': 'n/a'},
            'session': {'direction': 'SHORT', 'strength': 'HIGH', 'note': 'n/a'},
            'medium': {'direction': 'LONG', 'strength': 'HIGH', 'phase': 'MARKUP', 'note': 'n/a'},
        },
        'state': 'SEARCH_TRIGGER', 'active_block': 'LONG', 'execution_side': 'LONG',
        'block_depth_pct': 10.0, 'depth_label': 'WORK', 'range_position_pct': 8.0,
        'distance_to_lower_edge': 210.0, 'distance_to_upper_edge': 2270.0, 'edge_distance_pct': 16.0,
        'trigger_type': 'NONE', 'trigger_note': 'нет сигнала', 'trigger_blocked': False,
        'action': 'WAIT', 'entry_type': None, 'context_label': 'WEAK', 'context_score': 1,
        'consensus_direction': 'SHORT', 'consensus_confidence': 'MID', 'consensus_votes': '2/3',
        'warnings': [], 'trade_plan_active': False, 'trade_plan_mode': 'GRID MONITORING',
        'hedge_state': 'ARM', 'hedge_arm_up': 74083.0, 'hedge_arm_down': 71017.0,
        'grid_action': {'grid_regime': 'DANGER', 'bias_side': 'LONG', 'structural_side': 'SHORT', 'priority_side': 'LONG', 'down_target': 71017.0, 'up_target': 74083.0, 'down_impulse_pct': 0.7, 'up_impulse_pct': 3.58, 'down_layers': 0, 'up_layers': 3, 'long_action': 'ENABLE', 'short_action': 'HOLD'},
        'bias_score': -4, 'bias_label': 'медвежье давление', 'absorption': {'label': 'нет данных', 'bars_at_edge': 1},
        'top_signal': '⏸️ WAIT',
        'current_action_lines': ['• руками: не входить — ждать подтверждение'],
        'manual_action_lines': ['• действие: не входить — ждать подтверждение'],
        'grid_action_lines': ['• LONG grid: ENABLE', '• SHORT grid: HOLD'],
        'position_control': {'status': 'FLAT', 'source': 'none', 'entry_price': None, 'pnl_pct': 0.0, 'recommended_action': 'WAIT'},
        'risk_authority': {'lines': ['• MODE: LOCKDOWN', '• ADD: NO_ADD']},
        'if_then_plan': [],
        'trade_plan': {},
    }
    text = render_full_report(snapshot)
    assert 'POSITION CONTROL:' not in text


def test_position_control_block_is_rendered_for_real_position_state():
    snapshot = {
        'symbol': 'BTCUSDT', 'tf': '1h', 'timestamp': '13:55',
        'forecast': {
            'short': {'direction': 'SHORT', 'strength': 'HIGH', 'note': 'n/a'},
            'session': {'direction': 'SHORT', 'strength': 'HIGH', 'note': 'n/a'},
            'medium': {'direction': 'LONG', 'strength': 'HIGH', 'phase': 'MARKUP', 'note': 'n/a'},
        },
        'state': 'SEARCH_TRIGGER', 'active_block': 'LONG', 'execution_side': 'LONG',
        'block_depth_pct': 10.0, 'depth_label': 'WORK', 'range_position_pct': 8.0,
        'distance_to_lower_edge': 210.0, 'distance_to_upper_edge': 2270.0, 'edge_distance_pct': 16.0,
        'trigger_type': 'RECLAIM', 'trigger_note': 'касание нижнего края', 'trigger_blocked': True, 'trigger_block_reason': 'структура 1h против активного блока',
        'action': 'WAIT', 'entry_type': None, 'context_label': 'WEAK', 'context_score': 1,
        'consensus_direction': 'SHORT', 'consensus_confidence': 'MID', 'consensus_votes': '2/3',
        'warnings': [], 'trade_plan_active': False, 'trade_plan_mode': 'GRID MONITORING',
        'hedge_state': 'ARM', 'hedge_arm_up': 74083.0, 'hedge_arm_down': 71017.0,
        'grid_action': {'grid_regime': 'DANGER', 'bias_side': 'LONG', 'structural_side': 'SHORT', 'priority_side': 'LONG', 'down_target': 71017.0, 'up_target': 74083.0, 'down_impulse_pct': 0.7, 'up_impulse_pct': 3.58, 'down_layers': 0, 'up_layers': 3, 'long_action': 'ENABLE', 'short_action': 'HOLD'},
        'bias_score': -4, 'bias_label': 'медвежье давление', 'absorption': {'label': 'нет данных', 'bars_at_edge': 1},
        'top_signal': '⚠️ DANGER | 210$ до пробоя вниз — LONG под угрозой',
        'current_action_lines': ['• руками: не входить — ждать подтверждение'],
        'manual_action_lines': ['• действие: не входить — ждать подтверждение'],
        'grid_action_lines': ['• LONG grid: ENABLE', '• SHORT grid: HOLD'],
        'position_control': {'status': 'LONG MANAGE', 'source': 'state', 'entry_price': 71017.0, 'pnl_pct': 1.25, 'recommended_action': 'REDUCE / PROTECT'},
        'risk_authority': {'lines': ['• MODE: LOCKDOWN', '• ADD: NO_ADD']},
        'if_then_plan': ['▶ ПРОБОЙ: закрытие < 71017.00 (2 бара) → SHORT | цель 71017.00'],
        'trade_plan': {'entry': 71017.0},
    }
    text = render_full_report(snapshot)
    assert 'POSITION CONTROL:' in text
    assert '• STATUS: LONG MANAGE' in text
    assert '• ACTION: REDUCE / PROTECT' in text
