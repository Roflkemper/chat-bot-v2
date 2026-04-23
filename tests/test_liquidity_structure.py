from features.liquidity_structure import detect_liquidity_structure


def test_detects_upper_rejection_distribution():
    candles = []
    price = 71000.0
    for i in range(40):
        candles.append({
            'open': price,
            'high': price + 120,
            'low': price - 120,
            'close': price + (10 if i % 2 == 0 else -10),
            'volume': 1000 + i,
        })
    # inject repeated upper rejections near same high with higher volume
    candles[-5] = {'open': 71800, 'high': 72100, 'low': 71680, 'close': 71740, 'volume': 1700}
    candles[-3] = {'open': 71820, 'high': 72110, 'low': 71700, 'close': 71730, 'volume': 1800}
    candles[-1] = {'open': 71840, 'high': 72120, 'low': 71690, 'close': 71710, 'volume': 1900}
    result = detect_liquidity_structure(candles)
    assert result['repeated_upper_rejection'] is True
    assert result['volume_rejection_up'] is True
    assert result['distribution'] is True
