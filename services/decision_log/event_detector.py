from __future__ import annotations

import csv
import json
import os
from collections import OrderedDict
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast

from .models import (
    CapturedEvent,
    EventSeverity,
    EventType,
    MarketContext,
    PortfolioContext,
    compute_severity,
)
from .storage import EVENTS_PATH, LAST_SEEN_PATH, append_event, load_last_seen, save_last_seen

SNAPSHOTS_PATH = Path("ginarea_live/snapshots.csv")
PARAMS_PATH = Path("ginarea_live/params.csv")
ADVISE_SIGNALS_PATH = Path("state/advise_signals.jsonl")
STATE_LATEST_PATH = Path("docs/STATE/state_latest.json")
MARGIN_THRESHOLDS = (60.0, 30.0, 15.0)

# Event types that fire continuously and need between-iteration dedup
_DEDUP_EVENT_TYPES: frozenset[EventType] = frozenset({
    EventType.BOUNDARY_BREACH,
    EventType.PNL_EXTREME,
    EventType.PNL_EVENT,
})
_DEDUP_WINDOW_MINUTES = 5


def _read_csv_latest_by_bot(path: Path) -> dict[str, dict[str, str]]:
    """Robust CSV reader for the live params.csv. Handles NUL bytes that
    occasionally appear when a writer is killed mid-write (observed
    2026-05-11 errors.log: '_csv.Error: line contains NUL').

    Strips \\x00 bytes before parsing; logs once per call if any seen.
    """
    if not path.exists():
        return {}
    latest: dict[str, dict[str, str]] = {}
    try:
        raw = path.read_bytes()
    except OSError:
        return {}
    if not raw:
        return {}
    had_nul = b"\x00" in raw
    if had_nul:
        raw = raw.replace(b"\x00", b"")
    try:
        text = raw.decode("utf-8", errors="replace")
    except UnicodeDecodeError:
        return {}
    import io
    try:
        reader = csv.DictReader(io.StringIO(text))
        for row in reader:
            bot_id = str(row.get("bot_id", "")).strip()
            ts = str(row.get("ts_utc", ""))
            if not bot_id:
                continue
            prev = latest.get(bot_id)
            if prev is None or ts >= str(prev.get("ts_utc", "")):
                latest[bot_id] = dict(row)
    except csv.Error as exc:
        # Parser still unhappy after NUL-stripping — log and bail out cleanly.
        import logging
        logging.getLogger(__name__).warning(
            "params.csv parse failed (had_nul=%s): %s", had_nul, exc,
        )
        return latest
    return latest


def _to_float(value: Any) -> float:
    try:
        if value in ("", None):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_dt(value: str | None, *, default: datetime | None = None) -> datetime:
    if not value:
        return default or datetime.now(timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _load_latest_advise_market_context(path: Path = ADVISE_SIGNALS_PATH) -> tuple[MarketContext, float]:
    if not path.exists():
        return MarketContext(price_btc=0.0, regime_label="unknown"), 0.0
    last_good: dict[str, Any] | None = None
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                last_good = json.loads(line)
            except json.JSONDecodeError:
                continue
    if last_good is None:
        return MarketContext(price_btc=0.0, regime_label="unknown"), 0.0
    market = dict(last_good.get("market_context", {}) or {})
    exposure = dict(last_good.get("current_exposure", {}) or {})
    above = market.get("nearest_liq_above")
    below = market.get("nearest_liq_below")
    session = dict(market.get("session", {}) or {})
    ctx = MarketContext(
        price_btc=_to_float(market.get("price_btc")),
        regime_label=str(market.get("regime_label", "unknown")),
        regime_modifiers=list(market.get("regime_modifiers", []) or []),
        rsi_1h=market.get("rsi_1h"),
        rsi_5m=market.get("rsi_5m"),
        price_change_5m_pct=_to_float(market.get("price_change_5m_30bars_pct")),
        price_change_1h_pct=_to_float(market.get("price_change_1h_pct")),
        atr_normalized=market.get("atr_normalized"),
        session_kz=str(session.get("kz_active", "NONE")),
        nearest_liq_above=_to_float(above.get("price")) if isinstance(above, dict) else None,
        nearest_liq_below=_to_float(below.get("price")) if isinstance(below, dict) else None,
    )
    return ctx, _to_float(exposure.get("free_margin_pct"))


def _load_state_latest(path: Path = STATE_LATEST_PATH) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return {}


def build_portfolio_context(
    snapshots: dict[str, dict[str, str]],
    *,
    free_margin_pct: float | None = None,
    depo_total: float | None = None,
    drawdown_pct: float | None = None,
) -> PortfolioContext:
    state_latest = _load_state_latest()
    portfolio = dict(state_latest.get("portfolio", {}) or {})
    depo_total_value = depo_total if depo_total is not None else _to_float(portfolio.get("depo_total")) or _to_float(os.getenv("ADVISOR_DEPO_TOTAL"))
    drawdown_value = drawdown_pct if drawdown_pct is not None else _to_float(portfolio.get("dd_pct"))
    free_margin_value = free_margin_pct if free_margin_pct is not None else _to_float(portfolio.get("free_margin_pct"))
    shorts_unrealized = 0.0
    longs_unrealized = 0.0
    shorts_btc = 0.0
    longs_usd = 0.0
    for row in snapshots.values():
        position = _to_float(row.get("position"))
        current_profit = _to_float(row.get("current_profit"))
        if position < 0:
            shorts_unrealized += current_profit
            shorts_btc += abs(position)
        elif position > 0:
            longs_unrealized += current_profit
            longs_usd += abs(position) * _to_float(row.get("average_price"))
    return PortfolioContext(
        depo_total=depo_total_value,
        shorts_unrealized_usd=shorts_unrealized,
        longs_unrealized_usd=longs_unrealized,
        net_unrealized_usd=shorts_unrealized + longs_unrealized,
        free_margin_pct=free_margin_value,
        drawdown_pct=drawdown_value,
        shorts_position_btc=shorts_btc,
        longs_position_usd=longs_usd,
    )


def _event_id(now: datetime, counter: int) -> str:
    return f"evt-{now.strftime('%Y%m%d')}-{counter:04d}"


def _next_counter(state: dict[str, Any], now: datetime) -> int:
    current_date = state.get("counter_date")
    today = now.strftime("%Y%m%d")
    if current_date != today:
        state["counter_date"] = today
        state["event_counter"] = 0
    state["event_counter"] = int(state.get("event_counter", 0)) + 1
    return int(state["event_counter"])


def _build_event(
    state: dict[str, Any],
    *,
    now: datetime,
    event_type: EventType,
    severity: EventSeverity,
    bot_id: str | None,
    summary: str,
    payload: dict[str, Any],
    market_context: MarketContext,
    portfolio_context: PortfolioContext,
) -> CapturedEvent:
    counter = _next_counter(state, now)
    return CapturedEvent(
        event_id=_event_id(now, counter),
        ts=now,
        event_type=event_type,
        severity=severity,
        bot_id=bot_id,
        summary=summary,
        payload=payload,
        market_context=replace(market_context),
        portfolio_context=replace(portfolio_context),
    )


def _aggregate_same_type_events(events: list[CapturedEvent]) -> list[CapturedEvent]:
    """Merge same (event_type, severity) groups from one iteration into a single event."""
    groups: OrderedDict[tuple[EventType, EventSeverity], list[CapturedEvent]] = OrderedDict()
    for event in events:
        key = (event.event_type, event.severity)
        if key not in groups:
            groups[key] = []
        groups[key].append(event)
    result: list[CapturedEvent] = []
    for group in groups.values():
        if len(group) == 1:
            result.append(group[0])
        else:
            bot_ids = [e.bot_id for e in group if e.bot_id]
            merged_payload = dict(group[0].payload)
            merged_payload["affected_bots"] = bot_ids
            result.append(
                replace(
                    group[0],
                    bot_id="multiple",
                    summary=f"{group[0].event_type}: {len(group)} ботов одновременно",
                    payload=merged_payload,
                )
            )
    return result


def _apply_dedup(
    events: list[CapturedEvent],
    state: dict[str, Any],
    now: datetime,
) -> list[CapturedEvent]:
    """Suppress continuous-detector events already fired within the dedup window."""
    window_start = now - timedelta(minutes=10)
    recent: list[dict[str, Any]] = [
        e for e in (state.get("recent_events") or [])
        if _to_dt(e.get("ts")) >= window_start
    ]
    cutoff = now - timedelta(minutes=_DEDUP_WINDOW_MINUTES)
    result: list[CapturedEvent] = []
    for event in events:
        if event.event_type not in _DEDUP_EVENT_TYPES:
            result.append(event)
            continue
        already_fired = any(
            e.get("event_type") == event.event_type and e.get("severity") == event.severity
            for e in recent
            if _to_dt(e.get("ts")) >= cutoff
        )
        if not already_fired:
            result.append(event)
    for event in result:
        if event.event_type in _DEDUP_EVENT_TYPES:
            recent.append({
                "ts": now.isoformat(),
                "event_type": event.event_type,
                "severity": event.severity,
                "bot_id": event.bot_id,
            })
    state["recent_events"] = recent[-100:]
    return result


def detect_events(
    current_snapshots: dict[str, dict[str, str]],
    current_params: dict[str, dict[str, str]],
    last_seen_state: dict[str, Any],
    *,
    now: datetime,
    market_context: MarketContext,
    portfolio_context: PortfolioContext,
) -> tuple[list[CapturedEvent], dict[str, Any]]:
    state = deepcopy(last_seen_state)

    # Cold start: empty state → save baseline, emit nothing this iteration
    if not state:
        state["initialized"] = True
        state["snapshots"] = current_snapshots
        state["params"] = current_params
        state["portfolio_history"] = []
        state["free_margin_pct"] = portfolio_context.free_margin_pct
        state["regime_label"] = market_context.regime_label
        state["recent_events"] = []
        return [], state

    state["initialized"] = True
    events: list[CapturedEvent] = []
    prev_snapshots = dict(state.get("snapshots", {}) or {})
    prev_params = dict(state.get("params", {}) or {})

    for bot_id, current in current_params.items():
        prev = dict(prev_params.get(bot_id, {}) or {})
        changed: list[dict[str, Any]] = []
        for field in ("grid_step", "target", "instop", "border_top", "border_bottom", "raw_params_json"):
            old_val = prev.get(field)
            new_val = current.get(field)
            if old_val != new_val:
                changed.append({"field": field, "old": old_val, "new": new_val})
        if changed:
            readable = ", ".join(item["field"] for item in changed if item["field"] != "raw_params_json") or "raw_params_json"
            payload: dict[str, Any] = {"changes": changed}
            events.append(
                _build_event(
                    state,
                    now=now,
                    event_type=EventType.PARAM_CHANGE,
                    severity=compute_severity(EventType.PARAM_CHANGE, payload, market_context, portfolio_context),
                    bot_id=bot_id,
                    summary=f"Изменение параметров бота {current.get('alias') or bot_id}: {readable}",
                    payload=payload,
                    market_context=market_context,
                    portfolio_context=portfolio_context,
                )
            )

    for bot_id, current in current_snapshots.items():
        prev = dict(prev_snapshots.get(bot_id, {}) or {})
        if prev and prev.get("status") != current.get("status"):
            payload = {"old_status": prev.get("status"), "new_status": current.get("status")}
            events.append(
                _build_event(
                    state,
                    now=now,
                    event_type=EventType.BOT_STATE_CHANGE,
                    severity=compute_severity(EventType.BOT_STATE_CHANGE, payload, market_context, portfolio_context),
                    bot_id=bot_id,
                    summary=f"Смена статуса бота {current.get('alias') or bot_id}: {prev.get('status')} → {current.get('status')}",
                    payload=payload,
                    market_context=market_context,
                    portfolio_context=portfolio_context,
                )
            )

        if prev:
            prev_position = abs(_to_float(prev.get("position")))
            current_position = abs(_to_float(current.get("position")))
            base = prev_position if prev_position > 0 else 1.0
            delta_ratio = abs(current_position - prev_position) / base
            if delta_ratio > 0.05:
                payload = {"old_position": prev_position, "new_position": current_position, "delta_ratio": delta_ratio}
                events.append(
                    _build_event(
                        state,
                        now=now,
                        event_type=EventType.POSITION_CHANGE,
                        severity=compute_severity(EventType.POSITION_CHANGE, payload, market_context, portfolio_context),
                        bot_id=bot_id,
                        summary=f"Изменение позиции бота {current.get('alias') or bot_id}: {prev_position:.4f} → {current_position:.4f}",
                        payload=payload,
                        market_context=market_context,
                        portfolio_context=portfolio_context,
                    )
                )

        current_price = market_context.price_btc
        params_row = current_params.get(bot_id, {})
        border_top = _to_float(params_row.get("border_top"))
        border_bottom = _to_float(params_row.get("border_bottom"))
        if border_top > 0 and current_price > border_top:
            payload = {"price": current_price, "border_top": border_top}
            events.append(
                _build_event(
                    state,
                    now=now,
                    event_type=EventType.BOUNDARY_BREACH,
                    severity=compute_severity(EventType.BOUNDARY_BREACH, payload, market_context, portfolio_context),
                    bot_id=bot_id,
                    summary=f"Цена вышла выше верхней границы бота {current.get('alias') or bot_id}",
                    payload=payload,
                    market_context=market_context,
                    portfolio_context=portfolio_context,
                )
            )
        elif border_bottom > 0 and 0 < current_price < border_bottom:
            payload = {"price": current_price, "border_bottom": border_bottom}
            events.append(
                _build_event(
                    state,
                    now=now,
                    event_type=EventType.BOUNDARY_BREACH,
                    severity=compute_severity(EventType.BOUNDARY_BREACH, payload, market_context, portfolio_context),
                    bot_id=bot_id,
                    summary=f"Цена вышла ниже нижней границы бота {current.get('alias') or bot_id}",
                    payload=payload,
                    market_context=market_context,
                    portfolio_context=portfolio_context,
                )
            )

    history = list(state.get("portfolio_history", []) or [])
    history.append({"ts": now.isoformat(), "net_unrealized_usd": portfolio_context.net_unrealized_usd})
    history = [item for item in history if _to_dt(item.get("ts"), default=now) >= now - timedelta(hours=24)]
    compare_15m = next(
        (
            item for item in history
            if _to_dt(item.get("ts"), default=now) <= now - timedelta(minutes=15)
        ),
        None,
    )
    if compare_15m is not None:
        delta = portfolio_context.net_unrealized_usd - _to_float(compare_15m.get("net_unrealized_usd"))
        if abs(delta) > 200.0:
            payload = {"delta_pnl_usd": delta}
            events.append(
                _build_event(
                    state,
                    now=now,
                    event_type=EventType.PNL_EVENT,
                    severity=compute_severity(EventType.PNL_EVENT, payload, market_context, portfolio_context),
                    bot_id=None,
                    summary=f"Сильное изменение нереализованного PnL за 15 минут: {delta:+.0f} USD",
                    payload=payload,
                    market_context=market_context,
                    portfolio_context=portfolio_context,
                )
            )

    if history:
        values = [_to_float(item.get("net_unrealized_usd")) for item in history]
        current_value = portfolio_context.net_unrealized_usd
        if current_value <= min(values[:-1] or values):
            payload = {"extreme": "low", "value": current_value}
            events.append(
                _build_event(
                    state,
                    now=now,
                    event_type=EventType.PNL_EXTREME,
                    severity=compute_severity(EventType.PNL_EXTREME, payload, market_context, portfolio_context),
                    bot_id=None,
                    summary=f"Новый минимум PnL за 24ч: {current_value:.0f} USD",
                    payload=payload,
                    market_context=market_context,
                    portfolio_context=portfolio_context,
                )
            )
        elif current_value >= max(values[:-1] or values):
            payload = {"extreme": "high", "value": current_value}
            events.append(
                _build_event(
                    state,
                    now=now,
                    event_type=EventType.PNL_EXTREME,
                    severity=compute_severity(EventType.PNL_EXTREME, payload, market_context, portfolio_context),
                    bot_id=None,
                    summary=f"Новый максимум PnL за 24ч: {current_value:.0f} USD",
                    payload=payload,
                    market_context=market_context,
                    portfolio_context=portfolio_context,
                )
            )

    prev_margin = state.get("free_margin_pct")
    current_margin = portfolio_context.free_margin_pct
    if isinstance(prev_margin, (int, float)):
        for threshold in MARGIN_THRESHOLDS:
            if prev_margin > threshold >= current_margin:
                payload = {"threshold": threshold, "old_margin_pct": prev_margin, "new_margin_pct": current_margin}
                events.append(
                    _build_event(
                        state,
                        now=now,
                        event_type=EventType.MARGIN_ALERT,
                        severity=compute_severity(EventType.MARGIN_ALERT, payload, market_context, portfolio_context),
                        bot_id=None,
                        summary=f"Свободная маржа упала ниже {threshold:.0f}%: сейчас {current_margin:.1f}%",
                        payload=payload,
                        market_context=market_context,
                        portfolio_context=portfolio_context,
                    )
                )
        if prev_margin < 40.0 <= current_margin:
            payload = {"old_margin_pct": prev_margin, "new_margin_pct": current_margin}
            events.append(
                _build_event(
                    state,
                    now=now,
                    event_type=EventType.MARGIN_RECOVERY,
                    severity=compute_severity(EventType.MARGIN_RECOVERY, payload, market_context, portfolio_context),
                    bot_id=None,
                    summary=f"Свободная маржа восстановилась выше 40%: сейчас {current_margin:.1f}%",
                    payload=payload,
                    market_context=market_context,
                    portfolio_context=portfolio_context,
                )
            )

    prev_regime = state.get("regime_label")
    if prev_regime and prev_regime != market_context.regime_label:
        payload = {"old_regime": prev_regime, "new_regime": market_context.regime_label}
        events.append(
            _build_event(
                state,
                now=now,
                event_type=EventType.REGIME_CHANGE,
                severity=compute_severity(EventType.REGIME_CHANGE, payload, market_context, portfolio_context),
                bot_id=None,
                summary=f"Смена рыночного режима: {prev_regime} → {market_context.regime_label}",
                payload=payload,
                market_context=market_context,
                portfolio_context=portfolio_context,
            )
        )

    # Within-iteration: merge same (event_type, severity) groups from multiple bots
    events = _aggregate_same_type_events(events)

    # Between-iteration: suppress continuous events that already fired within dedup window
    events = _apply_dedup(events, state, now)

    state["snapshots"] = current_snapshots
    state["params"] = current_params
    state["portfolio_history"] = history
    state["free_margin_pct"] = current_margin
    state["regime_label"] = market_context.regime_label
    return events, state


def detector_run_once(
    *,
    snapshots_path: Path = SNAPSHOTS_PATH,
    params_path: Path = PARAMS_PATH,
    events_path: Path = EVENTS_PATH,
    last_seen_path: Path = LAST_SEEN_PATH,
    now: datetime | None = None,
    notifier: Any | None = None,
) -> list[CapturedEvent]:
    current_now = now or datetime.now(timezone.utc)
    current_snapshots = _read_csv_latest_by_bot(snapshots_path)
    current_params = _read_csv_latest_by_bot(params_path)
    market_context, free_margin_pct = _load_latest_advise_market_context()
    portfolio_context = build_portfolio_context(current_snapshots, free_margin_pct=free_margin_pct)
    last_seen = load_last_seen(last_seen_path)
    events, new_state = detect_events(
        current_snapshots,
        current_params,
        last_seen,
        now=current_now,
        market_context=market_context,
        portfolio_context=portfolio_context,
    )
    for event in events:
        append_event(event, events_path)
        if notifier is not None and event.severity in (EventSeverity.WARNING, EventSeverity.CRITICAL):
            notifier(event)
    save_last_seen(new_state, last_seen_path)
    return events
