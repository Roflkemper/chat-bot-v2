from __future__ import annotations

import csv
import json
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

SNAPSHOTS_PATH = Path("ginarea_live/snapshots.csv")
STATE_LATEST_PATH = Path("docs/STATE/state_latest.json")
ADVISE_SIGNALS_PATH = Path("state/advise_signals.jsonl")
NULL_SIGNALS_PATH = Path("state/advise_null_signals.jsonl")
EVENTS_PATH = Path("state/decision_log/events.jsonl")
LIQ_CLUSTERS_PATH = Path("state/liq_clusters/active.json")
COMPETITION_PATH = Path("state/competition_state.json")
ENGINE_STATUS_PATH = Path("state/engine_status.json")
REGIME_STATE_PATH = Path("data/regime/switcher_state.json")
# Live Classifier A output (per CLASSIFIER_AUTHORITY_v1 §1). Read via
# services/dashboard/regime_adapter.adapt_regime_state(). The legacy
# REGIME_STATE_PATH above (switcher_state.json) is no longer the source
# of truth — it was written by the deprecated dashboard_bootstrap_state.py
# scaffold against frozen forecast-pipeline parquets.
CLASSIFIER_A_STATE_PATH = Path("state/regime_state.json")
VIRTUAL_TRADER_LOG_PATH = Path("data/virtual_trader/positions_log.jsonl")
OUTPUT_PATH = Path("docs/STATE/dashboard_state.json")

# ── Forecast block decommissioned (TZ-FORECAST-DECOMMISSION, 2026-05-05) ──
# Per FORECAST_CALIBRATION_DIAGNOSTIC_v1.md verdict: FUNDAMENTALLY WEAK.
# Replayed full-year Brier = 0.2569 (worse than 0.25 baseline). Murphy
# decomposition: resolution = 0.0001 across all horizons. Calibration
# (Platt + isotonic) recovers exactly the 0.2500 no-skill baseline but
# cannot manufacture missing resolution. MARKUP and MARKDOWN regimes show
# sign inversion. Forecast is removed from the dashboard, state, and tests.
#
# What remains here intentionally:
#   - regime classifier output (independent, still used by regulation card)
#   - regulation_action_card (REGULATION v0.1.1 §3 mirror)
#
# Historical reference (commented for the future model, if any):
#   _CV_BRIER = {"MARKUP": {...}, "MARKDOWN": {...}, "RANGE": {...}}
#   _DELIVERY_MATRIX = {...}
#   FORECAST_STALE_THRESHOLD_HOURS = 2.0
#   FORECAST_USABILITY_ACTIONABLE_BRIER = 0.22
#   FORECAST_USABILITY_ACTIONABLE_PROB_LO = 0.40
#   FORECAST_USABILITY_ACTIONABLE_PROB_HI = 0.60
#   FORECAST_USABILITY_WEAK_BRIER = 0.265
#   FORECAST_USABILITY_WEAK_PROB_LO = 0.45
#   FORECAST_USABILITY_WEAK_PROB_HI = 0.55

PHASE_1_TOTAL_DAYS = 14

# Regulation v0.1.1 §3 activation matrix (REGULATION_v0_1_1.md §3). Frozen mapping
# from {regime_label} → {config_id} → {ON / CONDITIONAL / OFF, reason}.
# This is a rendering-layer mirror of the regulation. If the regulation is
# revised, update this constant in lockstep with the doc.
_REGULATION_ACTIVATION_V0_1_1: dict[str, dict[str, dict[str, str]]] = {
    "RANGE": {
        "CFG-L-RANGE":         {"status": "ON",          "reason": "REG §3: ON in RANGE (Pack E + E-NoStop both 4/4 profitable)."},
        "CFG-L-FAR":           {"status": "ON",          "reason": "REG §3: ON in RANGE (Pack BT 4/4 profitable)."},
        "CFG-S-RANGE-DEFAULT": {"status": "ON",          "reason": "REG §3: ON in RANGE (Pack A 1y +12 181 USD; RANGE dominates year)."},
        "CFG-S-INDICATOR":     {"status": "OFF",         "reason": "REG §2: SUSPENDED (Pack A2/A4 + Pack D 4/4 losing)."},
        "CFG-L-DEFAULT":       {"status": "OFF",         "reason": "REG §2: SUSPENDED (Pack C 3/3 losing)."},
    },
    "MARKUP": {
        "CFG-L-RANGE":         {"status": "ON",          "reason": "REG §3: ON in MARKUP (Pack E pack-level positive across mixed regimes)."},
        "CFG-L-FAR":           {"status": "ON",          "reason": "REG §3: ON in MARKUP (Pack BT pack-level positive across mixed regimes)."},
        "CFG-S-RANGE-DEFAULT": {"status": "CONDITIONAL", "reason": "REG §3: CONDITIONAL — within-pack regime sensitivity not validated; deploy with bounded loss limits."},
        "CFG-S-INDICATOR":     {"status": "OFF",         "reason": "REG §2: SUSPENDED."},
        "CFG-L-DEFAULT":       {"status": "OFF",         "reason": "REG §2: SUSPENDED."},
    },
    "MARKDOWN": {
        "CFG-L-RANGE":         {"status": "CONDITIONAL", "reason": "REG §3: CONDITIONAL — bullish-year dataset over-weights MARKUP-favorable; pause if MARKDOWN-share live PnL deviates negatively."},
        "CFG-L-FAR":           {"status": "CONDITIONAL", "reason": "REG §3: CONDITIONAL — same as CFG-L-RANGE."},
        "CFG-S-RANGE-DEFAULT": {"status": "CONDITIONAL", "reason": "REG §3: CONDITIONAL — Pack A trend-regime performance not specifically validated."},
        "CFG-S-INDICATOR":     {"status": "OFF",         "reason": "REG §2: SUSPENDED. (Monitoring-only hypothesis flag exists but not deployable.)"},
        "CFG-L-DEFAULT":       {"status": "OFF",         "reason": "REG §2: SUSPENDED."},
    },
    "DISTRIBUTION": {
        # Per REG §1.3 + REGIME_PERIODS_2025_2026 §1: classifier emits 3 labels,
        # DISTRIBUTION absent. If a fourth-regime ever appears, NO RULE applies.
        "CFG-L-RANGE":         {"status": "NO_RULE",     "reason": "REG §3.3: classifier does not emit DISTRIBUTION; out of regulation scope."},
        "CFG-L-FAR":           {"status": "NO_RULE",     "reason": "REG §3.3."},
        "CFG-S-RANGE-DEFAULT": {"status": "NO_RULE",     "reason": "REG §3.3."},
        "CFG-S-INDICATOR":     {"status": "OFF",         "reason": "REG §2: SUSPENDED."},
        "CFG-L-DEFAULT":       {"status": "OFF",         "reason": "REG §2: SUSPENDED."},
    },
}

_BOLI_DEFAULT: list[dict[str, Any]] = [
    {"id": 1, "name": "Стресс-мониторинг", "status": "manual"},
    {"id": 2, "name": "Detection ложных выносов", "status": "manual"},
    {"id": 3, "name": "Manual sizing rebalance", "status": "manual"},
    {"id": 4, "name": "Drift к катастрофе", "status": "in_progress"},
]


def _to_float(v: Any) -> float:
    try:
        return float(v) if v not in (None, "", "None") else 0.0
    except (TypeError, ValueError):
        return 0.0


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, ValueError):
        return {}


def _read_jsonl(path: Path, *, limit: int | None = None) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return rows[-limit:] if limit is not None else rows


def _normalize_bot_id(raw: str) -> str:
    """Canonicalize bot_id by stripping legacy '.0' float suffix.

    GinArea tracker historically wrote bot IDs as floats ('5196832375.0');
    a later fix switched to integer strings ('5196832375'). The CSV thus
    contains both formats for the same bot. Without normalization the dashboard
    counted such bots twice (TZ-DASHBOARD-POSITION-DEDUP, 2026-05-05).
    """
    s = str(raw or "").strip()
    if s.endswith(".0") and s[:-2].isdigit():
        return s[:-2]
    return s


def _read_csv_latest_by_bot(path: Path) -> list[dict[str, str]]:
    """Return latest snapshot per unique bot_id (canonical form).

    Dedups across legacy '.0' suffix variations: '5196832375' and
    '5196832375.0' map to one canonical key, latest ts_utc wins.
    """
    if not path.exists():
        return []
    latest: dict[str, dict[str, str]] = {}
    try:
        with path.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                bot_id = _normalize_bot_id(row.get("bot_id", ""))
                ts = str(row.get("ts_utc", ""))
                if not bot_id:
                    continue
                prev = latest.get(bot_id)
                if prev is None or ts >= str(prev.get("ts_utc", "")):
                    latest[bot_id] = dict(row)
    except (OSError, csv.Error):
        pass
    return list(latest.values())


def _build_positions(
    snapshots: list[dict[str, str]],
    net_btc: float | None,
    free_margin_pct: float | None,
    drawdown_pct: float,
) -> dict[str, Any]:
    longs: list[dict[str, Any]] = []
    shorts: list[dict[str, Any]] = []
    for row in snapshots:
        pos = _to_float(row.get("position"))
        profit = _to_float(row.get("current_profit"))
        alias = str(row.get("alias") or row.get("bot_id") or "")
        if pos > 0:
            longs.append({"alias": alias, "size_usd": round(pos, 0), "unrealized": round(profit, 2)})
        elif pos < 0:
            shorts.append({"alias": alias, "size_btc": round(pos, 4), "unrealized": round(profit, 2)})
    return {
        "longs": {
            "total_usd": round(sum(b["size_usd"] for b in longs), 0),
            "unrealized_usd": round(sum(b["unrealized"] for b in longs), 2),
            "active_bots": longs,
        },
        "shorts": {
            "total_btc": round(sum(b["size_btc"] for b in shorts), 4),
            "unrealized_usd": round(sum(b["unrealized"] for b in shorts), 2),
            "active_bots": shorts,
        },
        "net_btc": net_btc,
        "free_margin_pct": free_margin_pct,
        "drawdown_pct": drawdown_pct,
    }


def _build_phase1(
    signals: list[dict[str, Any]],
    null_signals: list[dict[str, Any]],
    now: datetime,
) -> dict[str, Any]:
    if not signals:
        return {
            "day_n": 0,
            "day_total": PHASE_1_TOTAL_DAYS,
            "advise_signals_count": 0,
            "null_signals_count": len(null_signals),
            "dominant_setup": None,
            "regime_distribution": {},
        }
    first_ts_str = str(signals[0].get("ts", ""))
    day_n = 1
    try:
        first_ts = datetime.fromisoformat(first_ts_str.replace("Z", "+00:00"))
        day_n = max(1, (now - first_ts).days + 1)
    except (ValueError, AttributeError):
        pass
    setup_counter: Counter[str] = Counter(
        str(s["setup_id"])
        for s in signals
        if s.get("setup_id")
    )
    dominant_setup: str | None = setup_counter.most_common(1)[0][0] if setup_counter else None
    regime_list = [
        str(s.get("market_context", {}).get("regime_label", ""))
        for s in signals
        if s.get("market_context", {}).get("regime_label")
    ]
    total = len(regime_list)
    regime_dist: dict[str, float] = (
        {k: round(v / total, 2) for k, v in Counter(regime_list).items()}
        if total
        else {}
    )
    return {
        "day_n": day_n,
        "day_total": PHASE_1_TOTAL_DAYS,
        "advise_signals_count": len(signals),
        "null_signals_count": len(null_signals),
        "dominant_setup": dominant_setup,
        "regime_distribution": regime_dist,
    }


def _build_recent_decisions(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "event_id": str(e.get("event_id", "")),
            "type": str(e.get("event_type", "")),
            "ts": str(e.get("ts", "")),
            "outcome": "pending",
        }
        for e in reversed(events[-5:])
    ]


def _build_alerts_24h(events: list[dict[str, Any]], now: datetime) -> list[dict[str, Any]]:
    cutoff = now - timedelta(hours=24)
    result: list[dict[str, Any]] = []
    for e in events:
        ts_str = str(e.get("ts", ""))
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            continue
        if ts < cutoff:
            continue
        if e.get("severity") not in ("WARNING", "CRITICAL"):
            continue
        result.append({"ts": ts_str, "msg": str(e.get("summary", ""))})
    return result[-10:]


def _build_engine_status(engine_cfg: dict[str, Any]) -> dict[str, Any]:
    return {
        "calibration_done_at": str(engine_cfg.get("calibration_done_at") or "2026-04-30T10:36:00Z"),
        "bugs_detected": int(engine_cfg.get("bugs_detected") or 3),
        "bugs_fixed": int(engine_cfg.get("bugs_fixed") or 0),
        "fix_eta": str(engine_cfg.get("fix_eta") or "pending TZ-ENGINE-BUG-FIX"),
    }


def _build_competition(comp_cfg: dict[str, Any]) -> dict[str, Any]:
    return {
        "rank": comp_cfg.get("rank"),
        "pnl_total_usd": comp_cfg.get("pnl_total_usd"),
        "volume_total_usd": comp_cfg.get("volume_total_usd"),
        "volume_target_usd": comp_cfg.get("volume_target_usd"),
        "days_remaining": comp_cfg.get("days_remaining"),
        "daily_volume_avg": comp_cfg.get("daily_volume_avg"),
        "projected_volume_30d": comp_cfg.get("projected_volume_30d"),
        "rebate_estimate": comp_cfg.get("rebate_estimate"),
    }


# Forecast helpers removed (TZ-FORECAST-DECOMMISSION). Were:
#   _brier_band(brier) -> green|yellow|red|qualitative
#   _forecast_usability_band(prob_up, brier, mode) -> (band, reasoning)
#   _forecast_staleness(bar_time, now) -> staleness dict
# See FORECAST_CALIBRATION_DIAGNOSTIC_v1.md for the verdict that retired them.


def _file_age_minutes(path: Path, now: datetime) -> float | None:
    """Return age of file mtime in minutes, or None if file missing."""
    if not path.exists():
        return None
    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return None
    return round((now - mtime).total_seconds() / 60.0, 1)


def _build_freshness(
    *,
    now: datetime,
    snapshots_path: Path,
    regime_state_path: Path,
) -> dict[str, Any]:
    """Per-source freshness ages + warning level.

    Warning levels:
      "ok"     — all sources < 10 min old
      "yellow" — at least one source 10-120 min old (positions stale)
      "red"    — at least one source > 120 min old (likely the live tracker is down)

    Forecast-staleness tracking removed in TZ-FORECAST-DECOMMISSION; the
    forecast block no longer exists, so its freshness is no longer meaningful.
    """
    ages = {
        "snapshots_min": _file_age_minutes(snapshots_path, now),
        "regime_state_min": _file_age_minutes(regime_state_path, now),
    }
    level = "ok"
    notes: list[str] = []
    pos_age = ages["snapshots_min"]
    if pos_age is None:
        level = "red"
        notes.append("snapshots.csv missing — tracker not running")
    elif pos_age > 120:
        level = "red"
        notes.append(f"snapshots stale ({pos_age:.0f} min) — tracker may be down")
    elif pos_age > 10:
        level = max(level, "yellow", key=["ok", "yellow", "red"].index)
        notes.append(f"snapshots {pos_age:.0f} min old")

    return {
        "level": level,
        "ages_min": ages,
        "notes": notes,
        "data_source": "ginarea_live/snapshots.csv (accepted as v1 live source — see services/dashboard/README.md §Data flow)",
    }


def _build_regime(regime_state: dict[str, Any]) -> dict[str, Any]:
    """Render current regime block: label, confidence, stability, hysteresis."""
    if not regime_state:
        return {
            "label": None,
            "confidence": None,
            "stability": None,
            "stable_bars": None,
            "switch_pending": False,
            "candidate_regime": None,
            "last_updated": None,
            "note": "no live regime state — start app_runner with switcher persistence enabled",
        }
    return {
        "label": regime_state.get("regime"),
        "confidence": regime_state.get("regime_confidence"),
        "stability": regime_state.get("regime_stability"),
        "stable_bars": regime_state.get("bars_in_current_regime"),
        "switch_pending": bool(regime_state.get("candidate_regime")),
        "candidate_regime": regime_state.get("candidate_regime"),
        "candidate_bars": regime_state.get("candidate_bars", 0),
        "last_updated": regime_state.get("updated_at"),
    }


# _build_forecast removed (TZ-FORECAST-DECOMMISSION).
# Forecast block was retired per FORECAST_CALIBRATION_DIAGNOSTIC_v1 verdict
# (FUNDAMENTALLY WEAK; resolution = 0.0001 across horizons; calibrated Brier
# recovers no-skill 0.2500 baseline only). The dashboard no longer renders
# numeric forecast probabilities. Regime classifier output remains and feeds
# the regulation action card below.


def _build_regulation_card(regime_label: str | None) -> dict[str, Any]:
    """Render the operator-facing regulation action card.

    P1 of TZ-DASHBOARD-USABILITY-FIX-PHASE-1. For the current regime label,
    show which configurations from REGULATION_v0_1_1 §3 are ON / CONDITIONAL /
    OFF, with one-line reasoning per row. The mapping is frozen in
    _REGULATION_ACTIVATION_V0_1_1 above; the card is a pure render of that
    table for the current regime.

    Returns shape:
      {
        regime_label, regulation_version,
        on:          [{cfg_id, reason}, ...],
        conditional: [{cfg_id, reason}, ...],
        off:         [{cfg_id, reason}, ...],
        no_rule:     [{cfg_id, reason}, ...],
        note,
      }
    """
    out: dict[str, Any] = {
        "regulation_version": "v0.1.1",
        "regime_label": regime_label,
        "on": [],
        "conditional": [],
        "off": [],
        "no_rule": [],
        "note": None,
    }
    if not regime_label:
        out["note"] = "no regime label — activation rules cannot be applied"
        return out
    table = _REGULATION_ACTIVATION_V0_1_1.get(regime_label)
    if table is None:
        out["note"] = (
            f"regime '{regime_label}' not in REGULATION v0.1.1 §3 activation matrix; "
            "either classifier emitted an unexpected label or regulation needs revision"
        )
        return out
    for cfg_id, entry in table.items():
        status = entry["status"]
        row = {"cfg_id": cfg_id, "reason": entry["reason"]}
        if status == "ON":
            out["on"].append(row)
        elif status == "CONDITIONAL":
            out["conditional"].append(row)
        elif status == "OFF":
            out["off"].append(row)
        elif status == "NO_RULE":
            out["no_rule"].append(row)
    return out


def _build_decision_layer_block(
    *,
    now: datetime,
    draft: dict[str, Any],
    state_latest: dict[str, Any],
    regime_state: dict[str, Any],
    engine_cfg: dict[str, Any],
    freshness: dict[str, Any],
) -> dict[str, Any]:
    """Wire Decision Layer (TZ-DECISION-LAYER-CORE-WIRE).

    Reads draft state + auxiliary inputs, runs the rule engine, returns the
    augmentation block for dashboard_state.json["decision_layer"].

    Margin block (TZ-MARGIN-COEFFICIENT-INPUT-WIRE 2026-05-06):
      state_latest.json["margin"] is populated by state_snapshot.py from
      services.margin.read_latest_margin() — newer of operator-supplied
      override file (state/manual_overrides/margin_overrides.jsonl) and
      a future automated feed. When the margin block is absent, M-* rules
      short-circuit to no-event (M-* dormant; D-4 surfaces this).
    """
    from services.decision_layer import DecisionInputs, evaluate as decision_evaluate

    exposure = dict(state_latest.get("exposure") or {})
    nearest_short = dict(exposure.get("nearest_short_liq") or {})
    nearest_long = dict(exposure.get("nearest_long_liq") or {})
    margin_block = state_latest.get("margin") or {}

    # Margin coefficient — operator-supplied (or future automated) via
    # services.margin source resolution. None when no record exists.
    raw_coef = margin_block.get("coefficient")
    margin_coefficient = float(raw_coef) if raw_coef is not None else None

    # Distance to liquidation: prefer margin block (operator UI value, accurate
    # mark-price-based); fall back to per-bot exposure liq prices (which are
    # entry-price-based approximations and currently always have distance_pct=None).
    raw_dist = margin_block.get("distance_to_liquidation_pct")
    if raw_dist is not None:
        distance_to_liq_pct: float | None = float(raw_dist)
    else:
        dist_short = nearest_short.get("distance_pct")
        dist_long = nearest_long.get("distance_pct")
        candidates = [d for d in (dist_short, dist_long) if d is not None]
        distance_to_liq_pct = float(min(candidates)) if candidates else None

    # Margin data age — feeds D-4 (margin_data_stale).
    margin_data_age_min = margin_block.get("data_age_minutes") if margin_block else None
    if margin_data_age_min is not None:
        try:
            margin_data_age_min = float(margin_data_age_min)
        except (TypeError, ValueError):
            margin_data_age_min = None

    # Position state
    net_btc_raw = exposure.get("net_btc")
    position_btc = float(net_btc_raw) if net_btc_raw is not None else None

    # Unrealized PnL: sum bots[].live.unrealized_usd
    unreal_total: float = 0.0
    have_any = False
    for b in state_latest.get("bots", []) or []:
        live = b.get("live") or {}
        u = live.get("unrealized_usd")
        if u is not None:
            try:
                unreal_total += float(u)
                have_any = True
            except (TypeError, ValueError):
                pass
    unrealized = unreal_total if have_any else None

    inputs_stale = freshness.get("level") in ("yellow", "red")

    inp = DecisionInputs(
        now=now,
        regime_label=regime_state.get("regime"),
        regime_confidence=(
            float(regime_state["regime_confidence"])
            if regime_state.get("regime_confidence") is not None else None
        ),
        regime_stability=(
            float(regime_state["regime_stability"])
            if regime_state.get("regime_stability") is not None else None
        ),
        bars_in_current_regime=(
            int(regime_state["bars_in_current_regime"])
            if regime_state.get("bars_in_current_regime") is not None else None
        ),
        candidate_regime=regime_state.get("candidate_regime"),
        candidate_bars=(
            int(regime_state["candidate_bars"])
            if regime_state.get("candidate_bars") is not None else None
        ),
        margin_coefficient=margin_coefficient,
        distance_to_liquidation_pct=distance_to_liq_pct,
        margin_data_age_min=margin_data_age_min,
        position_btc=position_btc,
        unrealized_pnl_usd=unrealized,
        current_price=draft.get("current_price_btc"),
        snapshots_age_min=(freshness.get("ages_min") or {}).get("snapshots_min"),
        regime_state_age_min=(freshness.get("ages_min") or {}).get("regime_state_min"),
        engine_bugs_detected=(
            int(engine_cfg["bugs_detected"])
            if engine_cfg.get("bugs_detected") is not None else None
        ),
        engine_bugs_fixed=(
            int(engine_cfg["bugs_fixed"])
            if engine_cfg.get("bugs_fixed") is not None else None
        ),
        engine_fix_eta=engine_cfg.get("fix_eta"),
        inputs_stale=inputs_stale,
    )
    try:
        result = decision_evaluate(inp)
    except (OSError, ValueError) as exc:
        logging.getLogger(__name__).warning("decision_layer evaluate failed: %s", exc)
        return {
            "last_evaluated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "active_severity": "NONE",
            "events_recent": [],
            "events_24h_count": 0,
            "events_24h_by_rule": {},
            "rate_limit_status": {"primary_used_24h": 0, "primary_cap": 20, "window_oldest_event_at": None},
            "error": str(exc),
        }
    return result.decision_layer_block


def _build_virtual_trader(rows: list[dict[str, Any]], now: datetime) -> dict[str, Any]:
    """Aggregate virtual_trader positions_log.jsonl over 7d window."""
    cutoff = now - timedelta(days=7)
    # latest record per position_id
    latest: dict[str, dict[str, Any]] = {}
    for r in rows:
        pid = r.get("position_id")
        if pid:
            latest[pid] = r

    wins = losses = open_n = 0
    rr_realized: list[float] = []
    open_positions: list[dict[str, Any]] = []
    for r in latest.values():
        try:
            entry_time = datetime.fromisoformat(str(r.get("entry_time", "")).replace("Z", "+00:00"))
        except ValueError:
            continue
        if entry_time < cutoff:
            continue
        status = r.get("status")
        r_real = r.get("r_realized")
        if status in ("open", "tp1_hit"):
            open_n += 1
            open_positions.append({
                "position_id": r.get("position_id"),
                "direction": r.get("direction"),
                "entry_price": r.get("entry_price"),
                "entry_time": r.get("entry_time"),
                "sl": r.get("sl"),
                "tp1": r.get("tp1"),
                "tp2": r.get("tp2"),
                "half_closed": r.get("half_closed", False),
            })
        elif r_real is not None:
            if r_real > 0:
                wins += 1
            else:
                losses += 1
            rr_realized.append(float(r_real))

    avg_rr = round(sum(rr_realized) / len(rr_realized), 2) if rr_realized else 0.0
    decided = wins + losses
    win_rate_pct = round(wins / decided * 100, 1) if decided > 0 else None
    return {
        "signals_7d": wins + losses + open_n,
        "wins": wins,
        "losses": losses,
        "open": open_n,
        "win_rate_pct": win_rate_pct,
        "avg_rr": avg_rr,
        "open_positions": open_positions[:5],
    }


def build_state(
    *,
    now: datetime | None = None,
    snapshots_path: Path = SNAPSHOTS_PATH,
    state_latest_path: Path = STATE_LATEST_PATH,
    signals_path: Path = ADVISE_SIGNALS_PATH,
    null_signals_path: Path = NULL_SIGNALS_PATH,
    events_path: Path = EVENTS_PATH,
    liq_path: Path = LIQ_CLUSTERS_PATH,
    competition_path: Path = COMPETITION_PATH,
    engine_path: Path = ENGINE_STATUS_PATH,
    regime_state_path: Path = CLASSIFIER_A_STATE_PATH,
    virtual_trader_log_path: Path = VIRTUAL_TRADER_LOG_PATH,
) -> dict[str, Any]:
    from services.dashboard.regime_adapter import adapt_regime_state

    now = now or datetime.now(timezone.utc)
    snapshots = _read_csv_latest_by_bot(snapshots_path)
    state_latest = _load_json(state_latest_path)
    signals = _read_jsonl(signals_path)
    null_signals = _read_jsonl(null_signals_path)
    events = _read_jsonl(events_path)
    liq_raw = _load_json(liq_path)
    competition_cfg = _load_json(competition_path)
    engine_cfg = _load_json(engine_path)
    # Classifier A live output projected to Decision Layer schema. Adapter
    # returns None when the file is missing or unprojectable — pass {} to
    # downstream so _build_regime emits its "no regime state" placeholder.
    regime_state = adapt_regime_state(path=regime_state_path) or {}
    vt_rows = _read_jsonl(virtual_trader_log_path)

    # Current price: last signal → state_latest → None
    current_price: float | None = None
    if signals:
        p = signals[-1].get("market_context", {}).get("price_btc")
        if p is not None:
            current_price = float(p)
    if current_price is None:
        raw_p = state_latest.get("exposure", {}).get("price_btc")
        current_price = float(raw_p) if raw_p is not None else None

    exposure = dict(state_latest.get("exposure") or {})
    net_btc_raw = exposure.get("net_btc")
    net_btc: float | None = float(net_btc_raw) if net_btc_raw is not None else None
    fm_raw = exposure.get("free_margin_pct")
    free_margin_pct: float | None = float(fm_raw) if fm_raw is not None else None
    drawdown_pct = _to_float(exposure.get("drawdown_pct"))

    liq_clusters: list[Any] = liq_raw.get("clusters", []) if isinstance(liq_raw, dict) else []

    regime_block = _build_regime(regime_state)
    freshness_block = _build_freshness(
        now=now,
        snapshots_path=snapshots_path,
        regime_state_path=regime_state_path,
    )
    draft = {
        "last_updated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "current_price_btc": current_price,
        "positions": _build_positions(snapshots, net_btc, free_margin_pct, drawdown_pct),
        "competition": _build_competition(competition_cfg),
        "phase_1_paper_journal": _build_phase1(signals, null_signals, now),
        "engine_status": _build_engine_status(engine_cfg),
        "boli_status": list(_BOLI_DEFAULT),
        "recent_decisions": _build_recent_decisions(events),
        "active_liq_clusters": liq_clusters if isinstance(liq_clusters, list) else [],
        "alerts_24h": _build_alerts_24h(events, now),
        "regime": regime_block,
        # forecast: REMOVED in TZ-FORECAST-DECOMMISSION; retired per FORECAST_CALIBRATION_DIAGNOSTIC_v1
        "regulation_action_card": _build_regulation_card(regime_block.get("label")),
        "virtual_trader": _build_virtual_trader(vt_rows, now),
        "freshness": freshness_block,
    }
    draft["decision_layer"] = _build_decision_layer_block(
        now=now,
        draft=draft,
        state_latest=state_latest,
        regime_state=regime_state,
        engine_cfg=engine_cfg,
        freshness=freshness_block,
    )
    return draft


def build_and_save_state(
    *,
    output_path: Path = OUTPUT_PATH,
    now: datetime | None = None,
    snapshots_path: Path = SNAPSHOTS_PATH,
    state_latest_path: Path = STATE_LATEST_PATH,
    signals_path: Path = ADVISE_SIGNALS_PATH,
    null_signals_path: Path = NULL_SIGNALS_PATH,
    events_path: Path = EVENTS_PATH,
    liq_path: Path = LIQ_CLUSTERS_PATH,
    competition_path: Path = COMPETITION_PATH,
    engine_path: Path = ENGINE_STATUS_PATH,
    regime_state_path: Path = CLASSIFIER_A_STATE_PATH,
    virtual_trader_log_path: Path = VIRTUAL_TRADER_LOG_PATH,
) -> dict[str, Any]:
    state = build_state(
        now=now,
        snapshots_path=snapshots_path,
        state_latest_path=state_latest_path,
        signals_path=signals_path,
        null_signals_path=null_signals_path,
        events_path=events_path,
        liq_path=liq_path,
        competition_path=competition_path,
        engine_path=engine_path,
        regime_state_path=regime_state_path,
        virtual_trader_log_path=virtual_trader_log_path,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return state
