# data_freshness_check
Trigger: backtest, ohlcv, market_collector, real validation, frozen, исторические данные.

Before any backtest/validation:
1. Check OHLCV last bar timestamp. Stale if >24h from now.
2. Check market_collector parquet write activity for last 1h.
3. Check tracker snapshots for last 1h.

If any stale:
DATA STALE: [source] last update [ts]. Operation blocked.
Operator action: refresh data via [TZ-050 OHLCV ingestion or equivalent].

Do not proceed with stale data. Do not fake fresh timestamps.
