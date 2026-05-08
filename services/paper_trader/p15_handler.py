"""P-15 paper trader — auto-execute virtual trades on P-15 lifecycle events.

Subscribes to setups with setup_type starting with "p15_" and applies
the corresponding action (open layer / harvest 50% / reentry / close all).
Writes events to state/paper_trades.jsonl with strategy="p15" tag so the
weekly comparison report can split P-15 PnL from manual/auto trades.

Lifecycle mapping:
  P15_*_OPEN    → record OPEN event for new layer ($1000 notional)
  P15_*_HARVEST → record CLOSE_PARTIAL event for 50% of position
  P15_*_REENTRY → record OPEN event for new layer at offset price
  P15_*_CLOSE   → record CLOSE event for full position
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from services.paper_trader import journal
from services.setup_detector.models import Setup

logger = logging.getLogger(__name__)

P15_TRADES_PATH = Path("state/p15_paper_trades.jsonl")
P15_BASE_SIZE_USD = 1000.0


def _basis_get(setup: Setup, label: str, default=None):
    for b in setup.basis:
        if b.label == label:
            return b.value
    return default


def handle_p15_setup(setup: Setup) -> Optional[dict]:
    """Handle a P-15 lifecycle setup → write paper-trader event.

    Returns the recorded event dict, or None if the setup is not P-15.
    """
    stype = setup.setup_type.value
    if not stype.startswith("p15_"):
        return None

    direction_str = "long" if "_long_" in stype else "short"
    stage = str(_basis_get(setup, "stage", "?"))
    now = datetime.now(timezone.utc)
    trade_id = f"p15-{direction_str}-{now.strftime('%Y-%m-%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"

    common = {
        "ts": now.isoformat(),
        "trade_id": trade_id,
        "strategy": "p15",
        "side": direction_str,
        "setup_type": stype,
        "setup_id": setup.setup_id,
        "pair": setup.pair,
        "stage": stage,
        "p15_layer": int(_basis_get(setup, "layers", 0) or 0),
        "p15_avg_entry": float(_basis_get(setup, "avg_entry", 0) or 0),
        "p15_extreme": float(_basis_get(setup, "extreme", 0) or 0),
        "p15_total_size_usd": float(_basis_get(setup, "total_size_usd", 0) or 0),
        "p15_unrealized_usd": float(_basis_get(setup, "unrealized_usd", 0) or 0),
    }

    record: Optional[dict] = None

    if stage == "OPEN":
        record = {**common,
            "action": "OPEN",
            "entry": setup.current_price,
            "size_usd": P15_BASE_SIZE_USD,
            "size_btc": round(P15_BASE_SIZE_USD / setup.current_price, 6),
        }
    elif stage == "HARVEST":
        exit_price = float(_basis_get(setup, "exit_price", 0) or 0)
        harvest_size = float(_basis_get(setup, "harvest_size_usd", 0) or 0)
        harvest_pnl = float(_basis_get(setup, "harvest_pnl_usd", 0) or 0)
        record = {**common,
            "action": "HARVEST",
            "exit_price": exit_price,
            "size_usd": harvest_size,
            "realized_pnl_usd": harvest_pnl,
            "next_reentry_price": float(_basis_get(setup, "next_reentry_price", 0) or 0),
        }
    elif stage == "REENTRY":
        reentry_price = float(_basis_get(setup, "reentry_price", 0) or 0)
        record = {**common,
            "action": "OPEN",
            "entry": reentry_price,
            "size_usd": P15_BASE_SIZE_USD,
            "size_btc": round(P15_BASE_SIZE_USD / max(reentry_price, 1), 6),
            "is_reentry": True,
        }
    elif stage == "CLOSE":
        close_price = float(_basis_get(setup, "close_price", 0) or 0)
        realized = float(_basis_get(setup, "realized_pnl_usd", 0) or 0)
        reason = str(_basis_get(setup, "reason", "") or "")
        record = {**common,
            "action": "CLOSE",
            "exit_price": close_price,
            "size_usd": float(common["p15_total_size_usd"]),
            "realized_pnl_usd": realized,
            "reason": reason,
        }

    if record is None:
        return None

    # Write to dedicated P-15 jsonl + main paper_trades.jsonl for unified reporting
    try:
        P15_TRADES_PATH.parent.mkdir(parents=True, exist_ok=True)
        with P15_TRADES_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        logger.exception("p15_paper_trader.p15_write_failed")

    try:
        journal.append_event(record)
    except Exception:
        logger.exception("p15_paper_trader.journal_write_failed")

    logger.info(
        "p15_paper_trader.recorded stage=%s side=%s layer=%d size=%.0f",
        stage, direction_str, common["p15_layer"], common.get("p15_total_size_usd", 0),
    )
    return record
