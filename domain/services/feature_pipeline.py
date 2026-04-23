from __future__ import annotations

from domain.contracts.feature_context import FeatureContext
from domain.contracts.raw_market_context import RawMarketContext


class FeaturePipeline:
    def run(self, raw: RawMarketContext) -> FeatureContext:
        return FeatureContext(
            range_feature={'range_position_label': 'UNKNOWN', 'range_position_pct': 50.0, 'at_edge': False},
            liquidity_blocks_feature={'upper_block': None, 'lower_block': None, 'reaction_zone': None},
            liquidation_reaction_feature={'status': 'NONE', 'reaction_side': 'NONE'},
            impulse_feature={'state': 'CHOP', 'direction': 'NONE', 'strength': 'LOW', 'quality': 'CHOPPY'},
            fake_move_feature={'status': 'NONE', 'side': 'NONE', 'confidence': 0.0},
            volume_feature={'relative_volume': 1.0, 'volume_confirmation_status': 'WEAK'},
            orderflow_feature={'dominance_side': 'NONE', 'dominance_strength': 'LOW'},
            reversal_feature={'status': 'NO_REVERSAL', 'side': 'NONE', 'confidence': 0.0},
            pinbar_feature={'detected': False, 'side': 'NONE', 'confirmation_status': 'NONE'},
            multi_tf_feature={'main_tf_bias': 'NEUTRAL', 'higher_tf_bias': 'NEUTRAL', 'agreement_status': 'NEUTRAL'},
            pattern_memory_feature={'pattern_status': 'NEUTRAL', 'historical_bias': 'NEUTRAL', 'historical_confidence': 0.0},
            grid_preactivation_feature={'long_grid_readiness': 'HOLD', 'short_grid_readiness': 'HOLD', 'grid_context_state': 'WATCH'},
        )
