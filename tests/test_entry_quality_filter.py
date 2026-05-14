from __future__ import annotations

from pathlib import Path

import pytest

from core.entry_quality_filter import build_entry_quality_context, check_entry_filters
from core.backtest_engine import run_backtest_from_candles
from core import pipeline


def _candles(count: int = 140, base: float = 100.0, step: float = 0.1):
    rows = []
    price = base
    for i in range(count):
        open_price = price
        close_price = price + step
        rows.append({
            "open_time": i,
            "open": round(open_price, 4),
            "high": round(max(open_price, close_price) + 0.3, 4),
            "low": round(min(open_price, close_price) - 0.3, 4),
            "close": round(close_price, 4),
            "volume": 100.0,
            "close_time": i + 1,
        })
        price = close_price
    return rows


def test_entry_quality_filter_passes_without_climax_conditions():
    candles = _candles(count=20, base=100.0, step=0.25)
    ok, reason = check_entry_filters(candles, entry_idx=len(candles) - 1, side='LONG', lookback=8)
    assert ok is True
    assert reason == 'OK'


def test_entry_quality_filter_blocks_climax_volume_short():
    candles = _candles(count=20, base=100.0, step=-0.2)
    candles[-1]['volume'] = 260.0
    ctx = build_entry_quality_context(candles, entry_idx=len(candles) - 1, side='SHORT', lookback=8)
    assert ctx['ok'] is False
    assert ctx['reason_code'] == 'CLIMAX_VOLUME'


def test_backtest_engine_uses_entry_filter_veto(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    candles = _candles(count=150, base=100.0, step=0.25)

    calls = {'n': 0}

    def fake_snapshot(symbol: str = 'BTCUSDT'):
        calls['n'] += 1
        if calls['n'] == 1:
            return {
                'action': 'ENTER',
                'execution_side': 'LONG',
                'active_block': 'LONG',
                'trigger_type': 'RECLAIM',
                'trigger_blocked': False,
                'context_label': 'STRONG',
                'context_score': 3,
                'bias_score': 4,
                'session_side': 'LONG',
                'session_strength': 'MID',
                'range_low': 99.0,
                'entry_filter_ok': False,
                'entry_filter_reason': 'CLIMAX_VOLUME (объём 2.20x при движении 1.30% в сторону входа)',
                'entry_filter_reason_code': 'CLIMAX_VOLUME',
                'if_then_layer': {'scenarios': [{'side': 'LONG', 'entry': 100.0, 'invalidation': 99.0}]},
            }
        return {
            'action': 'WAIT',
            'execution_side': 'LONG',
            'active_block': 'LONG',
            'trigger_type': 'NONE',
            'trigger_blocked': False,
            'context_label': 'STRONG',
            'context_score': 3,
            'bias_score': 4,
            'session_side': 'LONG',
            'session_strength': 'MID',
            'range_low': 99.0,
            'if_then_layer': {'scenarios': []},
        }

    monkeypatch.setattr(pipeline, 'build_full_snapshot', fake_snapshot)
    result = run_backtest_from_candles(candles, output_dir=tmp_path)
    assert result['trades'] == 0
    assert result['if_then_failed'] >= 1
