"""Paper trade journal — append-only JSONL.

Schema (one record per state-change event):
  {
    "ts": "2026-05-07T10:00:00Z",
    "trade_id": "pt-2026-05-07-100000-ab12cd",
    "action": "OPEN" | "TP1" | "TP2" | "SL" | "EXPIRE" | "CANCEL",
    "side": "long" | "short",
    "setup_type": "long_double_bottom",
    "entry": 81250.0,
    "size_usd": 10000.0,
    "size_btc": 0.123,
    "sl": 81000.0, "tp1": 81700.0, "tp2": 82200.0,
    "exit_price": null,           # filled at TP/SL
    "realized_pnl_usd": null,     # filled at TP/SL
    "rr_realized": null,
    "hours_in_trade": null,
    "regime_at_entry": "RANGE",
    "session_at_entry": "ny_am",
    "confidence_pct": 75.0,
    "reason": "double_bottom_low_1=80850, low_2=80920, peak=82150, candle_confirmation=bullish_engulfing"
  }
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

JOURNAL_PATH = Path("state/paper_trades.jsonl")
_lock = threading.Lock()


def _resolve_path(path: Path | None) -> Path:
    return path if path is not None else JOURNAL_PATH


def append_event(record: dict, *, path: Path | None = None) -> None:
    """Append one event to the journal. Resolves JOURNAL_PATH at call time."""
    p = _resolve_path(path)
    with _lock:
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            with p.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        except OSError as exc:
            logger.warning("paper_trader.journal_write_failed: %s", exc)


def read_all(*, path: Path | None = None) -> list[dict]:
    """Read all journal events."""
    p = _resolve_path(path)
    if not p.exists():
        return []
    out = []
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError as exc:
        logger.warning("paper_trader.journal_read_failed: %s", exc)
    return out


def open_trades(*, path: Path | None = None) -> list[dict]:
    """Reconstruct currently-open trades from journal events.

    v0.1 convention: TP1, TP2, SL, EXPIRE, CANCEL all fully close the trade
    (services/paper_trader/trader.py:163 comment: 'for v0.1 we treat as full
    close to keep accounting simple'). Without removing the trade on TP1 the
    loop re-emits TP1 every poll cycle (was producing 5x duplicate Telegram
    alerts per trade — see commit history for the fix).
    """
    events = read_all(path=_resolve_path(path))
    by_id: dict[str, dict] = {}
    for e in events:
        tid = e.get("trade_id")
        if not tid:
            continue
        if e.get("action") == "OPEN":
            by_id[tid] = dict(e)
        elif e.get("action") in ("TP1", "TP2", "SL", "EXPIRE", "CANCEL"):
            by_id.pop(tid, None)
    return list(by_id.values())


def find_trade(trade_id: str, *, path: Path | None = None) -> Optional[dict]:
    for e in reversed(read_all(path=_resolve_path(path))):
        if e.get("trade_id") == trade_id and e.get("action") == "OPEN":
            return e
    return None
