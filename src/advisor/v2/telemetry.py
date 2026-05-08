"""Telemetry: advisor_log.jsonl + advisor_outcomes.jsonl + auto reconciliation."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .cascade import Recommendation

ROOT = Path(__file__).resolve().parents[3]
LOG_PATH = ROOT / "logs" / "advisor_log.jsonl"
OUTCOMES_PATH = ROOT / "logs" / "advisor_outcomes.jsonl"

HORIZONS_H: tuple[int, ...] = (1, 4, 24)

# Plays that open SHORT positions (profit when price falls)
_SHORT_PLAYS: frozenset[str] = frozenset({"P-6", "P-2"})
# Plays that open LONG positions (profit when price rises)
_LONG_PLAYS: frozenset[str] = frozenset({"P-7", "P-3"})


def _side_for_play(play_id: str) -> str:
    if play_id in _SHORT_PLAYS:
        return "SHORT"
    if play_id in _LONG_PLAYS:
        return "LONG"
    return "DEFENSIVE"


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_utc(ts: str) -> datetime | None:
    try:
        return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _append(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _read_all(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").strip().splitlines()
    except OSError:
        return []
    result: list[dict] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            result.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return result


# ── Logging ──────────────────────────────────────────────────────────────────

def log_recommendation(rec: Recommendation, portfolio_balance: float) -> None:
    _append(LOG_PATH, {
        "ts_utc": rec.ts_utc,
        "play_id": rec.play_id,
        "play_name": rec.play_name,
        "symbol": rec.symbol,
        "trigger": rec.trigger,
        "size_mode": rec.size_mode,
        "size_btc": rec.size_btc,
        "expected_pnl": rec.expected_pnl,
        "win_rate": rec.win_rate,
        "dd_pct": rec.dd_pct,
        "params": rec.params,
        "reason": rec.reason,
        "portfolio_balance": portfolio_balance,
    })


def schedule_outcome_check(rec: Recommendation, price_at_rec: float) -> None:
    """Register a pending outcome check for 1h/4h/24h reconciliation."""
    _append(OUTCOMES_PATH, {
        "type": "pending",
        "ts_utc": rec.ts_utc,
        "play_id": rec.play_id,
        "symbol": rec.symbol,
        "trigger": rec.trigger,
        "price_at_rec": price_at_rec,
        "size_btc": rec.size_btc,
        "side": _side_for_play(rec.play_id),
        "expected_pnl": rec.expected_pnl,
    })


# ── Reconciliation ────────────────────────────────────────────────────────────

def _pnl_proxy(side: str, price_at_rec: float, price_now: float, size_btc: float) -> float:
    """Simplified PnL proxy (BTC inverse-style): not grid simulation."""
    if side == "SHORT":
        return (price_at_rec - price_now) * size_btc
    if side == "LONG":
        return (price_now - price_at_rec) * size_btc
    return 0.0


def reconcile_pending(current_price: float) -> int:
    """Check all pending outcome entries; append reconciled records for elapsed horizons.

    Returns count of new reconciled entries written.
    """
    if current_price <= 0:
        return 0

    now = datetime.now(timezone.utc)
    all_records = _read_all(OUTCOMES_PATH)

    # Build set of already-reconciled (ts_utc, play_id, horizon) tuples
    done: set[tuple[str, str, int]] = set()
    for r in all_records:
        if r.get("type") == "outcome":
            done.add((r["rec_ts_utc"], r["play_id"], r["horizon_h"]))

    written = 0
    for r in all_records:
        if r.get("type") != "pending":
            continue
        ts = _parse_utc(r.get("ts_utc", ""))
        if ts is None:
            continue
        price_at_rec = float(r.get("price_at_rec") or 0)
        size_btc = float(r.get("size_btc") or 0)
        side = str(r.get("side") or "DEFENSIVE")
        play_id = r.get("play_id", "")
        rec_ts = r.get("ts_utc", "")

        for h in HORIZONS_H:
            if (rec_ts, play_id, h) in done:
                continue
            if now < ts + timedelta(hours=h):
                continue
            # Horizon elapsed — compute outcome
            pnl = _pnl_proxy(side, price_at_rec, current_price, size_btc)
            _append(OUTCOMES_PATH, {
                "type": "outcome",
                "rec_ts_utc": rec_ts,
                "play_id": play_id,
                "horizon_h": h,
                "price_at_rec": price_at_rec,
                "price_now": current_price,
                "pnl_proxy": round(pnl, 2),
                "hit": pnl > 0,
                "side": side,
                "expected_pnl": float(r.get("expected_pnl") or 0),
                "ts_reconciled": _now_utc(),
            })
            done.add((rec_ts, play_id, h))
            written += 1

    return written


# ── Stats ─────────────────────────────────────────────────────────────────────

def get_recent_log(n: int = 10) -> list[dict]:
    if not LOG_PATH.exists():
        return []
    try:
        lines = LOG_PATH.read_text(encoding="utf-8").strip().splitlines()
    except OSError:
        return []
    result: list[dict] = []
    for line in lines[-n:]:
        try:
            result.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return result


def get_stats(days: int = 7) -> dict[str, Any]:
    """Return recommendation count, hit rate, and actual vs expected pnl per play."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # Count recommendations from log
    log_entries = _read_all(LOG_PATH)
    by_play_count: dict[str, int] = {}
    for e in log_entries:
        ts = _parse_utc(e.get("ts_utc", ""))
        if ts and ts >= cutoff:
            pid = e.get("play_id", "?")
            by_play_count[pid] = by_play_count.get(pid, 0) + 1

    # Aggregate outcomes
    outcomes = _read_all(OUTCOMES_PATH)
    by_play_hits: dict[str, list[bool]] = {}
    by_play_pnl_actual: dict[str, list[float]] = {}
    by_play_pnl_expected: dict[str, list[float]] = {}

    for o in outcomes:
        if o.get("type") != "outcome":
            continue
        ts = _parse_utc(o.get("ts_reconciled") or o.get("rec_ts_utc", ""))
        if ts and ts < cutoff:
            continue
        if o.get("horizon_h") != 4:  # Use 4h horizon as primary metric
            continue
        pid = o.get("play_id", "?")
        by_play_hits.setdefault(pid, []).append(bool(o.get("hit")))
        by_play_pnl_actual.setdefault(pid, []).append(float(o.get("pnl_proxy") or 0))
        by_play_pnl_expected.setdefault(pid, []).append(float(o.get("expected_pnl") or 0))

    play_stats: dict[str, dict] = {}
    for pid, hits in by_play_hits.items():
        n_hits = sum(1 for h in hits if h)
        play_stats[pid] = {
            "n": len(hits),
            "hit_rate": round(n_hits / len(hits) * 100, 1) if hits else 0.0,
            "mean_actual_pnl": round(sum(by_play_pnl_actual.get(pid, [])) / max(1, len(by_play_pnl_actual.get(pid, []))), 2),
            "mean_expected_pnl": round(sum(by_play_pnl_expected.get(pid, [])) / max(1, len(by_play_pnl_expected.get(pid, []))), 2),
        }

    total_recs = sum(by_play_count.values())
    return {
        "total": total_recs,
        "days": days,
        "by_play_count": by_play_count,
        "by_play_outcomes": play_stats,
    }
