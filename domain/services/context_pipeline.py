from __future__ import annotations

from domain.contracts.feature_context import FeatureContext
from domain.contracts.market_context import MarketContext
from domain.contracts.raw_market_context import RawMarketContext


class ContextPipeline:
    def run(self, raw: RawMarketContext, features: FeatureContext) -> MarketContext:
        return MarketContext(
            market_identity={'symbol': raw.symbol, 'timeframe': raw.timeframe, 'timestamp': raw.timestamp},
            regime_context={'market_regime': 'RANGE', 'range_friendly': True, 'trend_friendly': False, 'high_noise': True},
            location_context={'price_location': features.range_feature.get('range_position_label', 'UNKNOWN'), 'active_reaction_zone': features.liquidity_blocks_feature.get('reaction_zone')},
            liquidity_context={'liquidity_event_status': features.liquidation_reaction_feature.get('status', 'NONE'), 'acceptance_vs_rejection': features.liquidation_reaction_feature.get('status', 'NONE'), 'liquidity_bias': 'NEUTRAL'},
            movement_context={'movement_state': features.impulse_feature.get('state', 'CHOP'), 'impulse_alive': False, 'impulse_fading': True, 'fake_move_risk': features.fake_move_feature.get('status', 'NONE'), 'movement_bias': 'NEUTRAL'},
            confirmation_context={'volume_confirmed': False, 'orderflow_confirmed': False, 'pinbar_confirmed': False, 'multi_tf_confirmed': False, 'confirmation_score': 0.0},
            reversal_context={'reversal_ready': False, 'reversal_side': 'NONE', 'reversal_confidence': 0.0},
            pattern_context={'historical_alignment': False, 'historical_bias': 'NEUTRAL', 'historical_weight': 0.0},
            risk_context={'risk_level': 'HIGH', 'chase_risk': True, 'late_entry_risk': True, 'false_break_risk': True, 'data_quality_risk': True},
            strategy_allowance_context={'allow_directional_long': False, 'allow_directional_short': False, 'allow_range_reentry': False, 'allow_grid_long': True, 'allow_grid_short': True},
            watch_context={'where_to_watch': 'reaction zone', 'watch_reason': 'scaffold market context', 'next_trigger_long': '', 'next_trigger_short': '', 'invalidation_zone_if_any': ''},
        )
