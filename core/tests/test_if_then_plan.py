from core.if_then_plan import build_if_then_plan
from core import pipeline


def _snapshot(**overrides):
    data = {
        'action': 'PREPARE',
        'active_block': 'LONG',
        'execution_side': 'LONG',
        'watch_side': 'SHORT',
        'trigger_type': 'RECLAIM',
        'trigger_blocked': False,
        'trigger_block_reason': '',
        'context_label': 'MID',
        'context_score': 2,
        'block_pressure': 'WITH',
        'block_pressure_strength': 'LOW',
        'range_low': 71017.0,
        'range_high': 74083.0,
        'range_mid': 72550.0,
        'break_level': 71017.0,
        'price': 71210.0,
        'consensus_direction': 'SHORT',
        'flip_prep_confirm_bars_needed': 2,
        'flip_prep_status': 'WATCHING',
    }
    data.update(overrides)
    return data


def test_if_then_plan_builds_separate_layer_with_structured_scenarios():
    plan = build_if_then_plan(_snapshot())
    assert plan['layer'] == 'IF_THEN_PLAN'
    assert len(plan['scenarios']) == 2
    assert plan['scenarios'][0]['then_action'] == 'PREPARE'
    assert plan['scenarios'][1]['then_action'] == 'PREPARE'
    text = '\n'.join(plan['lines'])
    assert 'IF:' in text
    assert 'THEN: действие PREPARE' in text
    assert 'THEN: invalidation' in text
    assert 'если не реализовалось' in text


def test_if_then_plan_wait_scenario_stays_non_executable_when_trigger_is_blocked():
    plan = build_if_then_plan(_snapshot(action='WAIT', trigger_blocked=True, trigger_block_reason='forecast против активного блока'))
    primary = plan['scenarios'][0]
    assert primary['then_action'] == 'WAIT'
    assert 'сценарий не активен' in primary['then_invalidation']
    assert 'ждать новый trigger' in primary['then_fallback']


def test_pipeline_exposes_if_then_layer_without_changing_decision_action(monkeypatch):
    candles = [{"open": 100, "high": 101, "low": 99, "close": 100.5, "volume": 100}] * 60
    monkeypatch.setattr(pipeline, 'get_price', lambda symbol: 100.2)
    monkeypatch.setattr(pipeline, 'get_klines', lambda symbol, interval, limit: candles)
    monkeypatch.setattr(pipeline, 'aggregate_to_4h', lambda x: x[-20:])
    monkeypatch.setattr(pipeline, 'aggregate_to_1d', lambda x: x[-20:])
    monkeypatch.setattr(pipeline, 'detect_trigger', lambda *args, **kwargs: (False, None, 'нет сигнала'))
    monkeypatch.setattr(pipeline, 'short_term_forecast', lambda x: {'direction': 'NEUTRAL', 'strength': 'LOW', 'note': 'n'})
    monkeypatch.setattr(pipeline, 'session_forecast', lambda x: {'direction': 'NEUTRAL', 'strength': 'LOW', 'note': 'n'})
    monkeypatch.setattr(pipeline, 'medium_forecast', lambda x: {'direction': 'NEUTRAL', 'strength': 'LOW', 'phase': 'RANGE', 'note': 'n'})
    monkeypatch.setattr(pipeline, 'build_consensus', lambda a, b, c: ('NONE', 'LOW', '0/3', 0))
    monkeypatch.setattr(pipeline, 'compute_block_pressure', lambda *args, **kwargs: ('NONE', 'LOW', False, ''))
    monkeypatch.setattr(pipeline, 'analyze_structural_context', lambda x: {'bias': 'NEUTRAL', 'strength': 'LOW'})
    monkeypatch.setattr(pipeline, 'detect_liquidity_structure', lambda x: {})
    monkeypatch.setattr(pipeline, 'load_market_state', lambda: {})
    monkeypatch.setattr(pipeline, 'load_position_state', lambda: {'active': False})
    monkeypatch.setattr(pipeline, 'save_market_state', lambda x: None)
    monkeypatch.setattr(pipeline, 'update_flip_prep', lambda prev, base: {'flip_prep_status': 'IDLE'})
    monkeypatch.setattr(pipeline, 'compute_scenario_weights', lambda base: (50, 50, [], []))

    snap = pipeline.build_full_snapshot('BTCUSDT')
    assert snap['action'] == 'WAIT'
    assert snap['if_then_layer']['layer'] == 'IF_THEN_PLAN'
    assert len(snap['if_then_layer']['scenarios']) == 2
    assert snap['if_then_plan'] == snap['if_then_layer']['lines']
