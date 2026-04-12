from features.structural_context import analyze_structural_context


def _c(o, h, l, c, v):
    return {"open": o, "high": h, "low": l, "close": c, "volume": v}


def test_detects_repeated_upper_rejections_as_short_bias():
    candles = [
        _c(100, 101, 99, 100.5, 100),
        _c(100.5, 101.2, 100, 100.9, 100),
        _c(100.9, 104.0, 100.8, 101.1, 180),
        _c(101.1, 101.6, 100.7, 101.0, 90),
        _c(101.0, 104.2, 100.9, 101.2, 190),
        _c(101.2, 101.8, 100.6, 100.8, 95),
        _c(100.8, 104.1, 100.7, 101.0, 210),
        _c(101.0, 101.3, 100.3, 100.5, 110),
    ]
    result = analyze_structural_context(candles, lookback=8)
    assert result['bias'] == 'SHORT'
    assert result['phase'] == 'DISTRIBUTION'
    assert result['upper_rejections_count'] >= 2


def test_grid_layers_follow_impulse_thresholds():
    candles = [
        _c(100, 100.5, 99.5, 100.1, 100),
        _c(100.1, 100.4, 99.8, 100.0, 100),
        _c(100.0, 100.2, 97.0, 99.1, 130),
        _c(99.1, 99.4, 96.8, 97.5, 150),
        _c(97.5, 98.0, 96.5, 97.0, 160),
        _c(97.0, 97.2, 95.2, 95.5, 155),
    ]
    result = analyze_structural_context(candles, lookback=6)
    assert result['impulse_down_pct'] >= 1.3
    assert result['grid_trigger_down'] >= 1
