from __future__ import annotations

from core.swing_reversal import build_swing_reversal_observe_context, detect_swing_reversal, scan_swing_reversal_trades
from core.backtest_engine import run_backtest_from_candles


def _candles() -> list[dict]:
    prices = [
        100.0, 99.5, 99.0, 98.5, 98.0, 97.6, 97.2, 97.0, 97.3, 97.8, 98.2, 98.7, 99.1, 99.5,
        100.0, 100.4, 100.8, 101.1, 101.4, 101.0, 100.7, 100.3, 99.9, 99.6, 99.3, 99.0, 98.8,
    ]
    rows = []
    for i, close in enumerate(prices):
        open_price = prices[i - 1] if i > 0 else close + 0.2
        rows.append({
            'open_time': i,
            'open': round(open_price, 4),
            'high': round(max(open_price, close) + 0.35, 4),
            'low': round(min(open_price, close) - 0.35, 4),
            'close': round(close, 4),
            'volume': 100 + i,
            'close_time': i + 1,
        })
    return rows


def test_swing_reversal_detects_candidate_inside_series():
    candles = _candles()
    ctx = detect_swing_reversal(candles, idx=10)
    assert ctx['candidate'] is True
    assert ctx['side'] == 'LONG'
    assert ctx['reason'] == 'SWING_LOW_CONFIRMED'


def test_swing_reversal_observe_context_returns_shape():
    candles = _candles()
    ctx = build_swing_reversal_observe_context(candles)
    assert 'candidate' in ctx
    assert 'reason' in ctx


def test_swing_reversal_scan_returns_trades():
    candles = _candles() * 8
    result = scan_swing_reversal_trades(candles)
    assert result['trades'] >= 1
    assert 'trades_data' in result


def test_backtest_report_contains_combined_validation(tmp_path):
    candles = _candles() * 8
    result = run_backtest_from_candles(candles, output_dir=tmp_path)
    assert 'swing_reversal_observe' in result
    assert 'combined_validation' in result
