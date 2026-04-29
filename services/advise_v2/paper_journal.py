"""Paper journal task for Phase 1.

Periodically generates advise_v2 signals from live data and appends them
to state/advise_signals.jsonl or state/advise_null_signals.jsonl.

Phase 1: observe only. No bot actions taken.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from .regime_adapter import map_regime_dict_to_advise_label
from .schemas import CurrentExposure, MarketContext
from .signal_generator import generate_signal
from .signal_logger import log_null_signal, log_signal

logger = logging.getLogger(__name__)

PAPER_JOURNAL_INTERVAL_SEC = 300

_ROOT = Path(__file__).resolve().parents[2]
_STATE_LATEST = _ROOT / "docs" / "STATE" / "state_latest.json"
_STATE_MAX_AGE_SEC = 600   # 10 min — warn if older


# ── RSI helper ────────────────────────────────────────────────────────────────

def _rsi(closes: list[float], window: int = 14) -> float:
    if len(closes) < window + 2:
        return 50.0
    s = pd.Series(closes, dtype=float)
    delta = s.diff()
    gain = delta.clip(lower=0).ewm(com=window - 1, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(com=window - 1, adjust=False).mean()
    last_loss = float(loss.iloc[-1])
    if last_loss == 0:
        return 100.0
    rs = float(gain.iloc[-1]) / last_loss
    return float(min(100.0, max(0.0, 100.0 - 100.0 / (1.0 + rs))))


# ── State reader ──────────────────────────────────────────────────────────────

def _read_state_latest() -> dict[str, Any]:
    try:
        data = json.loads(_STATE_LATEST.read_text(encoding="utf-8"))
        ts_str = data.get("ts", "")
        if ts_str:
            ts = datetime.fromisoformat(ts_str)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - ts).total_seconds()
            if age > _STATE_MAX_AGE_SEC:
                logger.warning("paper_journal: state_latest.json age=%.0fs > %ss", age, _STATE_MAX_AGE_SEC)
        return data
    except Exception as exc:
        logger.warning("paper_journal: state_latest read failed: %s", exc)
        return {}


# ── Context builders ──────────────────────────────────────────────────────────

def _build_market_context_sync(symbol: str = "BTCUSDT") -> MarketContext:
    from core.pipeline import build_full_snapshot
    from core.data_loader import load_klines

    snapshot = build_full_snapshot(symbol=symbol)
    regime = snapshot.get("regime", {})
    regime_label = map_regime_dict_to_advise_label(regime)

    modifiers = [m.lower() for m in regime.get("modifiers", []) if m.replace("_", "").isalpha()]

    # RSI from 1h klines (separate call — load_klines has 12s TTL cache)
    df_1h = load_klines(symbol=symbol, timeframe="1h", limit=50)
    rsi_1h = _rsi(df_1h["close"].tolist()) if not df_1h.empty else 50.0

    # price_change_5m_30bars
    df_5m = load_klines(symbol=symbol, timeframe="5m", limit=35)
    if len(df_5m) >= 31:
        c_now = float(df_5m["close"].iloc[-1])
        c_30 = float(df_5m["close"].iloc[-31])
        price_change_5m = round((c_now - c_30) / max(c_30, 1e-9) * 100, 4)
    else:
        price_change_5m = 0.0

    return MarketContext(
        price_btc=float(snapshot.get("price", 0.0)),
        regime_label=regime_label,
        regime_modifiers=modifiers,
        rsi_1h=rsi_1h,
        rsi_5m=None,
        price_change_5m_30bars_pct=price_change_5m,
        price_change_1h_pct=float(snapshot.get("delta_1h_pct") or 0.0),
        nearest_liq_below=None,
        nearest_liq_above=None,
    )


def _build_current_exposure_sync() -> CurrentExposure:
    state = _read_state_latest()
    exposure = state.get("exposure", {})

    shorts_btc = float(exposure.get("shorts_btc") or 0.0)
    longs_btc = float(exposure.get("longs_btc") or 0.0)
    net_btc = float(exposure.get("net_btc") or 0.0)

    try:
        from config import ADVISOR_DEPO_TOTAL
        depo_total = float(ADVISOR_DEPO_TOTAL or 0.0)
    except Exception:
        depo_total = 0.0

    available_usd = depo_total if depo_total > 0 else 1000.0

    # Estimate margin usage from total gross BTC × mark price
    price_btc = float(state.get("bots", [{}])[0].get("live", {}).get("mark") or 0.0)
    if price_btc <= 0 and state.get("bots"):
        price_btc = float(state["bots"][0].get("live", {}).get("avg_entry") or 80000.0)
    if price_btc <= 0:
        price_btc = 80000.0

    gross_btc = abs(shorts_btc) + abs(longs_btc)
    used_usd = gross_btc * price_btc
    free_margin_pct = max(0.0, min(100.0, (1.0 - used_usd / max(available_usd, 1.0)) * 100.0))
    margin_coef_pct = max(0.0, min(100.0, used_usd / max(available_usd, 1.0) * 100.0))

    return CurrentExposure(
        net_btc=net_btc,
        shorts_btc=min(0.0, shorts_btc),
        longs_btc=max(0.0, longs_btc),
        free_margin_pct=free_margin_pct,
        available_usd=available_usd,
        margin_coef_pct=margin_coef_pct,
    )


# ── Null reason heuristic ──────────────────────────────────────────────────────

def _null_reason(ctx: MarketContext, exp: CurrentExposure) -> str:
    if ctx.regime_label == "unknown":
        return "regime_unknown"
    if exp.free_margin_pct < 20.0:
        return "insufficient_margin"
    return "no_match_above_threshold"


# ── Core iteration ────────────────────────────────────────────────────────────

def _run_one_iteration_sync(signal_counter: int) -> None:
    try:
        market_ctx = _build_market_context_sync()
    except Exception as exc:
        logger.exception("paper_journal: market_context build failed: %s", exc)
        log_null_signal(reason="snapshot_failed", context={"error": str(exc)})
        return

    try:
        exposure = _build_current_exposure_sync()
    except Exception as exc:
        logger.exception("paper_journal: exposure build failed: %s", exc)
        log_null_signal(reason="exposure_failed", context={"error": str(exc)})
        return

    try:
        envelope = generate_signal(
            market_context=market_ctx,
            current_exposure=exposure,
            signal_counter=signal_counter,
        )
    except Exception as exc:
        logger.exception("paper_journal: generate_signal failed: %s", exc)
        log_null_signal(reason="generate_signal_error", context={"error": str(exc)})
        return

    if envelope is not None:
        log_signal(envelope)
        logger.info(
            "paper_journal: signal %s setup=%s regime=%s",
            envelope.signal_id, envelope.setup_id, market_ctx.regime_label,
        )
    else:
        reason = _null_reason(market_ctx, exposure)
        log_null_signal(
            reason=reason,
            context={
                "regime_label": market_ctx.regime_label,
                "rsi_1h": market_ctx.rsi_1h,
                "free_margin_pct": exposure.free_margin_pct,
            },
        )
        logger.debug("paper_journal: null signal reason=%s", reason)


# ── Async loop ────────────────────────────────────────────────────────────────

async def paper_journal_loop(
    *,
    interval_sec: int = PAPER_JOURNAL_INTERVAL_SEC,
    stop_event: asyncio.Event | None = None,
) -> None:
    """Async loop. Runs until stop_event is set. Each tick: build context → signal → log."""
    logger.info("paper_journal: loop started interval=%ds", interval_sec)
    signal_counter = 0
    while True:
        signal_counter += 1
        try:
            await asyncio.to_thread(_run_one_iteration_sync, signal_counter)
        except Exception as exc:
            logger.exception("paper_journal: iteration %d unexpected error: %s", signal_counter, exc)
        if stop_event and stop_event.is_set():
            logger.info("paper_journal: stop signaled")
            break
        try:
            wait_target = stop_event.wait() if stop_event else asyncio.sleep(interval_sec)
            await asyncio.wait_for(wait_target, timeout=float(interval_sec))
            if stop_event and stop_event.is_set():
                break
        except asyncio.TimeoutError:
            continue
    logger.info("paper_journal: loop stopped after %d iterations", signal_counter)
