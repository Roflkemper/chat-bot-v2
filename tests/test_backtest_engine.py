from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.backtest_engine import format_backtest_summary, run_backtest_from_candles
from core import pipeline


def _candles(count: int = 260, start: float = 100.0):
    data = []
    price = start
    for i in range(count):
        drift = 0.35 if i % 18 < 9 else -0.22
        open_price = price
        close_price = max(1.0, price + drift)
        high = max(open_price, close_price) + 0.8
        low = min(open_price, close_price) - 0.8
        data.append(
            {
                'open_time': i,
                'open': round(open_price, 4),
                'high': round(high, 4),
                'low': round(low, 4),
                'close': round(close_price, 4),
                'volume': 100 + i,
                'close_time': i + 1,
            }
        )
        price = close_price
    return data


def test_backtest_engine_returns_non_nan_metrics_and_writes_report(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    candles = _candles()

    def fake_snapshot(symbol: str = 'BTCUSDT'):
        return {
            'action': 'WAIT',
            'execution_side': 'SHORT',
            'active_block': 'SHORT',
            'watch_side': 'LONG',
            'consensus_direction': 'LONG',
            'block_pressure': 'AGAINST',
            'block_pressure_strength': 'HIGH',
            'range_mid': candles[-1]['close'] - 0.2,
            'trigger_type': 'NONE',
            'trigger_blocked': False,
            'context_label': 'STRONG',
            'context_score': 3,
            'bias_score': 3,
            'session_side': 'LONG',
            'session_strength': 'LOW',
            'if_then_layer': {'scenarios': [{'side': 'LONG', 'entry': 100.0, 'invalidation': 99.0}]},
        }

    monkeypatch.setattr(pipeline, 'build_full_snapshot', fake_snapshot)
    result = run_backtest_from_candles(candles, output_dir=tmp_path)
    assert isinstance(result['trades'], int)
    assert result['trades'] > 0
    assert result['if_then_triggered'] > 0
    assert result['if_then_executed'] > 0
    assert result['if_then_closed'] == result['trades']
    assert isinstance(result['winrate'], float)
    assert isinstance(result['avg_rr'], float)
    assert isinstance(result['pnl_pct'], float)
    assert result['report_path']
    report = Path(result['report_path'])
    assert report.exists()
    payload = json.loads(report.read_text(encoding='utf-8'))
    assert 'summary' in payload
    assert 'trades' in payload


def test_backtest_summary_formatter_contains_if_then_block():
    lines = format_backtest_summary(
        {
            'trades': 12,
            'winrate': 58.3,
            'avg_rr': 1.24,
            'pnl_pct': 7.1,
            'max_drawdown_pct': 2.6,
            'if_then_triggered': 8,
            'if_then_armed': 7,
            'if_then_executed': 5,
            'if_then_closed': 4,
            'if_then_failed': 3,
            'tp_hit_count': 2,
            'stop_count': 1,
            'timeout_count': 1,
        }
    )
    text = '\n'.join(lines)
    assert 'BACKTEST 90D' in text
    assert 'IF-THEN:' in text
    assert 'triggered: 8' in text
    assert 'armed: 7' in text
    assert 'closed: 4' in text
    assert 'tp_hit: 2' in text


def test_backtest_engine_records_exit_reasons(tmp_path: Path):
    result = run_backtest_from_candles(_candles(320), output_dir=tmp_path)
    if result['trades_data']:
        reasons = {x['exit_reason'] for x in result['trades_data']}
        assert reasons <= {'EXIT_SIGNAL', 'SIDE_FLIP', 'MOMENTUM_EXHAUSTED', 'STOP', 'TIMEOUT', 'TP_HIT'}


def test_backtest_engine_rejects_empty_signal_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    candles = _candles(320)

    def fake_snapshot(symbol: str = 'BTCUSDT'):
        return {
            'action': 'WAIT',
            'execution_side': 'SHORT',
            'active_block': 'SHORT',
            'watch_side': 'LONG',
            'consensus_direction': 'LONG',
            'block_pressure': 'AGAINST',
            'block_pressure_strength': 'HIGH',
            'range_mid': candles[-1]['close'] - 0.2,
            'trigger_type': 'NONE',
            'trigger_blocked': False,
            'context_label': 'STRONG',
            'context_score': 3,
            'bias_score': 3,
            'session_side': 'LONG',
            'session_strength': 'LOW',
            'if_then_layer': {'scenarios': [{'side': 'LONG', 'entry': 100.0, 'invalidation': 99.0}]},
        }

    monkeypatch.setattr(pipeline, 'build_full_snapshot', fake_snapshot)
    result = run_backtest_from_candles(candles, output_dir=tmp_path)
    assert result['trades'] > 0
    assert result['if_then_triggered'] > 0
    assert result['if_then_executed'] > 0


def test_backtest_hits_tp_before_timeout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    candles = _candles(140)
    candles[121]['high'] = candles[121]['close'] + 4.5
    candles[121]['low'] = candles[121]['close'] + 0.6

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
                'range_low': 108.5,
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
            'range_low': 108.5,
            'if_then_layer': {'scenarios': [{'side': 'LONG', 'entry': 100.0, 'invalidation': 99.0}]},
        }

    monkeypatch.setattr(pipeline, 'build_full_snapshot', fake_snapshot)
    result = run_backtest_from_candles(candles, output_dir=tmp_path)
    reasons = [x['exit_reason'] for x in result['trades_data']]
    assert 'TP_HIT' in reasons


def test_backtest_filters_weak_context_low_bias_and_session_conflict(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    candles = _candles(140)
    snapshots = [
        {
            'action': 'ENTER',
            'execution_side': 'LONG',
            'active_block': 'LONG',
            'trigger_type': 'RECLAIM',
            'trigger_blocked': False,
            'context_label': 'WEAK',
            'context_score': 1,
            'bias_score': 4,
            'session_side': 'LONG',
            'session_strength': 'LOW',
            'range_low': 99.0,
            'if_then_layer': {'scenarios': [{'side': 'LONG', 'entry': 100.0, 'invalidation': 99.0}]},
        },
        {
            'action': 'ENTER',
            'execution_side': 'LONG',
            'active_block': 'LONG',
            'trigger_type': 'RECLAIM',
            'trigger_blocked': False,
            'context_label': 'VALID',
            'context_score': 2,
            'bias_score': 1,
            'session_side': 'LONG',
            'session_strength': 'LOW',
            'range_low': 99.0,
            'if_then_layer': {'scenarios': [{'side': 'LONG', 'entry': 100.0, 'invalidation': 99.0}]},
        },
        {
            'action': 'ENTER',
            'execution_side': 'LONG',
            'active_block': 'LONG',
            'trigger_type': 'RECLAIM',
            'trigger_blocked': False,
            'context_label': 'VALID',
            'context_score': 2,
            'bias_score': 4,
            'session_side': 'SHORT',
            'session_strength': 'HIGH',
            'range_low': 99.0,
            'if_then_layer': {'scenarios': [{'side': 'LONG', 'entry': 100.0, 'invalidation': 99.0}]},
        },
    ]

    def fake_snapshot(symbol: str = 'BTCUSDT'):
        if snapshots:
            return snapshots.pop(0)
        return {
            'action': 'WAIT',
            'execution_side': 'NONE',
            'active_block': 'NONE',
            'trigger_type': 'NONE',
            'trigger_blocked': False,
            'context_label': 'WEAK',
            'context_score': 0,
            'bias_score': 0,
            'session_side': 'NEUTRAL',
            'session_strength': 'LOW',
            'if_then_layer': {'scenarios': []},
        }

    monkeypatch.setattr(pipeline, 'build_full_snapshot', fake_snapshot)
    result = run_backtest_from_candles(candles, output_dir=tmp_path)
    assert result['trades'] == 0
    assert result['if_then_failed'] >= 3


def test_backtest_partial_and_be_reduce_timeout_damage(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    candles = _candles(150)
    candles[121]['high'] = candles[121]['close'] + 1.5
    candles[121]['low'] = candles[121]['close'] + 0.6
    candles[122]['low'] = candles[121]['close'] + 0.1

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
                'range_low': 108.5,
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
            'range_low': 108.5,
            'if_then_layer': {'scenarios': [{'side': 'LONG', 'entry': 100.0, 'invalidation': 99.0}]},
        }

    monkeypatch.setattr(pipeline, 'build_full_snapshot', fake_snapshot)
    result = run_backtest_from_candles(candles, output_dir=tmp_path)
    assert result['trades'] >= 1
    trade = result['trades_data'][0]
    assert trade['partial_taken'] is True
    assert trade['be_armed'] is True
    assert trade['pnl_pct'] >= 0


def test_backtest_flip_sources_need_stronger_quality(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    candles = _candles(150)
    candles[120]['close'] = 100.0
    candles[121]['close'] = 101.0

    def fake_snapshot(symbol: str = 'BTCUSDT'):
        return {
            'action': 'WAIT',
            'execution_side': 'SHORT',
            'active_block': 'SHORT',
            'watch_side': 'LONG',
            'consensus_direction': 'LONG',
            'block_pressure': 'AGAINST',
            'block_pressure_strength': 'LOW',
            'range_mid': 100.5,
            'trigger_type': 'NONE',
            'trigger_blocked': False,
            'context_label': 'VALID',
            'context_score': 2,
            'bias_score': 2,
            'session_side': 'LONG',
            'session_strength': 'LOW',
            'if_then_layer': {'scenarios': [{'side': 'LONG', 'entry': 100.0, 'invalidation': 99.0}]},
        }

    monkeypatch.setattr(pipeline, 'build_full_snapshot', fake_snapshot)
    result = run_backtest_from_candles(candles, output_dir=tmp_path)
    assert result['trades'] == 0
    assert result['if_then_failed'] > 0


def test_backtest_expectancy_targets_keep_tp_profile_consistent():
    from core.backtest_engine import _tp_pct, _tp1_pct

    stop_pct = 0.8
    tp2_pct = _tp_pct({}, stop_pct, 'LONG', atr_pct=0.55)
    tp1_pct = _tp1_pct(stop_pct, tp2_pct, atr_pct=0.55)

    assert tp1_pct >= stop_pct
    assert tp2_pct >= round(stop_pct * 1.8, 4)
    assert tp2_pct <= round(stop_pct * 2.2, 4)
    assert tp1_pct < tp2_pct


def test_backtest_timeout_protects_mature_winner_longer():
    from core.backtest_engine import _dynamic_timeout_bars, _timeout_exit_allowed

    position = {
        'entry_price': 100.0,
        'side': 'LONG',
        'stop_pct': 0.8,
        'tp1_pct': 0.8,
        'tp2_pct': 1.6,
        'be_buffer_pct': 0.35,
        'base_timeout_bars': 12,
        'partial_taken': True,
    }

    dynamic_timeout = _dynamic_timeout_bars(position, current_price=101.0, atr_pct=0.4)
    assert dynamic_timeout >= 24
    assert _timeout_exit_allowed(position, current_price=101.0, held_bars=dynamic_timeout, atr_pct=0.4) is False
    assert _timeout_exit_allowed(position, current_price=101.0, held_bars=int(dynamic_timeout * 1.8), atr_pct=0.4) is True


def test_backtest_timeout_runner_protection_uses_peak_progress():
    from core.backtest_engine import _update_timeout_state, _dynamic_timeout_bars, _timeout_exit_allowed

    position = {
        'entry_price': 100.0,
        'side': 'LONG',
        'stop_pct': 0.8,
        'tp1_pct': 1.0,
        'tp2_pct': 1.9,
        'be_buffer_pct': 0.35,
        'base_timeout_bars': 12,
        'partial_taken': False,
        'peak_progress': 0.0,
        'peak_pnl_pct': 0.0,
        'last_progress_held_bars': 0,
    }

    _update_timeout_state(position, current_price=101.1, held_bars=10)
    dynamic_timeout = _dynamic_timeout_bars(position, current_price=100.18, atr_pct=0.55)
    assert dynamic_timeout >= 22
    assert _timeout_exit_allowed(position, current_price=100.18, held_bars=dynamic_timeout, atr_pct=0.55) is False
    assert _timeout_exit_allowed(position, current_price=100.18, held_bars=int(dynamic_timeout * 1.7), atr_pct=0.55) is True


def test_backtest_timeout_dead_trade_closes_on_base_timeout():
    from core.backtest_engine import _update_timeout_state, _dynamic_timeout_bars, _timeout_exit_allowed

    position = {
        'entry_price': 100.0,
        'side': 'LONG',
        'stop_pct': 0.8,
        'tp1_pct': 1.0,
        'tp2_pct': 1.9,
        'be_buffer_pct': 0.35,
        'base_timeout_bars': 12,
        'partial_taken': False,
        'peak_progress': 0.0,
        'peak_pnl_pct': 0.0,
        'last_progress_held_bars': 0,
    }

    _update_timeout_state(position, current_price=100.05, held_bars=12)
    dynamic_timeout = _dynamic_timeout_bars(position, current_price=100.05, atr_pct=0.7)
    assert dynamic_timeout == 12
    assert _timeout_exit_allowed(position, current_price=100.05, held_bars=12, atr_pct=0.7) is True


def test_dead_trade_exit_allows_small_green_compressed_trade():
    from core.backtest_engine import _dead_trade_exit_allowed

    position = {
        'side': 'LONG',
        'entry_price': 100.0,
        'partial_taken': False,
        'tp2_taken': False,
        'entry_atr_pct': 0.8,
        'dead_trade_min_bars': 8,
        'dead_trade_max_profit_pct': 0.35,
        'dead_trade_compression_ratio': 0.75,
        'peak_progress': 0.2,
        'peak_pnl_pct': 0.22,
    }
    assert _dead_trade_exit_allowed(position, current_price=100.2, held_bars=8, atr_pct=0.5) is True


def test_dead_trade_exit_ignored_after_partial():
    from core.backtest_engine import _dead_trade_exit_allowed

    position = {
        'side': 'LONG',
        'entry_price': 100.0,
        'partial_taken': True,
        'tp2_taken': False,
        'entry_atr_pct': 0.8,
        'dead_trade_min_bars': 8,
        'dead_trade_max_profit_pct': 0.35,
        'dead_trade_compression_ratio': 0.75,
        'peak_progress': 0.5,
        'peak_pnl_pct': 0.9,
    }
    assert _dead_trade_exit_allowed(position, current_price=100.2, held_bars=12, atr_pct=0.4) is False


def test_tp2_allows_tp3_tail_for_markup_long():
    from core.backtest_engine import _apply_intrabar_management

    position = {
        'side': 'LONG',
        'entry_price': 100.0,
        'stop_pct': 1.0,
        'tp1_pct': 1.0,
        'tp2_pct': 2.0,
        'partial_taken': True,
        'tp1_hit_index': 1,
        'be_armed': True,
        'be_buffer_pct': 0.35,
        'partial_size': 0.30,
        'remaining_size': 0.70,
        'realized_pnl_pct': 0.30,
        'tp3_enabled': True,
        'tp3_tail_size': 0.10,
        'tp2_taken': False,
    }
    bar = {'open': 101.5, 'high': 102.2, 'low': 101.2, 'close': 102.0}
    reason, price, updated = _apply_intrabar_management(position, bar, current_index=5)
    assert reason is None
    assert price is None
    assert updated['tp2_taken'] is True
    assert updated['remaining_size'] == 0.10
    assert updated['realized_pnl_pct'] > 1.4
