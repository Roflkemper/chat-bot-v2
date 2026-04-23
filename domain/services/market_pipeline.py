from __future__ import annotations

from datetime import datetime, UTC
from domain.contracts.raw_market_context import RawMarketContext


class MarketPipeline:
    def run(self, symbol: str, timeframe: str) -> RawMarketContext:
        # CORE V1 scaffold: real donor wiring should replace fallback payload below.
        now = datetime.now(UTC).isoformat()
        return RawMarketContext(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=now,
            current_price=0.0,
            last_close=0.0,
            candles_main_tf=[],
            candles_higher_tf=[],
            volume_snapshot={'status': 'fallback'},
            orderflow_snapshot={'status': 'fallback'},
            liquidity_feed_status='fallback',
            liquidation_feed_status='fallback',
            source_health={'market_pipeline': 'scaffold'},
            fallback_flags=['market_pipeline_scaffold'],
            missing_sources=['real_market_sources'],
            data_quality_score=0.1,
        )
