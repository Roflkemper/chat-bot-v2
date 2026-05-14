from __future__ import annotations

from typing import Any, Dict


def safe_regime_v2(df) -> Dict[str, Any]:
    try:
        from core.regime_engine_v2 import detect_regime_v2
        return detect_regime_v2(df)
    except Exception:
        try:
            from core.market_regime import detect_market_regime
            old = detect_market_regime(df)
            return {
                'base_regime': old.get('state', 'UNKNOWN'),
                'regime_label': old.get('state', 'UNKNOWN'),
                'confidence': float(old.get('confidence', 0.0)),
                'mean_reversion_bias': 50.0,
                'continuation_bias': 50.0,
                'grid_friendly': False,
                'countertrend_friendly': False,
                'trend_friendly': False,
                'features': {},
            }
        except Exception:
            return {
                'base_regime': 'UNKNOWN', 'regime_label': 'UNKNOWN', 'confidence': 0.0,
                'mean_reversion_bias': 50.0, 'continuation_bias': 50.0,
                'grid_friendly': False, 'countertrend_friendly': False, 'trend_friendly': False, 'features': {},
            }


def safe_liquidity_map(df) -> Dict[str, Any]:
    try:
        from core.liquidity_map import build_liquidity_map
        return build_liquidity_map(df)
    except Exception:
        return {'swing_high': 0.0, 'swing_low': 0.0, 'equal_highs_count': 0, 'equal_lows_count': 0, 'swept_high': False, 'swept_low': False, 'acceptance': False, 'liquidity_state': 'NEUTRAL'}


def safe_pattern_memory_v2(df) -> Dict[str, Any]:
    try:
        from core.pattern_history_engine_v15 import build_pattern_history_context
        ctx = build_pattern_history_context(df)
        if isinstance(ctx, dict):
            ctx.setdefault('pattern_type', 'LOCAL_MEMORY')
            ctx.setdefault('match_quality', 'SOFT')
            ctx.setdefault('expected_path', 'RANGE_ROTATION')
            ctx.setdefault('invalidation', 'паттерн ломается при резком обратном импульсе от текущей зоны')
            ctx.setdefault('pattern_note', 'локальная память активна')
            return ctx
    except Exception:
        pass
    try:
        from core.pattern_memory_v2 import build_pattern_vector
        vec = build_pattern_vector(df)
        return {'pattern_vector': vec, 'long_prob': 40.0, 'short_prob': 40.0, 'neutral_prob': 20.0, 'matches': 1, 'matched_count': 1, 'summary': 'pattern memory fallback active', 'pattern_type': 'LOCAL_MEMORY', 'match_quality': 'SOFT', 'expected_path': 'RANGE_ROTATION', 'invalidation': 'нужен новый confirm после слома локальной структуры', 'pattern_note': 'включён мягкий fallback паттерна', 'direction': 'NEUTRAL', 'pattern_bias': 'NEUTRAL', 'confidence': 18.0}
    except Exception:
        return {'pattern_vector': None, 'long_prob': 40.0, 'short_prob': 40.0, 'neutral_prob': 20.0, 'matches': 1, 'matched_count': 1, 'summary': 'pattern memory unavailable', 'pattern_type': 'LOCAL_MEMORY', 'match_quality': 'SOFT', 'expected_path': 'RANGE_ROTATION', 'invalidation': 'паттерн временно недоступен', 'pattern_note': 'историческая память недоступна', 'direction': 'NEUTRAL', 'pattern_bias': 'NEUTRAL', 'confidence': 18.0}


def safe_ml_v2(df, regime_label: str) -> Dict[str, Any]:
    setup_type = 'countertrend'
    label = (regime_label or '').upper()
    if 'TREND' in label:
        setup_type = 'trend'
    elif 'RANGE' in label:
        setup_type = 'range'
    try:
        from core.features import build_feature_vector_v2
        from core.ml_model_v2 import SetupModels
        models = SetupModels()
        features = build_feature_vector_v2(df)
        out = models.predict_bundle(features, setup_type)
        out['feature_vector'] = list(features)
        return out
    except Exception:
        return {
            'setup_type': setup_type,
            'probability': 0.5,
            'confidence': 0.5,
            'edge_strength': 0.0,
            'follow_through_probability': 0.5,
            'reversal_probability': 0.5,
            'setup_quality_probability': 0.5,
            'features_used': 0,
            'source': 'ml_fallback',
            'model_status': 'error',
        }


def safe_backtest_v2(df) -> Dict[str, Any]:
    try:
        from core.setup_backtest import evaluate_trade
        res = evaluate_trade(df, max(0, len(df) - 15))
        return res or {'mfe': 0.0, 'mae': 0.0}
    except Exception:
        return {'mfe': 0.0, 'mae': 0.0}


def safe_microstructure(df=None) -> Dict[str, Any]:
    try:
        from core.microstructure import MicroSnapshot, build_microstructure_context
        snap = MicroSnapshot(bids=None, asks=None, aggressive_buy_ratio=0.5, aggressive_sell_ratio=0.5, recent_spread_bps=2.0)
        return build_microstructure_context(snap, df=df)
    except Exception:
        return {'micro_bias': 'NEUTRAL', 'confidence': 50.0, 'summary': 'micro unavailable'}


def safe_adaptive_weights(regime_label: str, setup_type: str) -> Dict[str, Any]:
    try:
        from core.adaptive_weights import AdaptiveWeights
        aw = AdaptiveWeights()
        return aw.get_weights(regime_label, setup_type)
    except Exception:
        return {'regime': 1.0, 'liquidity': 1.0, 'pattern': 1.0, 'ml': 1.0, 'derivatives': 1.0, 'micro': 0.7, 'personal': 0.8, 'backtest': 0.9}
