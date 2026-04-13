from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from core.backtest_engine import bars_for_days, run_backtest, run_backtest_from_candles
from market_data.ohlcv import get_klines

DEFAULT_SYMBOL = 'BTCUSDT'
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


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Run deterministic or live backtest for the project.')
    parser.add_argument('--symbol', default=DEFAULT_SYMBOL)
    parser.add_argument('--timeframe', default=DEFAULT_TIMEFRAME)
    parser.add_argument('--lookback-days', type=int, default=DEFAULT_LOOKBACK_DAYS)
    parser.add_argument('--output-dir', default=DEFAULT_OUTPUT_DIR)
    parser.add_argument('--mode', choices=['auto', 'live', 'frozen'], default='auto')
    parser.add_argument('--data-file', default='')
    parser.add_argument('--save-frozen', action='store_true')
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    default_frozen_path = _default_frozen_path(args.symbol, args.timeframe, args.lookback_days, output_dir)
    data_file = Path(args.data_file) if args.data_file else default_frozen_path

    source_label = 'LIVE_BINANCE'
    if args.mode in {'auto', 'frozen'} and data_file.exists():
        candles = _load_frozen_candles(data_file)
        source_label = f'FROZEN:{data_file.as_posix()}'
        result = run_backtest_from_candles(
            candles,
            symbol=args.symbol,
            timeframe=args.timeframe,
            lookback_days=args.lookback_days,
            output_dir=output_dir,
        )
    elif args.mode == 'frozen':
        raise SystemExit(f'[ERROR] Frozen data file not found: {data_file.as_posix()}')
    else:
        result = run_backtest(
            symbol=args.symbol,
            timeframe=args.timeframe,
            lookback_days=args.lookback_days,
            output_dir=output_dir,
        )
        if args.save_frozen:
            bars = bars_for_days(args.lookback_days, args.timeframe)
            # keep fetched candle count aligned with engine for reproducibility
            bars = bars + 120 + 12 + 10
            candles = get_klines(symbol=args.symbol, interval=args.timeframe, limit=bars)
            _save_frozen_candles(
                data_file,
                candles=candles,
                symbol=args.symbol,
                timeframe=args.timeframe,
                lookback_days=args.lookback_days,
                source='LIVE_FETCH_SAVED',
            )
            source_label = f'LIVE_BINANCE -> SAVED:{data_file.as_posix()}'

    print(f'DATA_SOURCE: {source_label}')
    for line in result.get('summary_lines') or []:
        print(line)
    summary_path = Path(result.get('report_path') or output_dir / 'backtest_90d_report.json')
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
