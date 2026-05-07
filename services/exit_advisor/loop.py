"""Exit advisor async loop — runs every 60-300s, sends Telegram advisory alerts.

Integration point for app_runner.py:
    from services.exit_advisor.loop import exit_advisor_loop
    asyncio.create_task(exit_advisor_loop(stop_event, send_fn=send_fn))

Alert dedup:
  - Same scenario_class + side: 30 min window
  - Re-fires on severity escalation (scenario_class upgrade)
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .margin_calculator import MarginCalculator
from .outcome_tracker import OutcomeTracker
from .position_state import ScenarioClass, build_position_state
from .strategy_ranker import StrategyRanker
from .telegram_renderer import format_advisory_alert

logger = logging.getLogger(__name__)

_LOOP_INTERVAL_SEC = 120          # 2-min default tick
_DEDUP_WINDOW_SEC = 1800          # 30-min dedup per scenario_class
_ROOT = Path(__file__).resolve().parents[2]

# Severity ordering for escalation detection
_SEVERITY_ORDER = {
    ScenarioClass.MONITORING: 0,
    ScenarioClass.EARLY_INTERVENTION: 1,
    ScenarioClass.CYCLE_DEATH: 2,
    ScenarioClass.MODERATE: 3,
    ScenarioClass.SEVERE: 4,
    ScenarioClass.CRITICAL: 5,
    ScenarioClass.URGENT_PROTECTION: 6,
}


async def exit_advisor_loop(
    stop_event: asyncio.Event,
    *,
    send_fn: Any = None,
    interval_sec: float = _LOOP_INTERVAL_SEC,
    regime_fn: Any = None,       # optional: () -> str
    session_fn: Any = None,      # optional: () -> str
) -> None:
    """Main exit advisor loop."""
    import json as _json
    from pathlib import Path as _Path

    ranker = StrategyRanker()
    margin_calc = MarginCalculator()
    tracker = OutcomeTracker()

    dedup_cache: dict[str, datetime] = {}      # scenario_class.value → last_sent
    last_severity: int = 0

    # 2026-05-07: persist dd_onset_cache между рестартами app_runner.
    # Без этого после каждого рестарта duration сбрасывается до 0 и CYCLE_DEATH
    # alert (требует max_dur_h >= 4h) никогда не срабатывает.
    _DD_CACHE_PATH = _Path("data/exit_advisor/dd_onset_cache.json")
    dd_onset_cache: dict[str, datetime] = {}
    try:
        if _DD_CACHE_PATH.exists():
            raw = _json.loads(_DD_CACHE_PATH.read_text(encoding="utf-8"))
            for bot_id, ts_str in raw.items():
                try:
                    dd_onset_cache[bot_id] = datetime.fromisoformat(ts_str)
                except Exception:
                    continue
            logger.info("exit_advisor.dd_onset_cache.loaded n=%d", len(dd_onset_cache))
    except Exception:
        logger.exception("exit_advisor.dd_onset_cache.load_failed")

    def _save_dd_cache() -> None:
        try:
            _DD_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            payload = {bot_id: ts.isoformat() for bot_id, ts in dd_onset_cache.items()}
            _DD_CACHE_PATH.write_text(_json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            logger.exception("exit_advisor.dd_onset_cache.save_failed")

    logger.info("exit_advisor_loop.started interval=%ds send_fn=%s", interval_sec, "wired" if send_fn else "missing")

    while not stop_event.is_set():
        try:
            _tick(
                ranker=ranker,
                margin_calc=margin_calc,
                tracker=tracker,
                send_fn=send_fn,
                dedup_cache=dedup_cache,
                last_severity_holder=[last_severity],
                dd_onset_cache=dd_onset_cache,
                regime_fn=regime_fn,
                session_fn=session_fn,
            )
            last_severity = _tick.last_severity if hasattr(_tick, "last_severity") else last_severity
            # Persist DD onset cache между рестартами
            _save_dd_cache()
        except Exception:
            logger.exception("exit_advisor_loop.tick_failed")

        try:
            await asyncio.wait_for(asyncio.shield(stop_event.wait()), timeout=interval_sec)
        except asyncio.TimeoutError:
            pass


def _tick(
    *,
    ranker: StrategyRanker,
    margin_calc: MarginCalculator,
    tracker: OutcomeTracker,
    send_fn: Any,
    dedup_cache: dict[str, datetime],
    last_severity_holder: list[int],
    dd_onset_cache: dict[str, datetime],
    regime_fn: Any,
    session_fn: Any,
) -> None:
    """Single synchronous tick of the exit advisor."""
    # 1. Build position state
    current_price = _get_current_price()
    state = build_position_state(current_price=current_price, dd_onset_cache=dd_onset_cache)

    # Track followup outcomes
    fired = tracker.tick(state)
    for outcome in fired:
        logger.info("exit_advisor.followup: %s", outcome)

    # Nothing to do if monitoring
    if not state.has_active_position:
        return
    if state.scenario_class == ScenarioClass.MONITORING:
        return

    # 2. Dedup check
    now = state.captured_at
    sc_key = state.scenario_class.value
    last_sent = dedup_cache.get(sc_key)
    current_severity = _SEVERITY_ORDER.get(state.scenario_class, 0)
    prev_severity = last_severity_holder[0]

    escalated = current_severity > prev_severity
    within_window = last_sent is not None and (now - last_sent) < timedelta(seconds=_DEDUP_WINDOW_SEC)

    if within_window and not escalated:
        logger.debug("exit_advisor.dedup_suppressed scenario=%s", sc_key)
        last_severity_holder[0] = current_severity
        return

    # 3. Get regime + session
    regime = regime_fn() if callable(regime_fn) else "unknown"
    session = session_fn() if callable(session_fn) else "NONE"

    # 4. Rank strategies
    strategies = ranker.rank(
        state,
        regime=regime,
        session=session,
        max_results=6,
        min_free_margin_usd=state.free_margin_usd,
    )

    if not strategies:
        last_severity_holder[0] = current_severity
        return

    # 5. Compute margins
    short_btc = abs(state.short_side.total_position_btc)
    margin_reqs = margin_calc.compute_all(
        strategies,
        current_price=state.current_price,
        free_margin_usd=state.free_margin_usd,
        total_balance_usd=state.total_balance_usd,
        short_position_btc=short_btc,
    )

    # 6. Format and send
    card = format_advisory_alert(state, strategies, margin_reqs)
    if card and send_fn is not None:
        try:
            if callable(send_fn):
                send_fn(card)
            dedup_cache[sc_key] = now
            logger.info(
                "exit_advisor.alert_sent scenario=%s severity=%d",
                sc_key, current_severity,
            )
        except Exception:
            logger.exception("exit_advisor.send_failed")

    last_severity_holder[0] = current_severity


def _get_current_price() -> float:
    """Get current BTC price from market state file."""
    try:
        import json
        state_path = _ROOT / "storage" / "market_state.json"
        if state_path.exists():
            data = json.loads(state_path.read_text(encoding="utf-8"))
            return float(data.get("price", 0.0) or 0.0)
    except Exception:
        pass
    return 0.0
