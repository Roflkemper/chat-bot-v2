"""Action-specific decision log — infrastructure for honest EV scoring.

Format (jsonl): state/exit_advisor_decisions.jsonl
  {
    "ts_utc": "2026-05-07T20:30:00Z",
    "decision_id": "uuid",
    "scenario_class": "early_intervention",
    "action_taken": "raise_boundary_pct_0.5" | "tighten_grid" | "close_25pct" | "monitor",
    "snapshot": {
      "btc_price": 81000,
      "worst_dd_pct": -4.0,
      "min_liq_dist_pct": 19.1,
      "duration_in_dd_h": 0.5,
      "short_btc_total": -2.328,
      "free_margin_pct": 91,
      "regime_4h_v2": "SLOW_UP",
      ...
    },
    "outcome_1h_pnl_change": null,    # filled later
    "outcome_4h_pnl_change": null,
    "outcome_24h_pnl_change": null,
    "outcome_1h_btc_move_pct": null,
    "outcome_4h_btc_move_pct": null,
    "outcome_24h_btc_move_pct": null
  }

Через 2-3 недели накопится 30-50+ decisions → scripts/exit_advisor_outcome_filler.py
дозаполнит outcome поля → можно строить EV scoring.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

DECISIONS_PATH = Path("state/exit_advisor_decisions.jsonl")


def log_decision(
    *,
    scenario_class: str,
    action_taken: str,
    snapshot: dict[str, Any],
    decision_id: Optional[str] = None,
) -> str:
    """Persist single operator decision. Returns decision_id."""
    DECISIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    if decision_id is None:
        decision_id = str(uuid.uuid4())

    entry = {
        "ts_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "decision_id": decision_id,
        "scenario_class": scenario_class,
        "action_taken": action_taken,
        "snapshot": snapshot,
        # Outcome fields — filled by scripts/exit_advisor_outcome_filler.py
        "outcome_1h_pnl_change": None,
        "outcome_4h_pnl_change": None,
        "outcome_24h_pnl_change": None,
        "outcome_1h_btc_move_pct": None,
        "outcome_4h_btc_move_pct": None,
        "outcome_24h_btc_move_pct": None,
    }

    try:
        with DECISIONS_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        logger.exception("decisions_log.write_failed")

    return decision_id


def load_decisions() -> list[dict]:
    if not DECISIONS_PATH.exists():
        return []
    out = []
    try:
        with DECISIONS_PATH.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return out


def overwrite_decisions(decisions: list[dict]) -> None:
    """Used by outcome filler to update entries with computed outcomes."""
    DECISIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        with DECISIONS_PATH.open("w", encoding="utf-8") as f:
            for d in decisions:
                f.write(json.dumps(d, ensure_ascii=False) + "\n")
    except OSError:
        logger.exception("decisions_log.overwrite_failed")
