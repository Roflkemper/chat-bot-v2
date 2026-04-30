from services.managed_grid_sim.regime_classifier import RegimeClassifier


def test_classify_compression_with_low_atr(sample_bars):
    bars = sample_bars[:20]
    for idx, bar in enumerate(bars):
        bars[idx] = bar._replace(close=100.0, high=100.1, low=99.9, volume=10.0)
    regime, trend = RegimeClassifier().classify(bars)
    assert regime.value == "compression"
    assert trend.value == "smooth_trending"


def test_classify_trend_up_with_positive_delta(sample_bars):
    regime, trend = RegimeClassifier().classify(sample_bars)
    assert regime.value == "trend_up"
    assert trend.value in {"volatile_trending", "smooth_trending"}


def test_classify_cascade_with_high_volume(sample_bars):
    bars = list(sample_bars)
    last = bars[-1]
    bars[-1] = last._replace(close=last.close * 1.03, high=last.high * 1.03, volume=10000.0)
    regime, trend = RegimeClassifier().classify(bars)
    assert regime.value == "cascade_up"
    assert trend.value == "cascade_driven"
