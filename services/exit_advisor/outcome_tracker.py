"""Outcome tracker: log operator decisions and track follow-up P&L.

Storage: data/exit_advisor/decisions.jsonl (append-only)
Followup schedule: +1h, +4h, +24h snapshots via OutcomeTracker.tick()

Each decision record:
  decision_id, ts_utc, scenario_class, option_idx, action_name, params,
  state_snapshot (serialized subset), expected_mean_pnl_usd, actual outcomes
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .position_state import PositionStateSnapshot
from .strategy_ranker import RankedStrategy

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[2]
_DECISIONS_JSONL = _ROOT / "data" / "exit_advisor" / "decisions.jsonl"

_FOLLOWUP_HORIZONS_H = [1, 4, 24]


class OutcomeTracker:
    def __init__(self, storage_path: Path = _DECISIONS_JSONL) -> None:
        self._path = storage_path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # In-memory pending followups: decision_id → {ts_fire, horizon_h, baseline_unrealized}
        self._pending: dict[str, list[dict]] = {}

    def log_decision(
        self,
        state: PositionStateSnapshot,
        strategy: RankedStrategy,
        option_idx: int,
    ) -> str:
        """Log an operator decision. Returns decision_id."""
        decision_id = f"exit-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"

        record: dict[str, Any] = {
            "decision_id": decision_id,
            "ts_utc": state.captured_at.isoformat(),
            "scenario_class": state.scenario_class.value,
            "option_idx": option_idx,
            "action_name": strategy.action_name,
            "family": strategy.family.value,
            "params": strategy.params,
            "expected_mean_pnl_usd": strategy.mean_pnl_usd,
            "win_rate_pct": strategy.win_rate_pct,
            "confidence": strategy.confidence.value,
            "n_samples": strategy.n_samples,
            "state": {
                "total_unrealized_usd": state.total_unrealized_usd,
                "free_margin_pct": state.free_margin_pct,
                "worst_dd_pct": state.worst_dd_pct,
                "min_liq_dist_pct": state.min_distance_to_liq_pct,
                "current_price": state.current_price,
            },
            "outcomes": {},
            "version": 1,
        }

        self._append(record)

        # Schedule followups
        now = state.captured_at
        self._pending[decision_id] = [
            {
                "horizon_h": h,
                "ts_fire": (now + timedelta(hours=h)).isoformat(),
                "baseline_unrealized": state.total_unrealized_usd,
                "fired": False,
            }
            for h in _FOLLOWUP_HORIZONS_H
        ]

        logger.info("exit_advisor.outcome_tracker: logged decision_id=%s", decision_id)
        return decision_id

    def tick(self, current_state: PositionStateSnapshot) -> list[dict]:
        """Check pending followups. Returns list of fired outcome dicts."""
        now = current_state.captured_at
        fired: list[dict] = []

        for decision_id, followups in list(self._pending.items()):
            for fu in followups:
                if fu["fired"]:
                    continue
                fire_ts = datetime.fromisoformat(fu["ts_fire"])
                if now >= fire_ts:
                    delta = current_state.total_unrealized_usd - fu["baseline_unrealized"]
                    outcome = {
                        "decision_id": decision_id,
                        "horizon_h": fu["horizon_h"],
                        "ts_utc": now.isoformat(),
                        "delta_unrealized_usd": round(delta, 2),
                        "current_price": current_state.current_price,
                    }
                    self._update_outcome(decision_id, fu["horizon_h"], outcome)
                    fu["fired"] = True
                    fired.append(outcome)

            # Clean up fully resolved decisions
            if all(f["fired"] for f in followups):
                del self._pending[decision_id]

        return fired

    def weekly_stats(self) -> dict:
        """Aggregate stats from the last 7 days of decisions."""
        records = self._load_all()
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)

        recent = [
            r for r in records
            if datetime.fromisoformat(r["ts_utc"].replace("Z", "+00:00")) >= cutoff
        ]

        if not recent:
            return {"period_days": 7, "n_decisions": 0}

        total = len(recent)
        outcomes_1h = [r["outcomes"].get("1h", {}).get("delta_unrealized_usd") for r in recent]
        outcomes_24h = [r["outcomes"].get("24h", {}).get("delta_unrealized_usd") for r in recent]

        def _mean(vals):
            clean = [v for v in vals if v is not None]
            return round(sum(clean) / len(clean), 2) if clean else None

        return {
            "period_days": 7,
            "n_decisions": total,
            "mean_delta_1h_usd": _mean(outcomes_1h),
            "mean_delta_24h_usd": _mean(outcomes_24h),
            "action_breakdown": _count_by(recent, "action_name"),
            "scenario_breakdown": _count_by(recent, "scenario_class"),
        }

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _append(self, record: dict) -> None:
        try:
            with self._path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            logger.exception("exit_advisor.outcome_tracker: append failed")

    def _load_all(self) -> list[dict]:
        if not self._path.exists():
            return []
        records = []
        try:
            with self._path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        records.append(json.loads(line))
        except Exception:
            logger.exception("exit_advisor.outcome_tracker: load failed")
        return records

    def _update_outcome(self, decision_id: str, horizon_h: int, outcome: dict) -> None:
        """Update outcome in existing record (rewrite last line matching id)."""
        try:
            records = self._load_all()
            for r in records:
                if r.get("decision_id") == decision_id:
                    r.setdefault("outcomes", {})[f"{horizon_h}h"] = outcome
            with self._path.open("w", encoding="utf-8") as f:
                for r in records:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
        except Exception:
            logger.exception("exit_advisor.outcome_tracker: update_outcome failed")


def _count_by(records: list[dict], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in records:
        v = r.get(key, "unknown")
        counts[v] = counts.get(v, 0) + 1
    return counts
