from core import pipeline
from renderers.renderer import render_full_report


def _c(o, h, l, c, v=100):
    return {"open": o, "high": h, "low": l, "close": c, "volume": v}


def test_pipeline_builds_position_control_and_lockdown(monkeypatch):
    candles = [_c(100, 101, 99, 100.8), _c(100.8, 101.1, 100.2, 100.9), _c(100.9, 101.2, 100.4, 101.0), _c(101.0, 101.1, 98.9, 99.0, 180)] * 50
    monkeypatch.setattr(pipeline, 'get_price', lambda symbol: 99.0)
    monkeypatch.setattr(pipeline, 'get_klines', lambda symbol, interval, limit: candles)
    monkeypatch.setattr(pipeline, 'aggregate_to_4h', lambda x: x[-20:])
    monkeypatch.setattr(pipeline, 'aggregate_to_1d', lambda x: x[-20:])
    monkeypatch.setattr(pipeline, 'detect_trigger', lambda *args, **kwargs: (False, None, 'нет'))
    monkeypatch.setattr(pipeline, 'short_term_forecast', lambda x: {'direction': 'SHORT', 'strength': 'HIGH', 'note': 'n'})
    monkeypatch.setattr(pipeline, 'session_forecast', lambda x: {'direction': 'SHORT', 'strength': 'HIGH', 'note': 'n'})
    monkeypatch.setattr(pipeline, 'medium_forecast', lambda x: {'direction': 'LONG', 'strength': 'HIGH', 'phase': 'MARKUP', 'note': 'n'})
    monkeypatch.setattr(pipeline, 'build_consensus', lambda a, b, c: ('SHORT', 'MID', '2/3', 2))
    monkeypatch.setattr(pipeline, 'compute_block_pressure', lambda *args, **kwargs: ('WITH', 'LOW', False, ''))
    monkeypatch.setattr(pipeline, 'analyze_structural_context', lambda x: {'bias': 'SHORT', 'strength': 'HIGH'})
    monkeypatch.setattr(pipeline, 'detect_liquidity_structure', lambda x: {})
    monkeypatch.setattr(pipeline, 'load_market_state', lambda: {})
    monkeypatch.setattr(pipeline, 'load_position_state', lambda: {'active': True, 'side': 'LONG', 'stage': 'MANAGE', 'entry_price': 101.0, 'size': 1.0, 'source': 'test'})
    monkeypatch.setattr(pipeline, 'save_market_state', lambda x: None)
    monkeypatch.setattr(pipeline, 'update_flip_prep', lambda prev, base: {'flip_prep_status': 'IDLE'})
    monkeypatch.setattr(pipeline, 'compute_scenario_weights', lambda base: (45, 55, [], []))

    snap = pipeline.build_full_snapshot('BTCUSDT')
    assert snap['position_control']['status'].startswith('LONG')
    assert snap['position_control']['recommended_action'] == 'REDUCE / PROTECT'
    assert snap['risk_authority']['mode'] == 'LOCKDOWN'


def test_renderer_shows_position_and_risk_blocks():
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
        'flip_prep_status': 'WATCHING', 'flip_prep_progress_bars': 0, 'flip_prep_confirm_bars_needed': 2, 'flip_prep_level': 71017.0,
        'top_signal': '⚠️ DANGER | 210$ до пробоя вниз — LONG под угрозой',
        'current_action_lines': ['• руками: не входить — ждать подтверждение'],
        'manual_action_lines': ['• действие: не входить — ждать подтверждение'],
        'bot_action_lines': ['• LONG grid: ENABLE', '• SHORT grid: HOLD'],
        'position_control': {'status': 'FLAT', 'source': 'none', 'entry_price': None, 'pnl_pct': 0.0, 'recommended_action': 'WAIT'},
        'risk_authority': {'lines': ['• MODE: LOCKDOWN', '• ADD: NO_ADD']},
        'if_then_plan': ['▶ ПРОБОЙ: закрытие < 71017.00 (2 бара) → SHORT | цель 71017.00'],
        'trade_plan': {'entry': 71017.0, 'add': 72000.0, 'tp1': 70500.0, 'tp2': 69500.0, 'invalidation': 74083.0},
        'scenario_alt_probability': 55, 'scenario_base_probability': 45, 'scenario_alt_text': 'пробой вниз', 'scenario_base_text': 'отбой',
    }
    text = render_full_report(snapshot)
    assert 'POSITION CONTROL:' not in text
    assert '⚡ ИСПОЛНЕНИЕ СЕЙЧАС:' in text
    assert '• MODE: LOCKDOWN' in text
    assert '• СЕТКИ:' in text
    assert '• ENTRY: 71017.0' in text
