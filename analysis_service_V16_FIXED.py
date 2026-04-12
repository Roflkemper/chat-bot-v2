from __future__ import annotations

import logging
import os
import time
import traceback
from typing import Any, Callable, Dict, List

from utils.observability import RequestTrace
from models.snapshots import AnalysisSnapshot
from core.data_loader import get_klines_cache_info, load_klines
from core.import_compat import (
    load_btc_analyzer,
    load_ginarea_analyzer,
    load_range_analyzer,
    normalize_analysis_payload,
)

from storage.personal_bot_learning import build_learning_forecast_adjustment
from core.grid_strategy import build_three_bot_grid_strategy

from core.compat_layer import (safe_regime_v2, safe_liquidity_map, safe_pattern_memory_v2, safe_ml_v2, safe_backtest_v2, safe_microstructure, safe_adaptive_weights)
from core.derivatives_context import DerivativesSnapshot, build_derivatives_context
from core.orderflow_layer import OrderflowSnapshot, build_orderflow_context
from core.liquidation_map import LiquidationSnapshot, build_liquidation_context
from core.expectancy_engine import build_expectancy_context
from core.volatility_impulse import build_volatility_impulse_context
from core.no_trade_engine import build_no_trade_context
from core.best_trade_ranker import rank_best_plays
from core.factor_hierarchy import build_factor_breakdown
from core.scenario_engine import build_scenarios
from core.grid_commander import grid_decision
from core.bot_authority import build_bot_authority
from core.grid_execution_authority_v15 import build_grid_execution_authority_v15
from core.decision_authority_v15 import build_decision_authority_v15
from core.output_contract_v14 import build_v14_output_contract
from core.liquidity_block_engine import build_liquidity_block_context
from core.liquidation_reaction_engine import build_liquidation_reaction_context
from core.pinbar_engine import build_pinbar_context
from core.volume_confirmation_engine import build_volume_confirmation_context
from core.reversal_engine_v15 import build_reversal_context
from core.fast_move_interpreter import build_fast_move_context
from core.fake_move_detector import build_fake_move_detector
from core.impulse_character_engine import build_impulse_character_context
from core.liquidity_decision_engine import build_liquidity_decision_context
from core.soft_signal import build_soft_signal
from core.move_projection import build_move_projection
from core.trade_flow import build_trade_flow_summary
from core.setup_stats import build_setup_stats_context, build_setup_learning_adjustment, build_learning_execution_plan
from core.coinglass_client import fetch_coin_context
from core.exchange_liquidity_engine import get_exchange_liquidity_context
from core.multi_tf_fusion import build_multi_tf_context
from core.pattern_memory import analyze_history_pattern

try:
    from core.decision_engine import combine_trade_decision
except Exception:
    combine_trade_decision = None

logger = logging.getLogger(__name__)
DEFAULT_TF = "1h"
_GLOBAL_ANALYSIS_CACHE: Dict[str, tuple[float, AnalysisSnapshot]] = {}
_GLOBAL_ANALYSIS_TTL_SEC = 8.0


def _safe_dict(v):
    return v if isinstance(v, dict) else {}


def _sync_nextgen_layers_into_merged(merged: dict, decision: dict) -> dict:
    try:
        merged = merged if isinstance(merged, dict) else {}
        decision = decision if isinstance(decision, dict) else {}
        merged["decision"] = decision
        merged["fake_move_detector"] = _safe_dict(decision.get("fake_move_detector"))
        merged["move_type_context"] = _safe_dict(decision.get("move_type_context"))
        merged["bot_mode_context"] = _safe_dict(decision.get("bot_mode_context"))
        merged["range_bot_permission"] = _safe_dict(decision.get("range_bot_permission"))
        merged["action_output"] = _safe_dict(decision.get("action_output"))
        merged["bot_mode_action"] = decision.get("bot_mode_action", "OFF")
        merged["directional_action"] = decision.get("directional_action", decision.get("action", "WAIT"))
        if "best_trade_play" in decision:
            merged["best_trade_play"] = decision.get("best_trade_play")
        if "best_trade_side" in decision:
            merged["best_trade_side"] = decision.get("best_trade_side")
        if "best_trade_score" in decision:
            merged["best_trade_score"] = decision.get("best_trade_score")
        return merged
    except Exception:
        return merged



def _is_directional_value(value: Any) -> bool:
    s = str(value or "").strip().upper()
    return s in {"ЛОНГ", "ШОРТ", "LONG", "SHORT", "ВВЕРХ", "ВНИЗ", "UP", "DOWN"}


def _should_override_merge(key: str, current: Any, new: Any) -> bool:
    if new is None:
        return False
    if key in {"forecast_direction", "final_decision", "signal"}:
        cur = str(current or "").strip().upper()
        newv = str(new or "").strip().upper()
        # Primary signal layer should win. Advisory layers (range/ginarea) must not
        # rewrite top-level direction once it has already been set by the main analyzer.
        if cur:
            return cur != newv
        return False
    if key in {"forecast_confidence"}:
        try:
            cur = float(current) if current is not None else None
            newv = float(new)
            return cur is not None and cur > 0 and newv <= cur
        except Exception:
            return False
    return False




def _apply_learning_forecast_weight(merged: Dict[str, Any]) -> Dict[str, Any]:
    analysis = merged.get("analysis") if isinstance(merged.get("analysis"), dict) else {}
    learning_summary = analysis.get("personal_learning") if isinstance(analysis.get("personal_learning"), dict) else {}
    if not learning_summary:
        return merged

    adj = build_learning_forecast_adjustment(learning_summary, {
        "best_bot": analysis.get("best_bot") or merged.get("best_bot"),
        "best_bot_label": analysis.get("best_bot_label") or merged.get("best_bot_label"),
        "market_regime": merged.get("market_regime") or analysis.get("market_regime") or merged.get("trade_style") or analysis.get("trade_style"),
        "range_position": merged.get("range_position") or analysis.get("range_position"),
        "forecast_direction": merged.get("forecast_direction"),
        "forecast_confidence": merged.get("forecast_confidence"),
    })

    merged["learning_forecast_adjustment"] = adj
    analysis["learning_forecast_adjustment"] = adj
    merged["analysis"] = analysis

    delta = float(adj.get("delta") or 0.0)
    hint = str(adj.get("direction_hint") or "НЕЙТРАЛЬНО").upper()
    current_dir = str(merged.get("forecast_direction") or "НЕЙТРАЛЬНО").upper()
    current_conf = float(merged.get("forecast_confidence") or 0.0)

    # Only nudge the top-layer forecast; never override a strong opposing signal.
    if abs(delta) >= 0.005:
        if current_dir in {"НЕЙТРАЛЬНО", "NEUTRAL", ""} and hint in {"ВВЕРХ", "ВНИЗ"}:
            merged["forecast_direction"] = hint
            merged["forecast_confidence"] = round(max(current_conf, 0.52 + abs(delta)), 3)
        elif hint == current_dir and hint in {"ВВЕРХ", "ВНИЗ"}:
            merged["forecast_confidence"] = round(min(0.95, current_conf + max(0.0, delta)), 3)
        elif hint in {"ВВЕРХ", "ВНИЗ"} and current_dir in {"ВВЕРХ", "ВНИЗ"} and hint != current_dir and delta < 0:
            merged["forecast_confidence"] = round(max(0.0, current_conf + delta), 3)

    # keep convenient text label for top blocks
    sign = "+" if delta >= 0 else ""
    merged["learning_forecast_summary"] = f"{adj.get('summary')} ({sign}{delta * 100:.1f}%)"
    return merged




def _build_derivatives_stub(df, coinglass: Dict[str, Any] | None = None):
    last_close = float(df['close'].iloc[-1])
    close_12 = float(df['close'].iloc[-12]) if len(df) > 12 else last_close
    price_change_1h_pct = ((last_close - close_12) / close_12 * 100.0) if close_12 else 0.0
    coinglass = coinglass or {}
    oi_close = float(coinglass.get('oi_close') or 0.0)
    oi_prev = float(coinglass.get('oi_prev_close') or oi_close or 0.0)
    oi_change = ((oi_close - oi_prev) / oi_prev * 100.0) if oi_prev else 0.0
    funding = float(coinglass.get('funding_rate') or 0.0)
    short_liq = float(coinglass.get('nearest_above_price') or 0.0)
    long_liq = float(coinglass.get('nearest_below_price') or 0.0)
    short_dist = abs(short_liq - last_close) / last_close * 100.0 if short_liq > 0 and last_close > 0 else 999.0
    long_dist = abs(last_close - long_liq) / last_close * 100.0 if long_liq > 0 and last_close > 0 else 999.0
    snapshot = DerivativesSnapshot(
        funding_rate=funding,
        funding_zscore=0.0,
        open_interest=oi_close,
        oi_change_1h_pct=oi_change,
        oi_change_4h_pct=oi_change,
        long_liq_distance_pct=long_dist,
        short_liq_distance_pct=short_dist,
    )
    out = build_derivatives_context(price_change_1h_pct=price_change_1h_pct, snapshot=snapshot)
    out['source'] = str(coinglass.get('source') or ('coinglass_v4' if coinglass.get('ok') else 'price_action_stub'))
    out['coinglass_ok'] = bool(coinglass.get('ok'))
    out['feed_health'] = str(coinglass.get('feed_health') or ('OK' if coinglass.get('ok') else 'UNKNOWN'))
    out['feed_stale_seconds'] = int(coinglass.get('feed_stale_seconds') or 0)
    out['fallback_active'] = bool(coinglass.get('fallback_active'))
    out['data_quality'] = 'LIVE' if out['feed_health'] == 'LIVE' else 'DEGRADED' if out['feed_health'] in {'DEGRADED', 'UNKNOWN'} else out['feed_health']
    if coinglass.get('errors'):
        out['coinglass_errors'] = list(coinglass.get('errors') or [])
    return out




def _build_orderflow_stub(df):
    close = df['close'].astype(float)
    open_ = df['open'].astype(float)
    volume = df['volume'].astype(float) if 'volume' in df.columns else close * 0 + 1.0
    recent = min(12, len(df))
    buy_vol = float((((close > open_).astype(float) * volume).tail(recent)).sum())
    sell_vol = float((((close < open_).astype(float) * volume).tail(recent)).sum())
    delta = buy_vol - sell_vol
    exhaustion_up = bool((df['high'].astype(float).tail(4).max() >= float(df['high'].astype(float).tail(12).max())) and close.tail(3).mean() <= close.tail(6).mean())
    exhaustion_down = bool((df['low'].astype(float).tail(4).min() <= float(df['low'].astype(float).tail(12).min())) and close.tail(3).mean() >= close.tail(6).mean())
    return build_orderflow_context(OrderflowSnapshot(
        aggressive_buy_volume=buy_vol,
        aggressive_sell_volume=sell_vol,
        delta_volume=delta,
        cumulative_delta=delta,
        buy_imbalance=(buy_vol / max(buy_vol + sell_vol, 1e-9)),
        sell_imbalance=(sell_vol / max(buy_vol + sell_vol, 1e-9)),
        absorption_at_high=exhaustion_up,
        absorption_at_low=exhaustion_down,
        exhaustion_up=exhaustion_up,
        exhaustion_down=exhaustion_down,
    ))




def _build_liquidation_stub(df, coinglass: Dict[str, Any] | None = None):
    high = df['high'].astype(float)
    low = df['low'].astype(float)
    close = df['close'].astype(float)
    last_close = float(close.iloc[-1])
    lookback = min(24, len(df))
    coinglass = coinglass or {}
    nearest_short = float(coinglass.get('nearest_above_price') or high.tail(lookback).max())
    nearest_long = float(coinglass.get('nearest_below_price') or low.tail(lookback).min())
    snapshot = LiquidationSnapshot(
        current_price=last_close,
        nearest_long_liq_price=nearest_long,
        nearest_short_liq_price=nearest_short,
        long_cluster_strength=max(float(coinglass.get('nearest_below_strength') or 0.0), max(0.0, (last_close - nearest_long) / max(last_close, 1e-9) * 100.0)),
        short_cluster_strength=max(float(coinglass.get('nearest_above_strength') or 0.0), max(0.0, (nearest_short - last_close) / max(last_close, 1e-9) * 100.0)),
    )
    out = build_liquidation_context(snapshot)
    out['source'] = str(coinglass.get('source') or ('coinglass_v4' if coinglass.get('ok') else 'swing_stub'))
    out['heatmap_ready'] = bool(coinglass.get('nearest_above_price') or coinglass.get('nearest_below_price'))
    out['coinglass_ok'] = bool(coinglass.get('ok'))
    out['recent_liquidation_events'] = int(coinglass.get('recent_liquidation_events') or coinglass.get('events_count') or 0)
    out['recent_liquidation_notional_usd'] = float(coinglass.get('recent_liquidation_notional_usd') or 0.0)
    out['price_oi_regime'] = str(coinglass.get('price_oi_regime') or 'NEUTRAL')
    out['funding_state'] = str(coinglass.get('funding_state') or coinglass.get('funding_bias') or 'NEUTRAL')
    out['feed_health'] = str(coinglass.get('feed_health') or '')
    out['feed_stale_seconds'] = int(coinglass.get('feed_stale_seconds') or 0)
    if coinglass.get('errors'):
        out['coinglass_errors'] = list(coinglass.get('errors') or [])
    return out


def _enrich_with_nextgen_layers(merged: Dict[str, Any]) -> Dict[str, Any]:
    try:
        analysis = merged.get('analysis') if isinstance(merged.get('analysis'), dict) else {}
        df = analysis.get('df')
        if df is None or getattr(df, 'empty', True):
            return merged

        merged['liquidity_map'] = safe_liquidity_map(df)
        merged['regime_v2'] = safe_regime_v2(df)
        last_price = float(df['close'].astype(float).iloc[-1])
        symbol = str(merged.get('symbol') or analysis.get('symbol') or 'BTCUSDT').upper()
        timeframe = str(merged.get('timeframe') or analysis.get('timeframe') or DEFAULT_TF).lower()
        coin = 'BTC' if symbol.startswith('BTC') else symbol.replace('USDT', '').replace('USD', '')

        exchange_ctx = get_exchange_liquidity_context(symbol=symbol, price=last_price)
        merged['coinglass_context'] = exchange_ctx
        if not exchange_ctx.get('ok') and os.getenv('COINGLASS_API_KEY'):
            api_ctx = fetch_coin_context(coin=coin, interval='1h', price=last_price)
            if isinstance(api_ctx, dict) and api_ctx.get('ok'):
                merged['coinglass_context'] = api_ctx

        try:
            pattern_ctx = analyze_history_pattern(df, symbol=symbol, timeframe=timeframe)
        except Exception:
            pattern_ctx = {}
        if not isinstance(pattern_ctx, dict) or (int(pattern_ctx.get('matched_count') or pattern_ctx.get('matches') or 0) <= 0 and str(pattern_ctx.get('summary') or '').strip() in {'', 'pattern memory unavailable'}):
            fallback_pattern = safe_pattern_memory_v2(df)
            if isinstance(fallback_pattern, dict) and fallback_pattern:
                pattern_ctx = {**fallback_pattern, **(pattern_ctx if isinstance(pattern_ctx, dict) else {})}
        pattern_ctx['timeframe'] = timeframe
        pattern_ctx['source'] = str(pattern_ctx.get('source') or ('history_2024_2026' if int(pattern_ctx.get('matched_count') or pattern_ctx.get('matches') or 0) > 0 else 'local_fallback'))
        pattern_ctx = _normalize_pattern_memory_for_renderer(pattern_ctx, current_price=last_price)
        merged['pattern_memory_v2'] = pattern_ctx
        merged['pattern_vector'] = pattern_ctx.get('pattern_vector')

        regime_label = merged['regime_v2'].get('regime_label', 'UNKNOWN')
        merged['ml_v2'] = safe_ml_v2(df, regime_label)
        merged['backtest_v2'] = safe_backtest_v2(df)
        merged['derivatives_context'] = _build_derivatives_stub(df, merged.get('coinglass_context'))
        dctx = merged['derivatives_context'] if isinstance(merged.get('derivatives_context'), dict) else {}
        cctx = merged['coinglass_context'] if isinstance(merged.get('coinglass_context'), dict) else {}
        lctx = merged.get('liquidation_context') if isinstance(merged.get('liquidation_context'), dict) else {}
        dctx['source'] = str(cctx.get('source') or dctx.get('source') or 'unknown')
        dctx['feed_health'] = str(cctx.get('feed_health') or dctx.get('feed_health') or 'UNKNOWN')
        dctx['feed_stale_seconds'] = int(cctx.get('feed_stale_seconds') or dctx.get('feed_stale_seconds') or 0)
        dctx['fallback_active'] = bool(cctx.get('fallback_active') or dctx.get('fallback_active'))
        dctx['recent_liquidation_events'] = int(cctx.get('recent_liquidation_events') or lctx.get('recent_liquidation_events') or 0)
        dctx['recent_liquidation_notional_usd'] = float(cctx.get('recent_liquidation_notional_usd') or lctx.get('recent_liquidation_notional_usd') or 0.0)
        dctx['data_quality'] = 'LIVE' if dctx['feed_health'] == 'LIVE' else 'SNAPSHOT' if dctx['feed_health'] in {'METRICS_ONLY', 'WS_DISABLED'} else 'DEGRADED'
        dctx['execution_bias'] = str(dctx.get('derivative_edge') or 'NEUTRAL')
        merged['derivatives_context'] = dctx
        merged['recent_candles'] = [
            {
                'open': float(row['open']), 'high': float(row['high']), 'low': float(row['low']), 'close': float(row['close']),
                'volume': float(row['volume']) if 'volume' in df.columns else 0.0,
            }
            for _, row in df.tail(32).iterrows()
        ]
        merged['microstructure'] = safe_microstructure(df)
        merged['orderflow_context'] = _build_orderflow_stub(df)
        merged['liquidation_context'] = _build_liquidation_stub(df, merged.get('coinglass_context'))
        merged['volatility_impulse'] = build_volatility_impulse_context(df)
        merged['fast_move_context'] = build_fast_move_context(merged['liquidity_map'], merged['orderflow_context'], merged['volatility_impulse'], merged['microstructure'], float(df['close'].astype(float).iloc[-1]), merged['liquidation_context'])
        merged['impulse_character'] = build_impulse_character_context(merged)
        merged['liquidity_decision'] = build_liquidity_decision_context(merged)
        merged['liquidity_blocks'] = build_liquidity_block_context(merged)
        merged['liquidation_reaction'] = build_liquidation_reaction_context(merged)
        merged['pinbar_context'] = build_pinbar_context(merged)
        merged['volume_confirmation'] = build_volume_confirmation_context(merged)
        merged = _normalize_volume_confirmation_for_renderer(merged)
        merged = _normalize_impulse_character_for_renderer(merged)
        merged['reversal_v15'] = build_reversal_context(merged)
        merged['reversal_signal'] = merged['reversal_v15'].get('state', merged.get('reversal_signal'))
        merged['reversal_confidence'] = merged['reversal_v15'].get('confidence', merged.get('reversal_confidence'))

        personal_learning = analysis.get('personal_learning') if isinstance(analysis.get('personal_learning'), dict) else {}
        merged['personal_stats_v2'] = {'avg_rr': float(personal_learning.get('avg_rr', 0.0) or 0.0), 'trades': int(personal_learning.get('trades', 0) or 0)}
        merged['setup_stats'] = build_setup_stats_context(merged)
        active_setup = merged['setup_stats'].get('active_bot') if isinstance(merged.get('setup_stats'), dict) else {}
        if isinstance(active_setup, dict) and active_setup:
            merged['personal_stats_v2']['avg_rr'] = max(float(merged['personal_stats_v2'].get('avg_rr', 0.0) or 0.0), float(active_setup.get('avg_rr', 0.0) or 0.0))
            merged['personal_stats_v2']['trades'] = max(int(merged['personal_stats_v2'].get('trades', 0) or 0), int(active_setup.get('samples', 0) or 0))
        merged['adaptive_weights'] = safe_adaptive_weights(regime_label, merged['ml_v2'].get('setup_type', 'unknown'))
        merged['expectancy_context'] = build_expectancy_context(merged['ml_v2'], merged['pattern_memory_v2'], merged['backtest_v2'], merged['personal_stats_v2'])
        merged['no_trade_context'] = build_no_trade_context(merged['regime_v2'], merged['liquidity_map'], merged['expectancy_context'], merged['volatility_impulse'], merged['orderflow_context'])

        grid_strategy = merged.get('grid_strategy') if isinstance(merged.get('grid_strategy'), dict) else {}
        merged['grid_cmd'] = {'long_grid': 'ENABLE' if grid_strategy.get('enabled') else 'HOLD', 'short_grid': 'ENABLE' if grid_strategy.get('enabled') else 'HOLD'}
        if merged['regime_v2'].get('grid_friendly') is False and merged['regime_v2'].get('trend_friendly'):
            merged['grid_cmd'] = {'long_grid': 'DISABLE', 'short_grid': 'DISABLE'}

        merged['factor_breakdown'] = build_factor_breakdown(merged, merged.get('decision', {}) if isinstance(merged.get('decision'), dict) else {})
        merged['grid_cmd'] = grid_decision(merged['regime_v2'], merged['liquidity_map'], merged['ml_v2'], merged['factor_breakdown'])
        merged['scenario_rank'] = build_scenarios(merged, merged.get('decision', {}) if isinstance(merged.get('decision'), dict) else {})
        merged['best_trade_rank'] = rank_best_plays(merged['regime_v2'], merged['liquidity_map'], merged['derivatives_context'], merged['ml_v2'], merged['pattern_memory_v2'], merged['personal_stats_v2'], merged['grid_cmd'], merged['microstructure'], merged['adaptive_weights'], merged['expectancy_context'], merged['volatility_impulse'], merged['orderflow_context'], merged['liquidation_context'], merged['no_trade_context'])
        merged['trade_flow'] = build_trade_flow_summary(merged)
        legacy_fake = build_fake_move_detector(merged)
        reaction = merged.get('liquidation_reaction') if isinstance(merged.get('liquidation_reaction'), dict) else {}
        merged['fake_move_detector'] = {
            **(legacy_fake if isinstance(legacy_fake, dict) else {}),
            'state': str((reaction.get('acceptance') if isinstance(reaction, dict) else '') or (legacy_fake.get('state') if isinstance(legacy_fake, dict) else '') or 'NO_SWEEP').upper(),
            'summary': str((reaction.get('summary') if isinstance(reaction, dict) else '') or (legacy_fake.get('summary') if isinstance(legacy_fake, dict) else '') or 'реакция на блок пока не собрана'),
            'action': str((reaction.get('acceptance') if isinstance(reaction, dict) else '') or (legacy_fake.get('action') if isinstance(legacy_fake, dict) else '') or '').upper(),
        }
        merged['soft_signal'] = build_soft_signal(merged)
        merged['move_projection'] = build_move_projection(merged)
        merged['bot_authority_v2'] = build_bot_authority(merged.get('decision', {}) if isinstance(merged.get('decision'), dict) else {}, merged)
    except Exception:
        merged['nextgen_layers_error'] = traceback.format_exc()[:1200]
    return merged




def _normalize_pattern_memory_for_renderer(pattern_ctx: Dict[str, Any], current_price: float | None = None) -> Dict[str, Any]:
    pattern_ctx = dict(pattern_ctx or {})
    direction = str(
        pattern_ctx.get('direction')
        or pattern_ctx.get('direction_bias')
        or pattern_ctx.get('pattern_bias')
        or pattern_ctx.get('forecast_direction')
        or 'НЕЙТРАЛЬНО'
    ).upper()
    if direction in {'UP', 'LONG', 'BULLISH'}:
        direction = 'ЛОНГ'
    elif direction in {'DOWN', 'SHORT', 'BEARISH'}:
        direction = 'ШОРТ'
    elif direction in {'NEUTRAL', 'NONE'}:
        direction = 'НЕЙТРАЛЬНО'
    pattern_ctx['direction'] = direction
    matches = int(pattern_ctx.get('matched_count') or pattern_ctx.get('matches') or 0)
    pattern_ctx['matched_count'] = matches
    conf = pattern_ctx.get('confidence')
    if conf is None:
        conf = pattern_ctx.get('score') or pattern_ctx.get('probability') or 0.0
    try:
        conf = float(conf)
        if conf <= 1.0:
            conf *= 100.0
    except Exception:
        conf = 0.0
    pattern_ctx['confidence'] = round(max(0.0, min(conf, 100.0)), 1)
    years = pattern_ctx.get('source_years') or pattern_ctx.get('years') or []
    if isinstance(years, (str, int)):
        years = [years]
    if not years and matches > 0:
        years = [2024, 2025, 2026]
    pattern_ctx['source_years'] = list(years)
    avg_move = pattern_ctx.get('avg_future_return')
    if avg_move is None:
        avg_move = pattern_ctx.get('avg_move')
    try:
        if avg_move is not None:
            pattern_ctx['avg_future_return'] = float(avg_move)
    except Exception:
        pass
    summary = str(pattern_ctx.get('summary') or '').strip()
    if not summary:
        if matches > 0:
            bias_word = 'вверх' if direction == 'ЛОНГ' else 'вниз' if direction == 'ШОРТ' else 'нейтрально'
            summary = f'похожие участки чаще отрабатывали {bias_word}'
        else:
            summary = 'история паттернов ещё набирается'
    pattern_ctx['summary'] = summary
    return pattern_ctx


def _normalize_volume_confirmation_for_renderer(merged: Dict[str, Any]) -> Dict[str, Any]:
    orderflow = merged.get('orderflow_context') if isinstance(merged.get('orderflow_context'), dict) else {}
    volume = merged.get('volume_confirmation') if isinstance(merged.get('volume_confirmation'), dict) else {}
    micro = merged.get('microstructure') if isinstance(merged.get('microstructure'), dict) else {}
    rel = orderflow.get('relative_volume') or orderflow.get('volume_ratio') or micro.get('volume_ratio') or volume.get('relative_volume') or 1.0
    try:
        rel = float(rel)
    except Exception:
        rel = 1.0
    bias = str(volume.get('delta_side') or orderflow.get('bias') or orderflow.get('delta_side') or 'BALANCE').upper()
    if bias in {'BUY', 'BUYER', 'BULL', 'UP'}:
        bias = 'BUYER'
    elif bias in {'SELL', 'SELLER', 'BEAR', 'DOWN'}:
        bias = 'SELLER'
    else:
        bias = 'BALANCE'
    base_summary = str(volume.get('summary') or '').strip()
    order_summary = str(orderflow.get('summary') or '').strip()
    if not base_summary:
        if rel >= 1.35:
            base_summary = 'объём выше среднего, движение подтверждается'
        elif rel <= 0.8:
            base_summary = 'объём слабый, движение без сильного подтверждения'
        else:
            base_summary = 'объём близок к среднему, нужен контекст реакции'
    volume['relative_volume'] = rel
    volume['delta_side'] = bias
    volume['summary'] = base_summary
    if order_summary:
        orderflow['summary'] = order_summary
    elif bias == 'BUYER':
        orderflow['summary'] = 'агрессивный покупатель чуть активнее продавца'
    elif bias == 'SELLER':
        orderflow['summary'] = 'агрессивный продавец чуть активнее покупателя'
    else:
        orderflow['summary'] = 'явного перевеса по потоку нет'
    merged['volume_confirmation'] = volume
    merged['orderflow_context'] = orderflow
    return merged


def _normalize_impulse_character_for_renderer(merged: Dict[str, Any]) -> Dict[str, Any]:
    impulse = merged.get('impulse_character') if isinstance(merged.get('impulse_character'), dict) else {}
    reaction = merged.get('liquidation_reaction') if isinstance(merged.get('liquidation_reaction'), dict) else {}
    vol = merged.get('volume_confirmation') if isinstance(merged.get('volume_confirmation'), dict) else {}
    if impulse.get('state') and impulse.get('comment') and impulse.get('quality'):
        return merged
    rel = float(vol.get('relative_volume') or 1.0)
    acceptance = str(reaction.get('acceptance') or '').upper()
    if acceptance in {'BUY_SIDE_SWEEP_REJECTED', 'SELL_SIDE_SWEEP_REJECTED', 'REJECTED'}:
        state = 'FADE'
        comment = 'похоже на ложный вынос, идёт возврат после сбора ликвидности'
        quality = 'REVERSAL'
        strength = 'MEDIUM'
    elif rel >= 1.4:
        state = 'IMPULSE'
        comment = 'движение поддержано объёмом, continuation возможен'
        quality = 'EXPANDING'
        strength = 'HIGH'
    elif rel <= 0.85:
        state = 'CHOP'
        comment = 'объём слабый, движение больше похоже на реакцию внутри диапазона'
        quality = 'CHOPPY'
        strength = 'LOW'
    else:
        state = str(impulse.get('state') or 'BALANCED')
        comment = str(impulse.get('comment') or 'движение есть, но без чистого continuation')
        quality = str(impulse.get('quality') or 'MIXED')
        strength = str(impulse.get('strength') or 'MEDIUM')
    impulse['state'] = state
    impulse['comment'] = comment
    impulse['quality'] = quality
    impulse['strength'] = strength
    merged['impulse_character'] = impulse
    return merged


def _build_renderer_friendly_v14_snapshot(merged: Dict[str, Any], authority: Dict[str, Any], grid_authority: Dict[str, Any]) -> Dict[str, Any]:
    decision = merged.get('decision') if isinstance(merged.get('decision'), dict) else {}
    reaction = merged.get('liquidation_reaction') if isinstance(merged.get('liquidation_reaction'), dict) else {}
    blocks = merged.get('liquidity_blocks') if isinstance(merged.get('liquidity_blocks'), dict) else {}
    pattern = merged.get('pattern_memory_v2') if isinstance(merged.get('pattern_memory_v2'), dict) else {}
    impulse = merged.get('impulse_character') if isinstance(merged.get('impulse_character'), dict) else {}
    rng_low = merged.get('range_low')
    rng_mid = merged.get('range_mid')
    rng_high = merged.get('range_high')
    price = merged.get('price')
    try:
        low = float(rng_low) if rng_low is not None else None
        mid = float(rng_mid) if rng_mid is not None else None
        high = float(rng_high) if rng_high is not None else None
        px = float(price) if price is not None else None
    except Exception:
        low = mid = high = px = None
    location_state = 'MID'
    pos_pct = 50.0
    if px is not None and low is not None and high is not None and high > low:
        pos_pct = max(0.0, min(100.0, ((px - low) / (high - low)) * 100.0))
        if pos_pct >= 80:
            location_state = 'UPPER_EDGE'
        elif pos_pct >= 60:
            location_state = 'UPPER_PART'
        elif pos_pct <= 20:
            location_state = 'LOWER_EDGE'
        elif pos_pct <= 40:
            location_state = 'LOWER_PART'
        else:
            location_state = 'MID'
    direction = str(authority.get('direction') or decision.get('direction') or merged.get('final_decision') or 'НЕЙТРАЛЬНО').upper()
    action = str(authority.get('action') or decision.get('action') or 'WATCH_ZONE').upper()
    state = str(authority.get('state') or decision.get('action_text') or action).upper()
    summary = str(authority.get('summary') or decision.get('summary') or '').strip()
    if not summary:
        summary = str(reaction.get('summary') or impulse.get('comment') or pattern.get('summary') or 'нет данных').strip()
    setup_note = str(authority.get('setup_note') or '').strip()
    if not setup_note:
        setup_note = str(reaction.get('summary') or '').strip()
    entry_hint = str(authority.get('entry_hint') or decision.get('entry_hint') or '').strip()
    if not entry_hint:
        entry_hint = str(reaction.get('watch') or reaction.get('watch_text') or 'касание блока + возврат / удержание').strip()
    invalidation = str(authority.get('invalidation') or decision.get('invalidation') or '').strip()
    if not invalidation:
        upper = blocks.get('upper_block') if isinstance(blocks.get('upper_block'), dict) else {}
        lower = blocks.get('lower_block') if isinstance(blocks.get('lower_block'), dict) else {}
        if direction == 'ШОРТ' and upper.get('high'):
            invalidation = f"закрепление выше {float(upper.get('high')):.2f} ломает short-сценарий"
        elif direction == 'ЛОНГ' and lower.get('low'):
            invalidation = f"закрепление ниже {float(lower.get('low')):.2f} ломает long-сценарий"
        else:
            invalidation = 'без подтверждённой реакции идея неактивна'
    return {
        'direction': direction,
        'decision_action': action,
        'state': state,
        'summary': summary,
        'setup_note': setup_note,
        'entry_hint': entry_hint,
        'invalidation': invalidation,
        'pattern_bias': str(pattern.get('direction') or pattern.get('pattern_bias') or direction).upper(),
        'reaction_state': str(reaction.get('acceptance') or reaction.get('state') or 'NONE').upper(),
        'grid_action': str(authority.get('grid_action') or grid_authority.get('status') or 'WATCH').upper(),
        'location_state': location_state,
        'range_position_pct': round(pos_pct, 1),
    }

def _apply_v14_decision_takeover(merged: Dict[str, Any]) -> Dict[str, Any]:
    """Compatibility wrapper that now runs a pure V15 decision takeover.
    Kept to avoid changing call sites, but V14 authority is no longer used.
    """
    decision = merged.get('decision') if isinstance(merged.get('decision'), dict) else {}
    authority = build_decision_authority_v15(merged, decision)
    grid_authority = build_grid_execution_authority_v15(merged, authority)

    _legacy_snapshot = build_v14_output_contract(merged, decision, authority)
    v14_snapshot = _build_renderer_friendly_v14_snapshot(merged, authority, grid_authority)
    for _k, _v in (_legacy_snapshot or {}).items():
        v14_snapshot.setdefault(_k, _v)

    merged['v14_snapshot'] = v14_snapshot
    merged['decision_authority_v15'] = authority
    merged['grid_execution_authority_v15'] = grid_authority

    new_decision = dict(decision)
    direction = authority.get('direction') or new_decision.get('direction') or 'NEUTRAL'
    action = authority.get('action') or 'WATCH_ZONE'
    state = authority.get('state') or action
    summary = authority.get('summary') or new_decision.get('summary') or 'нет данных'
    setup_note = authority.get('setup_note') or ''
    why = list(authority.get('why') or [])
    invalidation = authority.get('invalidation') or new_decision.get('invalidation') or ''
    edge_score = float(authority.get('edge_score') or 0.0)
    edge_label = str(authority.get('edge_label') or 'WATCH').upper()

    new_decision['direction'] = direction
    new_decision['action'] = action
    new_decision['action_text'] = state
    new_decision['state'] = state
    new_decision['summary'] = summary
    new_decision['why'] = why
    new_decision['setup_note'] = setup_note
    new_decision['entry_hint'] = authority.get('entry_hint') or new_decision.get('entry_hint')
    new_decision['invalidation'] = invalidation
    new_decision['invalidation_reason'] = invalidation
    new_decision['edge_score'] = edge_score
    new_decision['edge_label'] = edge_label
    new_decision['trade_authorized'] = action.startswith('EXECUTE_')
    new_decision['setup_valid'] = action.startswith('EXECUTE_') or action.startswith('ARM_')
    new_decision['manager_action'] = 'MANAGE' if action.startswith('EXECUTE_') else action
    new_decision['manager_action_text'] = 'ВЕСТИ ПОЗИЦИЮ' if action.startswith('EXECUTE_') else state
    new_decision['best_trade_play'] = state.lower()
    new_decision['best_trade_play_id'] = state.lower()
    new_decision['best_trade_score'] = edge_score
    new_decision['expectation_text'] = setup_note or summary
    new_decision['regime'] = str(new_decision.get('regime') or merged.get('trade_style') or merged.get('market_mode') or 'RANGE')

    pattern = merged.get('pattern_memory_v2') if isinstance(merged.get('pattern_memory_v2'), dict) else {}
    reaction = merged.get('liquidation_reaction') if isinstance(merged.get('liquidation_reaction'), dict) else {}
    pin = merged.get('pinbar_context') if isinstance(merged.get('pinbar_context'), dict) else {}
    volume = merged.get('volume_confirmation') if isinstance(merged.get('volume_confirmation'), dict) else {}
    blocks = merged.get('liquidity_blocks') if isinstance(merged.get('liquidity_blocks'), dict) else {}

    summary_lines = [
        f"режим: {new_decision['regime']}",
        f"сейчас: {summary}",
        f"реакция на блок: {reaction.get('summary') or 'реакция ещё не собрана'}",
        f"паттерн: {pattern.get('summary') or 'история паттернов ещё набирается'}",
        f"пинбар: {pin.get('summary') or 'свечной сигнал не подтверждён'}",
        f"объём: {volume.get('summary') or 'объём нейтрален'}",
    ]
    launch_lines = []
    if authority.get('entry_hint'):
        launch_lines.append(authority.get('entry_hint'))
    ub = blocks.get('upper_block') if isinstance(blocks.get('upper_block'), dict) else {}
    lb = blocks.get('lower_block') if isinstance(blocks.get('lower_block'), dict) else {}
    if ub:
        launch_lines.append(f"верхний блок: {float(ub.get('low') or 0):.2f}–{float(ub.get('high') or 0):.2f}")
    if lb:
        launch_lines.append(f"нижний блок: {float(lb.get('low') or 0):.2f}–{float(lb.get('high') or 0):.2f}")
    invalidation_lines = [invalidation] if invalidation else []
    merged['action_output'] = {
        'title': '⚡ ЧТО ДЕЛАТЬ',
        'market_mode': new_decision['regime'],
        'directional_action': action,
        'summary_lines': summary_lines[:6],
        'launch_lines': launch_lines[:4],
        'invalidation_lines': invalidation_lines[:2],
    }

    grid_long = grid_authority.get('long_grid') or ('ARM' if action.startswith('ARM_LONG') or direction == 'ЛОНГ' and action.startswith('ARM_') else 'HOLD')
    grid_short = grid_authority.get('short_grid') or ('ARM' if action.startswith('ARM_SHORT') or direction == 'ШОРТ' and action.startswith('ARM_') else 'HOLD')
    merged['bot_authority_v2'] = {
        'status': grid_authority.get('status') or ('ACTIVE' if action.startswith('EXECUTE_') else 'ARMING' if action.startswith('ARM_') else 'WATCH'),
        'action': action,
        'reason': grid_authority.get('reason') or setup_note or summary,
        'master_mode': state,
        'authority': 'AUTHORIZED' if action.startswith('EXECUTE_') else 'SOFT_AUTHORIZED' if action.startswith('ARM_') else 'WATCH',
        'cards': merged.get('bot_authority_v2', {}).get('cards', []) if isinstance(merged.get('bot_authority_v2'), dict) else [],
    }

    merged['grid_cmd'] = {
        'long_grid': grid_long,
        'short_grid': grid_short,
    }

    merged['decision'] = new_decision
    merged['signal'] = direction
    merged['final_decision'] = direction
    merged['forecast_direction'] = direction
    merged['decision_summary'] = summary
    return merged


class AnalysisRequestContext:
    def __init__(self, trace: RequestTrace | None = None) -> None:
        self._analysis_cache: Dict[str, AnalysisSnapshot] = {}
        self.started_at = time.time()
        self.trace = trace

    def get_snapshot(self, timeframe: str) -> AnalysisSnapshot:
        tf = timeframe or DEFAULT_TF
        if tf in self._analysis_cache:
            return self._analysis_cache[tf]

        now = time.time()
        cached = _GLOBAL_ANALYSIS_CACHE.get(tf)
        if cached and (now - cached[0]) <= _GLOBAL_ANALYSIS_TTL_SEC:
            snap = cached[1]
            self._analysis_cache[tf] = snap
            if self.trace is not None:
                self.trace.mark(f"analysis:{tf}:global_cache")
            return snap

        snap = call_btc_analysis(tf)
        _GLOBAL_ANALYSIS_CACHE[tf] = (now, snap)
        self._analysis_cache[tf] = snap
        if self.trace is not None:
            self.trace.mark(f"analysis:{tf}")
        return snap

    def get_analysis(self, timeframe: str) -> Dict[str, Any]:
        return self.get_snapshot(timeframe).to_dict()

    def has_snapshot(self, timeframe: str) -> bool:
        tf = timeframe or DEFAULT_TF
        return tf in self._analysis_cache

    def summary_lines(self) -> List[str]:
        elapsed_ms = int((time.time() - self.started_at) * 1000)
        cache_info = get_klines_cache_info()
        lines = [
            f"request time: {elapsed_ms} ms",
            f"analysis snapshots in request: {len(self._analysis_cache)}",
            f"market cache ttl: {int(cache_info.get('ttl_seconds') or 0)} sec",
            f"market cache entries: {int(cache_info.get('entries') or 0)}",
        ]
        if self.trace is not None:
            lines.insert(0, f"request id: {self.trace.request_id}")
            lines.append(f"request marks: {self.trace.marks_text()}")
        return lines


def normalize_tf(text: str) -> str:
    t = (text or "").lower()
    # Важно: сначала проверяем более длинные таймфреймы,
    # иначе "15m" ошибочно матчится как "5m".
    if "15m" in t:
        return "15m"
    if "5m" in t:
        return "5m"
    if "4h" in t:
        return "4h"
    if "1d" in t:
        return "1d"
    return "1h"


def try_call_variants(func: Callable, variants: List[Callable[[], Any]]) -> Dict[str, Any]:
    last_error = None
    for caller in variants:
        try:
            return {"ok": True, "result": caller(), "error": None}
        except Exception as exc:
            last_error = exc
    return {
        "ok": False,
        "result": None,
        "error": f"{type(last_error).__name__}: {last_error}" if last_error else "unknown error",
    }




def _ensure_market_basics(merged: Dict[str, Any], symbol: str, timeframe: str) -> Dict[str, Any]:
    price = merged.get("price")
    try:
        price_num = float(price) if price is not None else 0.0
    except Exception:
        price_num = 0.0

    if price_num <= 0.0:
        try:
            df = load_klines(symbol=symbol, timeframe=timeframe, limit=120, use_cache=True)
            if df is not None and not df.empty and "close" in df.columns:
                recovered_price = float(df["close"].iloc[-1])
                if recovered_price > 0:
                    merged["price"] = round(recovered_price, 2)
                    merged.setdefault("analysis", {})
                    merged["analysis"]["market_data_recovered"] = True
        except Exception:
            merged.setdefault("analysis", {})
            merged["analysis"]["market_data_recovered"] = False

    if not merged.get("decision_summary") and isinstance(merged.get("decision"), dict):
        merged["decision_summary"] = str(merged["decision"].get("summary") or "")

    return merged

def build_minimal_fallback(symbol: str, timeframe: str) -> Dict[str, Any]:
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "price": None,
        "signal": "НЕЙТРАЛЬНО",
        "final_decision": "НЕЙТРАЛЬНО",
        "forecast_direction": "НЕЙТРАЛЬНО",
        "forecast_confidence": 0.0,
        "reversal_signal": "NO_REVERSAL",
        "reversal_confidence": 0.0,
        "reversal_patterns": [],
        "range_state": "позиция в диапазоне не определена",
        "range_low": None,
        "range_mid": None,
        "range_high": None,
        "ct_now": "контртренд: явного перекоса нет",
        "ginarea_advice": "нет данных",
        "decision_summary": "",
        "analysis": {},
        "stats": {},
    }


def enrich_range_fallback(data: Dict[str, Any]) -> Dict[str, Any]:
    low = data.get("range_low")
    mid = data.get("range_mid")
    high = data.get("range_high")
    price = data.get("price")
    if mid is None and low is not None and high is not None:
        data["range_mid"] = (float(low) + float(high)) / 2.0
    if low is None and mid is None and high is None and price is not None:
        p = float(price)
        data["range_low"] = p * 0.992
        data["range_mid"] = p
        data["range_high"] = p * 1.008
    if not data.get("range_state"):
        data["range_state"] = "позиция в диапазоне не определена"
    return data


def enrich_with_decision(data: Dict[str, Any]) -> Dict[str, Any]:
    normalized = normalize_analysis_payload(data)
    if combine_trade_decision is None:
        normalized.setdefault("decision", {})
        return normalized
    try:
        return combine_trade_decision(normalized)
    except Exception:
        normalized["decision_engine_error"] = traceback.format_exc()[:1000]
        normalized.setdefault("decision", {})
        return normalized



def _inject_real_liq_bias(data: Dict[str, Any]) -> Dict[str, Any]:
    decision = data.get('decision') if isinstance(data.get('decision'), dict) else {}
    coinglass = data.get('coinglass_context') if isinstance(data.get('coinglass_context'), dict) else {}
    if not decision:
        data['decision'] = decision
    feed_health = str(coinglass.get('feed_health') or '').upper()
    magnet = str(decision.get('liquidation_magnet') or coinglass.get('magnet_side') or 'NEUTRAL').upper()
    liq_state_live = str(decision.get('liquidity_state_live') or '').upper()
    if feed_health:
        decision['real_liq_feed'] = feed_health
        decision['real_liq_summary'] = str(coinglass.get('feed_summary') or '')
        decision['real_liq_stale_seconds'] = int(coinglass.get('feed_stale_seconds') or 0)
    if feed_health in {'LIVE', 'METRICS_ONLY'}:
        note = f"REAL-LIQ {feed_health}"
        if feed_health == 'LIVE' and decision.get('action_now') == 'ЖДАТЬ':
            if magnet == 'UP' and liq_state_live in {'UP_MAGNET', 'BUY_SIDE_SWEEP_REJECTED'}:
                decision['action_now'] = 'ЖДАТЬ ВЫНОС ВВЕРХ / РЕАКЦИЮ'
                decision['action_note'] = f"{note} | магнит вверх"
            elif magnet == 'DOWN' and liq_state_live in {'DOWN_MAGNET', 'SELL_SIDE_SWEEP_REJECTED'}:
                decision['action_now'] = 'ЖДАТЬ ВЫНОС ВНИЗ / РЕАКЦИЮ'
                decision['action_note'] = f"{note} | магнит вниз"
        elif feed_health == 'METRICS_ONLY' and not decision.get('action_note'):
            decision['action_note'] = note
    return data


def call_btc_analysis(timeframe: str) -> AnalysisSnapshot:
    symbol = "BTCUSDT"
    logger.info("analysis.start symbol=%s timeframe=%s", symbol, timeframe)
    merged = build_minimal_fallback(symbol, timeframe)

    loaders = [
        (load_btc_analyzer(), None),
        (
            load_range_analyzer(),
            ["range_low", "range_mid", "range_high", "range_state", "range_position"],
        ),
        (
            load_ginarea_analyzer(),
            [
                "ginarea_advice",
                "ct_now",
                "final_decision",
                "forecast_direction",
                "forecast_confidence",
                "signal",
                "entry_zone",
                "stop_loss",
                "take_profit",
                "range_low",
                "range_mid",
                "range_high",
                "range_state",
                "decision_summary",
                "reversal_signal",
                "reversal_confidence",
                "reversal_patterns",
                "unified_advice",
                "trade_style",
                "preferred_bot",
                "hold_bias",
                "scalp_only",
                "confirmation_needed",
                "reentry_zone",
                "invalidation_hint",
                "tactical_plan",
                "bot_cards",
                "best_bot",
                "best_bot_label",
                "best_bot_status",
                "best_bot_score",
                "execution_bias",
                "scalp_bot_label",
                "intraday_bot_label",
                "avoid_bot_label",
                "avoid_bot_reason",
                "matrix_summary",
                "dangerous_bots",
                "recommended_sequence",
                "management_summary",
                "range_management",
                "ct_management",
                "state_summary",
                "active_bots_now",
                "bot_manager_state",
                "custom_bot_labels",
                "manual_summary",
                "unified_strategy_matrix",
                "overlay_commentary",
                "spy_context",
                "history_pattern_direction",
                "history_pattern_confidence",
                "history_pattern_summary",
                "deviation_ladder",
                "mean60_price",
                "deviation_pct",
                "ladder_action",
                "range_bias_action",
            ],
        ),
    ]

    for loader, keys in loaders:
        if loader is None:
            continue

        res = try_call_variants(
            loader,
            [
                lambda l=loader: l(symbol, timeframe),
                lambda l=loader: l(symbol=symbol, timeframe=timeframe),
                lambda l=loader: l(timeframe=timeframe),
                lambda l=loader: l(symbol),
                lambda l=loader: l(),
            ],
        )

        if not res["ok"]:
            logger.warning(
                "analysis.loader_failed symbol=%s timeframe=%s loader=%s error=%s",
                symbol,
                timeframe,
                getattr(loader, "__name__", repr(loader)),
                res["error"],
            )
            continue

        raw_result = res["result"] if isinstance(res["result"], dict) else {"raw": res["result"]}
        payload = normalize_analysis_payload(raw_result, symbol=symbol, timeframe=timeframe)
        merged.setdefault("analysis", {})
        if isinstance(raw_result, dict):
            merged["analysis"].update(raw_result)
        merged["analysis"].update({k: v for k, v in payload.items() if k not in {"analysis", "df"}})
        if keys is None:
            merged.update(payload)
        else:
            for key in keys:
                if payload.get(key) is not None:
                    if _should_override_merge(key, merged.get(key), payload.get(key)):
                        continue
                    merged[key] = payload.get(key)

    merged = normalize_analysis_payload(merged, symbol=symbol, timeframe=timeframe)
    merged = _apply_learning_forecast_weight(merged)
    merged = enrich_range_fallback(merged)
    merged = enrich_with_decision(merged)
    merged = _sync_nextgen_layers_into_merged(merged, merged.get('decision') if isinstance(merged.get('decision'), dict) else {})
    merged = _ensure_market_basics(merged, symbol=symbol, timeframe=timeframe)
    merged = _enrich_with_nextgen_layers(merged)

    try:
        merged['setup_stats'] = build_setup_stats_context(merged)
        setup_adj = build_setup_learning_adjustment(merged.get('setup_stats', {}), merged)
        merged['setup_stats_adjustment'] = setup_adj
        merged['learning_execution_plan'] = build_learning_execution_plan(merged.get('setup_stats', {}), setup_adj, merged)
        merged.setdefault('analysis', {})
        merged['analysis']['setup_stats'] = merged['setup_stats']
        merged['analysis']['setup_stats_adjustment'] = setup_adj
        merged['analysis']['learning_execution_plan'] = merged['learning_execution_plan']
        decision = merged.get('decision') if isinstance(merged.get('decision'), dict) else {}
        if decision:
            conf = float(decision.get('confidence_pct') or decision.get('confidence') or 0.0)
            conf = max(0.0, min(95.0, conf + float(setup_adj.get('delta') or 0.0) * 100.0))
            decision['confidence_pct'] = round(conf, 1)
            decision['confidence'] = round(conf / 100.0, 3)
            decision['setup_stats_summary'] = str((merged.get('setup_stats') or {}).get('summary') or 'нет данных')
            decision['setup_stats_delta'] = round(float(setup_adj.get('delta') or 0.0) * 100.0, 2)
            decision['setup_stats_reasons'] = list(setup_adj.get('reasons') or [])[:3]
            if float(setup_adj.get('delta') or 0.0) <= -0.03 and str(decision.get('action_text') or '').upper() not in {'ЖДАТЬ', 'WAIT'}:
                decision['action_note'] = ((str(decision.get('action_note') or '') + ' | ') if decision.get('action_note') else '') + 'SETUP STATS: осторожно, исторический edge слабее'
            elif float(setup_adj.get('delta') or 0.0) >= 0.03:
                decision['action_note'] = ((str(decision.get('action_note') or '') + ' | ') if decision.get('action_note') else '') + 'SETUP STATS: личная статистика поддерживает сценарий'
            merged['decision'] = decision
    except Exception:
        merged['setup_stats_error'] = traceback.format_exc()[:1200]

    try:
        ml_ctx = merged.get('ml_v2') if isinstance(merged.get('ml_v2'), dict) else {}
        decision = merged.get('decision') if isinstance(merged.get('decision'), dict) else {}
        if decision and ml_ctx:
            base_prob = float(ml_ctx.get('probability') or 0.5)
            edge_strength = float(ml_ctx.get('edge_strength') or 0.0)
            ml_delta = 0.0
            if edge_strength >= 0.10:
                ml_delta = (base_prob - 0.5) * (16.0 if str(ml_ctx.get('model_status')) == 'trained' else 8.0)
            conf = float(decision.get('confidence_pct') or decision.get('confidence') or 0.0)
            conf = max(0.0, min(97.0, conf + ml_delta))
            decision['confidence_pct'] = round(conf, 1)
            decision['confidence'] = round(conf / 100.0, 3)
            decision['ml_probability'] = round(base_prob, 4)
            decision['ml_setup_type'] = str(ml_ctx.get('setup_type') or 'unknown')
            decision['ml_model_status'] = str(ml_ctx.get('model_status') or 'unknown')
            decision['ml_edge_strength'] = round(edge_strength, 4)
            decision['follow_through_probability'] = float(ml_ctx.get('follow_through_probability') or 0.5)
            decision['reversal_probability'] = float(ml_ctx.get('reversal_probability') or 0.5)
            decision['setup_quality_probability'] = float(ml_ctx.get('setup_quality_probability') or 0.5)
            ml_note = f"ML V6.3: {decision['ml_setup_type']} | prob {base_prob * 100:.1f}% | edge {edge_strength * 100:.1f}% | status {decision['ml_model_status']}"
            if edge_strength >= 0.18:
                decision['action_note'] = ((str(decision.get('action_note') or '') + ' | ') if decision.get('action_note') else '') + ml_note
            else:
                decision.setdefault('action_note', ml_note)
            merged['decision'] = decision
            merged.setdefault('analysis', {})
            merged['analysis']['ml_v2'] = ml_ctx
    except Exception:
        merged['ml_v2_adjustment_error'] = traceback.format_exc()[:1200]

    try:
        merged['multi_tf_context'] = build_multi_tf_context(merged)
        merged.setdefault('analysis', {})
        merged['analysis']['multi_tf_context'] = merged['multi_tf_context']
        decision = merged.get('decision') if isinstance(merged.get('decision'), dict) else {}
        mtf = merged.get('multi_tf_context') if isinstance(merged.get('multi_tf_context'), dict) else {}
        if decision and mtf:
            decision['multi_tf_alignment'] = mtf.get('alignment')
            decision['multi_tf_action'] = mtf.get('action')
            decision['multi_tf_summary'] = mtf.get('summary')
            decision['multi_tf_risk_modifier'] = mtf.get('risk_modifier')
            if mtf.get('alignment') == 'FULL ALIGNMENT':
                conf = float(decision.get('confidence_pct') or decision.get('confidence') or 0.0)
                conf = max(0.0, min(97.0, conf + 3.0))
                decision['confidence_pct'] = round(conf, 1)
                decision['confidence'] = round(conf / 100.0, 3)
            elif mtf.get('alignment') in {'CONFLICT', 'WEAK ALIGNMENT'}:
                conf = float(decision.get('confidence_pct') or decision.get('confidence') or 0.0)
                conf = max(0.0, min(97.0, conf - 4.0))
                decision['confidence_pct'] = round(conf, 1)
                decision['confidence'] = round(conf / 100.0, 3)
                note = 'MULTI-TF: есть конфликт ТФ, размер и агрессию лучше снизить'
                decision['action_note'] = ((str(decision.get('action_note') or '') + ' | ') if decision.get('action_note') else '') + note
            merged['decision'] = decision
    except Exception:
        merged['multi_tf_error'] = traceback.format_exc()[:1200]

    try:
        merged["grid_strategy"] = build_three_bot_grid_strategy(merged)
        merged["grid_active_bots"] = list((merged.get("grid_strategy") or {}).get("active_bots") or [])
        merged["grid_summary"] = str((merged.get("grid_strategy") or {}).get("summary") or "")
    except Exception:
        merged["grid_strategy"] = {"enabled": False, "summary": "grid strategy unavailable"}
        merged["grid_active_bots"] = []
        merged["grid_summary"] = "grid strategy unavailable"

    try:
        merged = _apply_v14_decision_takeover(merged)
    except Exception:
        merged['v14_takeover_error'] = traceback.format_exc()[:1200]

    merged.setdefault('analysis', {})
    if isinstance(merged.get('decision'), dict):
        for key in ('fake_move_detector','move_type_context','bot_mode_context','range_bot_permission','action_output','bot_mode_action','directional_action','soft_signal','move_projection'):
            if key in merged['decision']:
                merged['analysis'][key] = merged['decision'].get(key)
        merged['analysis']['decision'] = merged['decision']

    logger.info(
        "analysis.done symbol=%s timeframe=%s signal=%s final_decision=%s decision_keys=%s",
        symbol,
        timeframe,
        merged.get("signal"),
        merged.get("final_decision"),
        sorted((merged.get("decision") or {}).keys()) if isinstance(merged.get("decision"), dict) else "none",
    )
    return AnalysisSnapshot.from_dict(merged, symbol=symbol, timeframe=timeframe)
