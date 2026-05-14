"""Live derivatives poll — OI + funding rate from Binance REST every 5 min.

P0 #3 fix (2026-05-07): historical batch ingest existed in services.derivatives_ingest
but no live polling. advisor_v2 read OI/funding from frozen 1y parquet which doesn't
update — meaning "OI extreme" / "funding extreme" signals are based on stale data.

Outputs: state/deriv_live.json with structure:
  {
    "last_updated": "2026-05-07T12:00:00Z",
    "BTCUSDT": {
      "oi_usd": 12500000000,
      "oi_btc": 153000,
      "oi_change_1h_pct": 0.45,
      "funding_rate_8h": 0.0001,    # next 8h funding
      "premium_pct": 0.012,           # mark vs index
    },
    "ETHUSDT": {...},
    "XRPUSDT": {...}
  }
"""
from .loop import deriv_live_loop, build_snapshot, DERIV_LIVE_PATH

__all__ = ["deriv_live_loop", "build_snapshot", "DERIV_LIVE_PATH"]
