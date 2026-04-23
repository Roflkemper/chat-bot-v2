from __future__ import annotations

from domain.contracts.market_context import MarketContext
from renderers.view_models.analysis_view_model import AnalysisViewModel


class AnalysisViewBuilder:
    def build(self, context: MarketContext) -> AnalysisViewModel:
        return AnalysisViewModel(
            title='BTC ANALYSIS',
            timeframe=context.market_identity.get('timeframe', '15m'),
            price=0.0,
            bias=context.liquidity_context.get('liquidity_bias', 'NEUTRAL'),
            regime=context.regime_context.get('market_regime', 'UNKNOWN'),
            location=context.location_context.get('price_location', 'UNKNOWN'),
            upper_block=str(context.location_context.get('upper_block', '-')),
            lower_block=str(context.location_context.get('lower_block', '-')),
            movement_state=context.movement_context.get('movement_state', 'UNKNOWN'),
            movement_quality='CHOPPY' if context.regime_context.get('high_noise', False) else 'NORMAL',
            reaction_status=context.liquidity_context.get('acceptance_vs_rejection', 'NONE'),
            where_to_watch=context.watch_context.get('where_to_watch', ''),
            analysis_note=context.watch_context.get('watch_reason', ''),
        )
