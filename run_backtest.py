from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from core.backtest_engine import bars_for_days, run_backtest, run_backtest_from_candles
from market_data.ohlcv import get_klines

DEFAULT_SYMBOL = 'BTCUSDT'
DEFAULT_MULTI_SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'XRPUSDT']
DEFAULT_TIMEFRAME = '1h'
DEFAULT_LOOKBACK_DAYS = 90
DEFAULT_OUTPUT_DIR = 'backtests'


def _default_frozen_path(symbol: str, timeframe: str, lookback_days: int, output_dir: str | Path = DEFAULT_OUTPUT_DIR) -> Path:
    return Path(output_dir) / 'frozen' / f'{symbol}_{timeframe}_{lookback_days}d_frozen.json'


def _load_frozen_candles(path: Path) -> List[Dict[str, Any]]:
    payload = json.loads(path.read_text(encoding='utf-8'))
    if isinstance(payload, dict) and isinstance(payload.get('candles'), list):
        return list(payload['candles'])
    if isinstance(payload, list):
        return list(payload)
    raise ValueError(f'Unsupported frozen data format: {path.as_posix()}')


def _save_frozen_candles(
    path: Path,
    *,
    candles: List[Dict[str, Any]],
    symbol: str,
    timeframe: str,
    lookback_days: int,
    source: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        'meta': {
            'symbol': symbol,
            'timeframe': timeframe,
            'lookback_days': lookback_days,
            'bars': len(candles),
            'source': source,
        },
        'candles': list(candles),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')


def _parse_symbols(raw: str) -> List[str]:
    values = [x.strip().upper() for x in str(raw or '').split(',') if x.strip()]
    return values or list(DEFAULT_MULTI_SYMBOLS)


def _augment_trades_with_symbol(trades: List[Dict[str, Any]], symbol: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for trade in list(trades or []):
        row = dict(trade or {})
        row['symbol'] = symbol
        rows.append(row)
    return rows


def _load_trace_events(path: str | Path, symbol: str) -> List[Dict[str, Any]]:
    if not path:
        return []
    trace_path = Path(path)
    if not trace_path.exists():
        return []
    payload = json.loads(trace_path.read_text(encoding='utf-8'))
    rows: List[Dict[str, Any]] = []
    for event in list(payload or []):
        row = dict(event or {})
        row['symbol'] = symbol
        rows.append(row)
    return rows


def _combined_summary_lines(summary: Dict[str, Any], per_symbol: Dict[str, Dict[str, Any]]) -> List[str]:
    symbols = ', '.join(summary.get('symbols') or [])
    lines = [
        f"BACKTEST MULTI {summary.get('lookback_days', 90)}D",
        f"Symbols: {symbols}",
        f"Trades: {summary.get('trades', 0)}",
        f"Winrate: {summary.get('winrate', 0.0)}%",
        f"Avg RR: {summary.get('avg_rr', 0.0)}",
        f"PnL: {summary.get('pnl_pct', 0.0)}%",
        f"Max DD: -{summary.get('max_drawdown_pct', 0.0)}%",
        'PER SYMBOL:',
    ]
    for symbol, item in per_symbol.items():
        lines.append(
            f"- {symbol}: trades={item.get('trades', 0)} | wr={item.get('winrate', 0.0)}% | pnl={item.get('pnl_pct', 0.0)}% | dd={item.get('max_drawdown_pct', 0.0)}%"
        )
    return lines


def _run_single_backtest(
    *,
    symbol: str,
    timeframe: str,
    lookback_days: int,
    output_dir: Path,
    mode: str,
    data_file: Path,
    save_frozen: bool,
) -> tuple[Dict[str, Any], str]:
    source_label = 'LIVE_BINANCE'
    if mode in {'auto', 'frozen'} and data_file.exists():
        candles = _load_frozen_candles(data_file)
        source_label = f'FROZEN:{data_file.as_posix()}'
        result = run_backtest_from_candles(
            candles,
            symbol=symbol,
            timeframe=timeframe,
            lookback_days=lookback_days,
            output_dir=output_dir,
        )
    elif mode == 'frozen':
        raise SystemExit(f'[ERROR] Frozen data file not found: {data_file.as_posix()}')
    else:
        result = run_backtest(
            symbol=symbol,
            timeframe=timeframe,
            lookback_days=lookback_days,
            output_dir=output_dir,
        )
        if save_frozen:
            bars = bars_for_days(lookback_days, timeframe)
            bars = bars + 120 + 12 + 10
            candles = get_klines(symbol=symbol, interval=timeframe, limit=bars)
            _save_frozen_candles(
                data_file,
                candles=candles,
                symbol=symbol,
                timeframe=timeframe,
                lookback_days=lookback_days,
                source='LIVE_FETCH_SAVED',
            )
            source_label = f'LIVE_BINANCE -> SAVED:{data_file.as_posix()}'
    result['symbol'] = symbol
    result['trades_data'] = _augment_trades_with_symbol(result.get('trades_data') or [], symbol)
    return result, source_label


def _run_multi_backtest(
    *,
    symbols: List[str],
    timeframe: str,
    lookback_days: int,
    output_dir: Path,
) -> tuple[Dict[str, Any], List[str]]:
    combined_trades: List[Dict[str, Any]] = []
    combined_trace: List[Dict[str, Any]] = []
    per_symbol: Dict[str, Dict[str, Any]] = {}
    source_labels: List[str] = []
    total_trades = 0
    total_pnl = 0.0
    total_rr = 0.0
    total_wins = 0
    total_prepare = 0
    total_enter = 0
    total_exit_signal = 0
    total_triggered = 0
    total_armed = 0
    total_executed = 0
    total_closed = 0
    total_failed = 0
    total_momentum_exit = 0
    total_timeout = 0
    total_tp_hit = 0
    total_stop = 0
    max_drawdown = 0.0
    bars_by_symbol: Dict[str, int] = {}

    for symbol in symbols:
        data_file = _default_frozen_path(symbol, timeframe, lookback_days, output_dir)
        result, source_label = _run_single_backtest(
            symbol=symbol,
            timeframe=timeframe,
            lookback_days=lookback_days,
            output_dir=output_dir,
            mode='frozen',
            data_file=data_file,
            save_frozen=False,
        )
        source_labels.append(f'{symbol}={source_label}')
        per_symbol[symbol] = {
            'symbol': symbol,
            'trades': int(result.get('trades', 0)),
            'winrate': float(result.get('winrate', 0.0)),
            'avg_rr': float(result.get('avg_rr', 0.0)),
            'pnl_pct': float(result.get('pnl_pct', 0.0)),
            'max_drawdown_pct': float(result.get('max_drawdown_pct', 0.0)),
            'if_then_triggered': int(result.get('if_then_triggered', 0)),
            'if_then_executed': int(result.get('if_then_executed', 0)),
            'if_then_failed': int(result.get('if_then_failed', 0)),
            'report_path': result.get('report_path') or '',
            'trace_path': result.get('trace_path') or '',
        }
        bars_by_symbol[symbol] = int(result.get('bars', 0))
        symbol_trades = _augment_trades_with_symbol(result.get('trades_data') or [], symbol)
        combined_trades.extend(symbol_trades)
        combined_trace.extend(_load_trace_events(result.get('trace_path') or '', symbol))
        total_trades += int(result.get('trades', 0))
        total_pnl += float(result.get('pnl_pct', 0.0))
        total_rr += sum(float(x.get('rr', 0.0)) for x in symbol_trades)
        total_wins += sum(1 for x in symbol_trades if float(x.get('pnl_pct', 0.0)) > 0)
        total_prepare += int(result.get('prepare_count', 0))
        total_enter += int(result.get('enter_count', 0))
        total_exit_signal += int(result.get('exit_signal_count', 0))
        total_triggered += int(result.get('if_then_triggered', 0))
        total_armed += int(result.get('if_then_armed', 0))
        total_executed += int(result.get('if_then_executed', 0))
        total_closed += int(result.get('if_then_closed', 0))
        total_failed += int(result.get('if_then_failed', 0))
        total_momentum_exit += int(result.get('momentum_exit_count', 0))
        total_timeout += int(result.get('timeout_count', 0))
        total_tp_hit += int(result.get('tp_hit_count', 0))
        total_stop += int(result.get('stop_count', 0))
        max_drawdown = max(max_drawdown, float(result.get('max_drawdown_pct', 0.0)))

    summary = {
        'mode': 'multi',
        'symbols': list(symbols),
        'timeframe': timeframe,
        'lookback_days': lookback_days,
        'bars_by_symbol': bars_by_symbol,
        'trades': total_trades,
        'winrate': round((total_wins / total_trades) * 100.0, 2) if total_trades else 0.0,
        'avg_rr': round(total_rr / total_trades, 4) if total_trades else 0.0,
        'pnl_pct': round(total_pnl, 4),
        'max_drawdown_pct': round(max_drawdown, 4),
        'prepare_count': total_prepare,
        'enter_count': total_enter,
        'exit_signal_count': total_exit_signal,
        'if_then_triggered': total_triggered,
        'if_then_armed': total_armed,
        'if_then_executed': total_executed,
        'if_then_closed': total_closed,
        'if_then_failed': total_failed,
        'momentum_exit_count': total_momentum_exit,
        'timeout_count': total_timeout,
        'tp_hit_count': total_tp_hit,
        'stop_count': total_stop,
        'report_path': '',
        'swing_reversal_observe': False,
        'combined_validation': {},
    }
    summary_lines = _combined_summary_lines(summary, per_symbol)
    report_path = output_dir / f'backtest_multi_{lookback_days}d_report.json'
    trace_path = output_dir / f'backtest_multi_{lookback_days}d_trace.json'
    report_payload = {
        'summary': summary,
        'per_symbol': per_symbol,
        'trades': combined_trades,
    }
    report_path.write_text(json.dumps(report_payload, ensure_ascii=False, indent=2), encoding='utf-8')
    trace_path.write_text(json.dumps(combined_trace, ensure_ascii=False, indent=2), encoding='utf-8')
    result = dict(summary)
    result['summary_lines'] = summary_lines
    result['report_path'] = str(report_path)
    result['trace_path'] = str(trace_path)
    result['trades_data'] = combined_trades
    result['per_symbol'] = per_symbol
    return result, source_labels


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Run deterministic or live backtest for the project.')
    parser.add_argument('--symbol', default=DEFAULT_SYMBOL)
    parser.add_argument('--symbols', default=','.join(DEFAULT_MULTI_SYMBOLS))
    parser.add_argument('--timeframe', default=DEFAULT_TIMEFRAME)
    parser.add_argument('--lookback-days', type=int, default=DEFAULT_LOOKBACK_DAYS)
    parser.add_argument('--output-dir', default=DEFAULT_OUTPUT_DIR)
    parser.add_argument('--mode', choices=['auto', 'live', 'frozen', 'multi'], default='auto')
    parser.add_argument('--data-file', default='')
    parser.add_argument('--save-frozen', action='store_true')
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.mode == 'multi':
        symbols = _parse_symbols(args.symbols)
        result, source_labels = _run_multi_backtest(
            symbols=symbols,
            timeframe=args.timeframe,
            lookback_days=args.lookback_days,
            output_dir=output_dir,
        )
        print('DATA_SOURCE:')
        for label in source_labels:
            print(f'- {label}')
        for line in result.get('summary_lines') or []:
            print(line)
        report_path = Path(result.get('report_path') or output_dir / f'backtest_multi_{args.lookback_days}d_report.json')
        print(f'REPORT: {report_path.as_posix()}')
        txt_path = report_path.with_suffix('.txt')
        txt_lines = ['DATA_SOURCE:'] + [f'- {label}' for label in source_labels] + list(result.get('summary_lines') or [])
        txt_path.write_text('\n'.join(txt_lines), encoding='utf-8')
        return 0

    default_frozen_path = _default_frozen_path(args.symbol, args.timeframe, args.lookback_days, output_dir)
    data_file = Path(args.data_file) if args.data_file else default_frozen_path
    result, source_label = _run_single_backtest(
        symbol=args.symbol,
        timeframe=args.timeframe,
        lookback_days=args.lookback_days,
        output_dir=output_dir,
        mode=args.mode,
        data_file=data_file,
        save_frozen=args.save_frozen,
    )

    print(f'DATA_SOURCE: {source_label}')
    for line in result.get('summary_lines') or []:
        print(line)
    _days = args.lookback_days
    summary_path = Path(result.get('report_path') or output_dir / f'backtest_{_days}d_report.json')
    print(f'REPORT: {summary_path.as_posix()}')
    txt_path = summary_path.with_suffix('.txt')
    txt_lines = [f'DATA_SOURCE: {source_label}'] + list(result.get('summary_lines') or [])
    txt_path.write_text('\n'.join(txt_lines), encoding='utf-8')

    if result.get('if_then_triggered', 0) > 0 and result.get('if_then_executed', 0) == 0:
        return 2
    if result.get('trades', 0) == 0 and result.get('if_then_triggered', 0) > 0:
        return 3
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
