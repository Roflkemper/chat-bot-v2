"""Advise audit logger — пишет каждый /advise call для последующей valid'ации.

Цель (TZ-ADVISE-AUDIT 2026-05-07): измерить даёт ли /advise полезный edge.
Через N дней анализируем `state/advise_audit.jsonl`:
  - сколько раз был вердикт LONG/SHORT/RANGE
  - какой движение цены пришло за +4h / +24h
  - сколько раз вердикт совпал со сценарием

Каждая запись — JSON с фиксированным набором полей. Outcome дозаполняется
отдельным процессом (cron/scheduled task) через 4h и 24h.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)
AUDIT_PATH = Path("state/advise_audit.jsonl")


def log_advise_call(
    *,
    verdict: str,
    reasoning: list[str],
    regime_4h: str | None,
    regime_1h: str | None,
    regime_15m: str | None,
    macro_micro_diverge: bool,
    btc_price: float | None,
    setups_count: int,
    open_paper_trades: int,
) -> None:
    """Persist a single /advise invocation snapshot.

    Outcome (price_after_4h / price_after_24h, verdict_correct) дозаполняется
    отдельной job'ой через scripts/advise_outcome_filler.py.
    """
    entry = {
        "ts_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "verdict": verdict,
        "reasoning": reasoning,
        "regime": {
            "4h": regime_4h,
            "1h": regime_1h,
            "15m": regime_15m,
            "diverge": macro_micro_diverge,
        },
        "btc_price": btc_price,
        "setups_count": setups_count,
        "open_paper_trades": open_paper_trades,
        # Outcome поля — дозаполняются позже:
        "price_after_4h": None,
        "price_after_24h": None,
        "verdict_correct_4h": None,
        "verdict_correct_24h": None,
    }
    try:
        AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with AUDIT_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as exc:
        logger.warning("advise_audit.write_failed: %s", exc)
