import importlib
import sys
import types


def _install_stub(name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


def test_build_full_snapshot_runtime_hotfix(monkeypatch):
    market_data = _install_stub('market_data')
    price_feed = _install_stub('market_data.price_feed', get_price=lambda symbol: 105.0)
    ohlcv = _install_stub('market_data.ohlcv', get_klines=lambda symbol, interval, limit: [
        {'open': 90.0, 'close': 92.0, 'low': 89.0, 'high': 93.0},
        {'open': 92.0, 'close': 95.0, 'low': 91.0, 'high': 96.0},
        {'open': 95.0, 'close': 97.0, 'low': 94.0, 'high': 98.0},
        {'open': 97.0, 'close': 100.0, 'low': 96.0, 'high': 101.0},
        {'open': 100.0, 'close': 103.0, 'low': 99.0, 'high': 104.0},
        {'open': 103.0, 'close': 106.0, 'low': 102.0, 'high': 108.0},
    ])
    market_data.price_feed = price_feed
    market_data.ohlcv = ohlcv

    services = _install_stub('services')
    timeframe = _install_stub(
        'services.timeframe_aggregator',
        aggregate_to_4h=lambda candles: candles,
        aggregate_to_1d=lambda candles: candles,
    )
    services.timeframe_aggregator = timeframe

    features = _install_stub('features')
    trigger_detection = _install_stub('features.trigger_detection', detect_trigger=lambda *args, **kwargs: (False, None, None))
    forecast = _install_stub(
        'features.forecast',
        short_term_forecast=lambda candles: {'direction': 'SHORT'},
        session_forecast=lambda candles: {'direction': 'SHORT'},
        medium_forecast=lambda candles: {'direction': 'SHORT'},
        build_consensus=lambda short_fc, session_fc, medium_fc: ('SHORT', 78, {'SHORT': 3}, 3),
    )
    features.trigger_detection = trigger_detection
    features.forecast = forecast

    core_pkg = importlib.import_module('core')
    scenario = _install_stub(
        'core.scenario_handoff',
        compute_block_pressure=lambda *args, **kwargs: ('WITH', 'LOW', False, ''),
        compute_scenario_weights=lambda snapshot: (64, 36, ['base'], ['alt']),
        update_flip_prep=lambda prev_state, snapshot: {'flip_prep_status': 'NONE'},
    )
    setattr(core_pkg, 'scenario_handoff', scenario)

    storage = _install_stub('storage')
    state_store = _install_stub(
        'storage.market_state_store',
        load_market_state=lambda: {},
        save_market_state=lambda snapshot: None,
    )
    storage.market_state_store = state_store

    sys.modules.pop('core.pipeline', None)
    pipeline = importlib.import_module('core.pipeline')

    snapshot = pipeline.build_full_snapshot(symbol='BTCUSDT')

    assert snapshot['execution_side'] == 'SHORT'
    assert snapshot['ginarea']['long_grid'] == 'REDUCE'
    assert snapshot['ginarea']['short_grid'] == 'WORK'
