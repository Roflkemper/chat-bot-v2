from core import pipeline


def _c(o, h, l, c, v=100):
    return {"open": o, "high": h, "low": l, "close": c, "volume": v}


def test_wait_when_structure_conflicts_with_long_block(monkeypatch):
    candles = [
        _c(100, 101, 99, 100.4),
        _c(100.4, 101.1, 100.0, 100.8),
        _c(100.8, 104.0, 100.7, 101.0, 180),
        _c(101.0, 101.3, 100.4, 100.9),
        _c(100.9, 104.2, 100.8, 101.1, 190),
        _c(101.1, 101.4, 100.5, 101.0),
        _c(101.0, 104.1, 100.9, 101.0, 210),
        _c(101.0, 101.1, 99.0, 99.2, 160),
    ]

    monkeypatch.setattr(pipeline, 'get_price', lambda symbol: 99.2)
    monkeypatch.setattr(pipeline, 'get_klines', lambda symbol, interval, limit: candles * 30)
    monkeypatch.setattr(pipeline, 'aggregate_to_4h', lambda x: x[-20:])
    monkeypatch.setattr(pipeline, 'aggregate_to_1d', lambda x: x[-20:])
    monkeypatch.setattr(pipeline, 'detect_trigger', lambda *args, **kwargs: (False, None, 'подтверждённого reject/reclaim ещё нет'))
    monkeypatch.setattr(pipeline, 'short_term_forecast', lambda x: {'direction': 'NEUTRAL', 'strength': 'LOW', 'note': 'n'})
    monkeypatch.setattr(pipeline, 'session_forecast', lambda x: {'direction': 'LONG', 'strength': 'MID', 'note': 'n'})
    monkeypatch.setattr(pipeline, 'medium_forecast', lambda x: {'direction': 'LONG', 'strength': 'MID', 'phase': 'MARKUP', 'note': 'n'})
    monkeypatch.setattr(pipeline, 'build_consensus', lambda a, b, c: ('LONG', 'MID', '2/3', 2))
    monkeypatch.setattr(pipeline, 'compute_block_pressure', lambda *args, **kwargs: ('WITH', 'LOW', False, ''))
    monkeypatch.setattr(pipeline, 'load_market_state', lambda: {})
    monkeypatch.setattr(pipeline, 'save_market_state', lambda x: None)
    monkeypatch.setattr(pipeline, 'update_flip_prep', lambda prev, base: {'flip_prep_status': 'IDLE'})
    monkeypatch.setattr(pipeline, 'compute_scenario_weights', lambda base: (45, 55, [], []))

    snap = pipeline.build_full_snapshot('BTCUSDT')
    assert snap['active_side'] == 'LONG'
    assert snap['structural_context']['bias'] == 'SHORT'
    assert snap['action'] == 'WAIT'
    assert snap['trigger_block_reason'] == 'структура 1h против активного блока'
    assert snap['ginarea']['priority_side'] == 'SHORT'
