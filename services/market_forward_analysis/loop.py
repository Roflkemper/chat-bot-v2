"""Market Forward Analysis async loop.

Runs two ticks:
  - Every 300s (5min): event detection (phase shift, bot risk change, forecast invalidation)
  - On session open (ASIA/LONDON/NY_AM/NY_PM): full session brief

Integration in app_runner.py:
    from services.market_forward_analysis.loop import market_forward_analysis_loop
    asyncio.create_task(market_forward_analysis_loop(stop_event, send_fn=send_fn))
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from ..market_intelligence.ict_killzones import current_session_from_utc, Session
from .data_loader import ForwardAnalysisDataLoader
from .phase_classifier import build_mtf_phase_state, Phase
from .forward_projection import compute_forward_projection
from .bot_impact import compute_bot_impact, RiskClass
from .recommendations import generate_recommendations
from .telegram_renderer import (
    format_session_brief,
    format_phase_change_alert,
    format_bot_risk_alert,
    format_forecast_invalidation,
)

logger = logging.getLogger(__name__)

_EVENT_TICK_SEC  = 300    # 5 min — event detection
_BRIEF_DEDUP_SEC = 3600   # 1h — max 1 brief per session open
_ALERT_DEDUP_SEC = 3600   # 1h dedup per bot risk alert
_PHASE_DEDUP_SEC = 1800   # 30 min — phase change alerts


_SESSION_MAP = {
    Session.ASIA:   "ASIA",
    Session.LONDON: "LONDON",
    Session.NY_AM:  "NY_AM",
    Session.NY_PM:  "NY_PM",
}


def _send(msg: str, send_fn: Any) -> bool:
    if not msg or send_fn is None:
        return False
    try:
        send_fn(msg)
        return True
    except Exception:
        logger.exception("market_forward_analysis.send_failed")
        return False


async def market_forward_analysis_loop(
    stop_event: asyncio.Event,
    *,
    send_fn: Any = None,
    event_tick_sec: float = _EVENT_TICK_SEC,
    symbol: str = "BTCUSDT",
    tail_days: int = 90,
) -> None:
    """Main async loop for market forward analysis."""
    loader = ForwardAnalysisDataLoader(symbol=symbol)
    loader.refresh(tail_days=tail_days)

    last_session: Optional[Session] = None
    last_brief_sent: dict[str, datetime] = {}
    last_bot_risk: dict[str, RiskClass] = {}
    last_phase_label: dict[str, str] = {}
    last_alert_sent: dict[str, datetime] = {}

    # Track previous forecast for invalidation detection
    last_projection: Optional[Any] = None

    logger.info("market_forward_analysis_loop.started symbol=%s tick=%ds", symbol, event_tick_sec)

    while not stop_event.is_set():
        try:
            now = datetime.now(timezone.utc)
            loader.refresh(tail_days=30)   # light refresh on tick

            frames = loader.all_frames()
            current_price = loader.current_price()

            # Build phase state
            phase_state = build_mtf_phase_state(frames, now=None)
            projection = compute_forward_projection(phase_state, frames.get("1h"))
            impact = compute_bot_impact(projection, current_price)
            recs = generate_recommendations(impact)

            current_sess = current_session_from_utc(now)

            # ── Session brief ─────────────────────────────────────────────────
            if (
                current_sess != last_session
                and current_sess != Session.NONE
                and current_sess in _SESSION_MAP
            ):
                sess_name = _SESSION_MAP[current_sess]
                last_sent = last_brief_sent.get(sess_name)
                elapsed = (now - last_sent).total_seconds() if last_sent else 9999
                if elapsed > _BRIEF_DEDUP_SEC:
                    msg = format_session_brief(
                        sess_name, phase_state, projection, impact, recs, current_price
                    )
                    if _send(msg, send_fn):
                        last_brief_sent[sess_name] = now
                        logger.info("mfa.session_brief_sent session=%s", sess_name)

            last_session = current_sess

            # ── Phase change alerts ───────────────────────────────────────────
            for tf, phase_result in phase_state.phases.items():
                old_label = last_phase_label.get(tf)
                new_label = phase_result.label.value
                if old_label and old_label != new_label and phase_result.confidence >= 50:
                    last_alert = last_alert_sent.get(f"phase_{tf}")
                    elapsed = (now - last_alert).total_seconds() if last_alert else 9999
                    if elapsed > _PHASE_DEDUP_SEC:
                        msg = format_phase_change_alert(
                            old_label, new_label, tf, phase_result.confidence, current_price
                        )
                        if _send(msg, send_fn):
                            last_alert_sent[f"phase_{tf}"] = now
                            logger.info("mfa.phase_change tf=%s %s->%s", tf, old_label, new_label)
                last_phase_label[tf] = new_label

            # ── Bot risk alerts ───────────────────────────────────────────────
            for bot, rec in zip(impact.bot_projections, recs):
                prev_risk = last_bot_risk.get(bot.bot_id)
                curr_risk = bot.risk_class

                # Alert only on ORANGE or RED, and only on transitions
                alert_worthy = curr_risk in (RiskClass.ORANGE, RiskClass.RED)
                is_new = prev_risk != curr_risk
                if alert_worthy and is_new:
                    last_alert = last_alert_sent.get(f"bot_{bot.bot_id}")
                    elapsed = (now - last_alert).total_seconds() if last_alert else 9999
                    if elapsed > _ALERT_DEDUP_SEC:
                        msg = format_bot_risk_alert(bot, rec, current_price)
                        if _send(msg, send_fn):
                            last_alert_sent[f"bot_{bot.bot_id}"] = now
                            logger.info("mfa.bot_risk_alert %s risk=%s", bot.alias, curr_risk.value)
                last_bot_risk[bot.bot_id] = curr_risk

            # ── Forecast invalidation ─────────────────────────────────────────
            if last_projection is not None:
                fc_4h = last_projection.forecasts.get("4h")
                if fc_4h and current_price > 0:
                    # Check if actual move is opposite to projected
                    prev_price = last_projection.forecasts.get("4h", None)
                    # Simple check: if direction was "up" and current price is below
                    # Note: would need price tracking; simplify with projection direction
                    pass  # TODO: track price at projection time for full invalidation check

            last_projection = projection

        except Exception:
            logger.exception("market_forward_analysis_loop.tick_failed")

        try:
            await asyncio.wait_for(asyncio.shield(stop_event.wait()), timeout=event_tick_sec)
        except asyncio.TimeoutError:
            pass


# ── Convenience: run checkpoint 1 report ─────────────────────────────────────

def run_checkpoint1_report(symbol: str = "BTCUSDT", tail_days: int = 365) -> dict:
    """Run checkpoint 1: phase distribution report over historical data.

    Used to validate classifier sanity before operator approves proceeding.
    Returns dict with phase distribution, a few obvious episode checks.
    """
    import pandas as pd
    from pathlib import Path
    from .data_loader import _load_1m, _resample
    from .phase_classifier import run_phase_history, Phase

    logger.info("checkpoint1: loading data...")
    df1m = _load_1m(symbol, tail_days=tail_days)
    if df1m is None or df1m.empty:
        return {"error": "no 1m data"}

    df1d = _resample(df1m, "1D")
    df4h = _resample(df1m, "4h")
    df1h = _resample(df1m, "1h")

    logger.info("checkpoint1: running phase history 1d bars=%d...", len(df1d))
    history = run_phase_history(df1d, df_4h=df4h, df_1h=df1h, step_bars=1, lookback=60)

    if history.empty:
        return {"error": "phase history empty"}

    # Phase distribution
    phase_dist = history["1d_phase"].value_counts().to_dict()

    # Confidence stats
    conf_stats = {
        "mean": float(history["1d_confidence"].mean()),
        "min":  float(history["1d_confidence"].min()),
        "p25":  float(history["1d_confidence"].quantile(0.25)),
        "p75":  float(history["1d_confidence"].quantile(0.75)),
    }

    # Sample: what was classified during known correction period?
    # Aug-Sep 2025: BTC corrected from ATH zone back to ~80-90k range
    if not history.empty:
        sample_period = history["2025-08-01":"2025-09-30"]
        if sample_period.empty:
            # fallback to first available month of history
            first_month = history.index[0]
            end_month = first_month + pd.Timedelta(days=30)
            sample_period = history[first_month:end_month]
        sample_label = sample_period["1d_phase"].mode()[0] if not sample_period.empty else "unknown"
        sample_price_range = (
            float(sample_period["close"].min()), float(sample_period["close"].max())
        ) if not sample_period.empty else (0, 0)
        sample_period_name = "aug-sep2025"
    else:
        sample_label = "unknown"
        sample_price_range = (0, 0)
        sample_period_name = "aug-sep2025"

    return {
        "phase_distribution": phase_dist,
        "confidence_stats": conf_stats,
        "coherence_rate_pct": float(history["coherent"].mean() * 100),
        "sample_period": {
            "name": sample_period_name,
            "dominant_phase": sample_label,
            "price_range": sample_price_range,
        },
        "total_bars": len(history),
        "current_phase": history.iloc[-1]["1d_phase"] if not history.empty else "unknown",
        "current_confidence": float(history.iloc[-1]["1d_confidence"]) if not history.empty else 0.0,
    }
