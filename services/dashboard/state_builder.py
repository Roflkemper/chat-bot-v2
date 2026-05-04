from __future__ import annotations

import csv
import json
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
LATEST_FORECAST_PATH = Path("data/forecast_features/latest_forecast.json")
VIRTUAL_TRADER_LOG_PATH = Path("data/virtual_trader/positions_log.jsonl")
OUTPUT_PATH = Path("docs/STATE/dashboard_state.json")

# CV-validated mean Brier per regime/horizon (from oos_validation_*.json).
# Used to assign band (green/yellow/red) when no live forecast is present.
_CV_BRIER: dict[str, dict[str, float]] = {
    "MARKUP":   {"1h": 0.2733, "4h": 0.2590, "1d": 0.2346},
    "MARKDOWN": {"1h": 0.2042, "4h": 0.2278, "1d": 0.2801},
    "RANGE":    {"1h": 0.2467, "4h": 0.2478, "1d": 0.2502},
}

# Validated delivery matrix — mirrors regime_switcher._DELIVERY_MATRIX.
_DELIVERY_MATRIX: dict[str, dict[str, str]] = {
    "MARKUP":       {"1h": "qualitative", "4h": "numeric",     "1d": "gated"},
    "MARKDOWN":     {"1h": "numeric",     "4h": "numeric",     "1d": "qualitative"},
    "RANGE":        {"1h": "numeric",     "4h": "numeric",     "1d": "numeric"},
    "DISTRIBUTION": {"1h": "qualitative", "4h": "qualitative", "1d": "qualitative"},
}

PHASE_1_TOTAL_DAYS = 14

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


def _read_csv_latest_by_bot(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    latest: dict[str, dict[str, str]] = {}
    try:
        with path.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                bot_id = str(row.get("bot_id", "")).strip()
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


def _brier_band(brier: float | None) -> str:
    """GREEN ≤0.22 / YELLOW 0.22–0.265 / RED >0.265 / 'qualitative' for None."""
    if brier is None:
        return "qualitative"
    if brier <= 0.22:
        return "green"
    if brier <= 0.265:
        return "yellow"
    return "red"


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
    latest_forecast_path: Path,
    regime_state_path: Path,
) -> dict[str, Any]:
    """Per-source freshness ages + warning level.

    Warning levels:
      "ok"     — all sources < 10 min old
      "yellow" — at least one source 10-120 min old (positions stale or forecast hours-old)
      "red"    — at least one source > 120 min old (likely the live tracker is down)
    """
    ages = {
        "snapshots_min": _file_age_minutes(snapshots_path, now),
        "latest_forecast_min": _file_age_minutes(latest_forecast_path, now),
        "regime_state_min": _file_age_minutes(regime_state_path, now),
    }
    # Warning derivation
    level = "ok"
    notes: list[str] = []
    pos_age = ages["snapshots_min"]
    fc_age = ages["latest_forecast_min"]
    if pos_age is None:
        level = "red"
        notes.append("snapshots.csv missing — tracker not running")
    elif pos_age > 120:
        level = "red"
        notes.append(f"snapshots stale ({pos_age:.0f} min) — tracker may be down")
    elif pos_age > 10:
        level = max(level, "yellow", key=["ok", "yellow", "red"].index)
        notes.append(f"snapshots {pos_age:.0f} min old")

    if fc_age is None:
        notes.append("no live forecast — using CV-matrix fallback")
    elif fc_age > 1440:  # >24h
        level = "red"
        notes.append(f"forecast {fc_age/60:.0f}h stale — bootstrap may need re-run")
    elif fc_age > 120:  # >2h
        level = max(level, "yellow", key=["ok", "yellow", "red"].index)
        notes.append(f"forecast {fc_age:.0f} min old")

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


def _build_forecast(latest_forecast: dict[str, Any], regime: str | None) -> dict[str, Any]:
    """Render 1h/4h/1d forecast with brier-band colors.

    If a live forecast file exists, use it. Otherwise emit static delivery
    matrix entries (mode + CV-mean brier) so the panel renders meaningfully
    on first load.
    """
    out: dict[str, Any] = {"horizons": {}, "source": None}
    horizons = ("1h", "4h", "1d")

    if latest_forecast and "horizons" in latest_forecast:
        out["source"] = "live"
        out["bar_time"] = latest_forecast.get("bar_time")
        out["regime_at_forecast"] = latest_forecast.get("regime")
        for hz in horizons:
            entry = latest_forecast["horizons"].get(hz, {})
            mode = entry.get("mode", "qualitative")
            value = entry.get("value")
            brier = entry.get("brier")
            out["horizons"][hz] = {
                "mode": mode,
                "value": value,
                "brier": brier,
                "band": _brier_band(brier) if mode == "numeric" else "qualitative",
                "caveat": entry.get("caveat"),
            }
        return out

    # Fallback: emit CV-validated delivery matrix entries for current regime
    out["source"] = "cv_matrix"
    if regime in _CV_BRIER:
        for hz in horizons:
            mode_spec = _DELIVERY_MATRIX[regime][hz]
            cv_brier = _CV_BRIER[regime][hz]
            if mode_spec == "qualitative":
                out["horizons"][hz] = {
                    "mode": "qualitative",
                    "value": None,
                    "brier": cv_brier,
                    "band": "qualitative",
                    "caveat": "delivered as qualitative per validated matrix",
                }
            elif mode_spec == "gated":
                out["horizons"][hz] = {
                    "mode": "gated",
                    "value": None,
                    "brier": cv_brier,
                    "band": _brier_band(cv_brier),
                    "caveat": "numeric only when regime_stability > 0.70",
                }
            else:
                out["horizons"][hz] = {
                    "mode": "numeric",
                    "value": None,
                    "brier": cv_brier,
                    "band": _brier_band(cv_brier),
                    "caveat": None,
                }
    else:
        for hz in horizons:
            out["horizons"][hz] = {
                "mode": "qualitative",
                "value": None,
                "brier": None,
                "band": "qualitative",
                "caveat": "no regime",
            }
    return out


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
    regime_state_path: Path = REGIME_STATE_PATH,
    latest_forecast_path: Path = LATEST_FORECAST_PATH,
    virtual_trader_log_path: Path = VIRTUAL_TRADER_LOG_PATH,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    snapshots = _read_csv_latest_by_bot(snapshots_path)
    state_latest = _load_json(state_latest_path)
    signals = _read_jsonl(signals_path)
    null_signals = _read_jsonl(null_signals_path)
    events = _read_jsonl(events_path)
    liq_raw = _load_json(liq_path)
    competition_cfg = _load_json(competition_path)
    engine_cfg = _load_json(engine_path)
    regime_state = _load_json(regime_state_path)
    latest_forecast = _load_json(latest_forecast_path)
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
    return {
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
        "forecast": _build_forecast(latest_forecast, regime_block.get("label")),
        "virtual_trader": _build_virtual_trader(vt_rows, now),
        "freshness": _build_freshness(
            now=now,
            snapshots_path=snapshots_path,
            latest_forecast_path=latest_forecast_path,
            regime_state_path=regime_state_path,
        ),
    }


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
    regime_state_path: Path = REGIME_STATE_PATH,
    latest_forecast_path: Path = LATEST_FORECAST_PATH,
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
        latest_forecast_path=latest_forecast_path,
        virtual_trader_log_path=virtual_trader_log_path,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return state
