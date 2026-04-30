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
OUTPUT_PATH = Path("docs/STATE/dashboard_state.json")

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
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return state
