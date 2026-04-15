from __future__ import annotations

from pathlib import Path

from market_data.ohlcv import get_klines
from run_backtest import _default_frozen_path, _save_frozen_candles
from core.backtest_engine import DEFAULT_HORIZON_BARS, MIN_WINDOW_BARS, bars_for_days

SYMBOL = 'BTCUSDT'
TIMEFRAME = '1h'
LOOKBACK_DAYS = 180
OUTPUT_DIR = Path('backtests')


def main() -> int:
    bars = bars_for_days(LOOKBACK_DAYS, TIMEFRAME) + MIN_WINDOW_BARS + DEFAULT_HORIZON_BARS + 10
    candles = get_klines(symbol=SYMBOL, interval=TIMEFRAME, limit=bars)
    path = _default_frozen_path(SYMBOL, TIMEFRAME, LOOKBACK_DAYS, OUTPUT_DIR)
    _save_frozen_candles(
        path,
        candles=candles,
        symbol=SYMBOL,
        timeframe=TIMEFRAME,
        lookback_days=LOOKBACK_DAYS,
        source='LIVE_FETCH_FREEZE_SCRIPT',
    )
    print(f'FROZEN_DATA_SAVED: {path.as_posix()}')
    print(f'BARS: {len(candles)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
