from core import pipeline
from renderers.renderer import render_full_report


def _c(o, h, l, c, v=100):
    return {"open": o, "high": h, "low": l, "close": c, "volume": v}


def test_snapshot_contains_manual_grid_and_liquidity_blocks(monkeypatch):
    candles = [_c(100, 101, 99, 100.4)] * 180 + [_c(100.4, 101.0, 98.8, 99.1, 150)] * 20

    monkeypatch.setattr(pipeline, 'get_price', lambda symbol: 99.2)
    monkeypatch.setattr(pipeline, 'get_klines', lambda symbol, interval, limit: candles)
    monkeypatch.setattr(pipeline, 'aggregate_to_4h', lambda x: x[-20:])
    monkeypatch.setattr(pipeline, 'aggregate_to_1d', lambda x: x[-20:])
    monkeypatch.setattr(pipeline, 'detect_trigger', lambda *args, **kwargs: (False, None, 'подтверждённого reject/reclaim ещё нет'))
    monkeypatch.setattr(pipeline, 'short_term_forecast', lambda x: {'direction': 'SHORT', 'strength': 'HIGH', 'note': 'n'})
    monkeypatch.setattr(pipeline, 'session_forecast', lambda x: {'direction': 'SHORT', 'strength': 'HIGH', 'note': 'n'})
    monkeypatch.setattr(pipeline, 'medium_forecast', lambda x: {'direction': 'LONG', 'strength': 'MID', 'phase': 'MARKUP', 'note': 'n'})
    monkeypatch.setattr(pipeline, 'build_consensus', lambda a, b, c: ('SHORT', 'MID', '2/3', 2))
    monkeypatch.setattr(pipeline, 'compute_block_pressure', lambda *args, **kwargs: ('AGAINST', 'MID', True, 'давление на смену зоны'))
    monkeypatch.setattr(pipeline, 'load_market_state', lambda: {})
    monkeypatch.setattr(pipeline, 'save_market_state', lambda x: None)
    monkeypatch.setattr(pipeline, 'update_flip_prep', lambda prev, base: {'flip_prep_status': 'WATCHING', 'flip_prep_progress_bars': 0, 'flip_prep_confirm_bars_needed': 2, 'flip_prep_level': 99.0})

    snap = pipeline.build_full_snapshot('BTCUSDT')

    assert snap['manual_action_lines']
    assert snap['grid_action_lines']
    assert snap['grid_shift_lines']
    assert snap['liquidity_void_lines']
    text = render_full_report(snap)
    assert '⚡ ИСПОЛНЕНИЕ СЕЙЧАС:' in text
    assert '• СЕТКИ:' in text
    assert 'GRID SHIFT / AUTHORITY:' in text
    assert 'LIQUIDITY VOID / NEXT DESTINATION:' in text


def test_edge_pressure_reduces_base_probability():
    snap = {
        'block_pressure': 'AGAINST',
        'block_pressure_strength': 'MID',
        'consensus_direction': 'SHORT',
        'active_block': 'LONG',
        'consensus_alignment_count': 2,
        'depth_label': 'WORK',
        'block_depth_pct': 12.0,
        'range_position_pct': 8.0,
        'forecast': {
            'short': {'direction': 'SHORT', 'strength': 'HIGH'},
            'session': {'direction': 'SHORT', 'strength': 'HIGH'},
            'medium': {'direction': 'LONG', 'phase': 'MARKUP'},
        },
        'hedge_state': 'ARM',
        'trigger_type': '',
        'flip_prep_status': 'WATCHING',
        'absorption': {'is_active': False},
    }
    base_prob, alt_prob, _, reasons = pipeline.compute_scenario_weights(snap)
    assert alt_prob > base_prob
    assert any('локальных ТФ' in x for x in reasons)
