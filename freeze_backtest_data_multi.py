from __future__ import annotations

from pathlib import Path

from core.backtest_engine import DEFAULT_HORIZON_BARS, MIN_WINDOW_BARS, bars_for_days
from market_data.ohlcv import get_klines
from run_backtest import DEFAULT_MULTI_SYMBOLS, _default_frozen_path, _save_frozen_candles

TIMEFRAME = '1h'
LOOKBACK_DAYS = 180
OUTPUT_DIR = Path('backtests')


def main() -> int:
    bars = bars_for_days(LOOKBACK_DAYS, TIMEFRAME) + MIN_WINDOW_BARS + DEFAULT_HORIZON_BARS + 10
    for symbol in DEFAULT_MULTI_SYMBOLS:
        candles = get_klines(symbol=symbol, interval=TIMEFRAME, limit=bars)
        path = _default_frozen_path(symbol, TIMEFRAME, LOOKBACK_DAYS, OUTPUT_DIR)
        _save_frozen_candles(
            path,
            candles=candles,
            symbol=symbol,
            timeframe=TIMEFRAME,
            lookback_days=LOOKBACK_DAYS,
            source='LIVE_FETCH_MULTI_FREEZE_SCRIPT',
        )
        print(f'FROZEN_DATA_SAVED: {path.as_posix()}')
        print(f'SYMBOL: {symbol} | BARS: {len(candles)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
