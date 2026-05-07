"""Track sign-flips в funding и premium из state/deriv_live_history.jsonl.

Когда funding или premium меняет знак — это сигнал смены sentiment рынка.
Используется в /advise + /momentum для контекста "когда последний раз было".
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
HISTORY_PATH = ROOT / "state" / "deriv_live_history.jsonl"


def _load_history(symbol: str = "BTCUSDT", max_entries: int = 500) -> list[dict]:
    """Read last N snapshots from deriv_live_history.jsonl.

    Returns list of dicts with: ts, funding, premium, oi.
    Sorted oldest → newest.
    """
    if not HISTORY_PATH.exists():
        return []
    entries: list[dict] = []
    try:
        with HISTORY_PATH.open(encoding="utf-8") as f:
            lines = f.readlines()
        for line in lines[-max_entries:]:
            line = line.strip()
            if not line:
                continue
            try:
                snap = json.loads(line)
            except json.JSONDecodeError:
                continue
            sym_data = snap.get(symbol, {})
            if not isinstance(sym_data, dict):
                continue
            ts_str = snap.get("last_updated", "")
            if not ts_str:
                continue
            entries.append({
                "ts": ts_str,
                "funding": sym_data.get("funding_rate_8h"),
                "premium": sym_data.get("premium_pct"),
                "oi_native": sym_data.get("oi_native"),
            })
    except OSError:
        logger.exception("flip_tracker.history_read_failed")
        return []
    return entries


def _find_last_flip(values: list[tuple[str, float | None]], current_sign: str) -> dict | None:
    """Find last entry with opposite sign. Returns {ts, value, hours_ago} or None."""
    if not values:
        return None
    now = datetime.now(timezone.utc)
    # Iterate backwards
    for ts_str, val in reversed(values):
        if val is None:
            continue
        v_sign = "+" if val > 0 else ("-" if val < 0 else "0")
        if v_sign != current_sign and v_sign != "0":
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                hours_ago = (now - ts).total_seconds() / 3600
                return {
                    "ts": ts_str,
                    "value": val,
                    "hours_ago": round(hours_ago, 1),
                }
            except ValueError:
                continue
    return None


def detect_oi_spike(symbol: str = "BTCUSDT", lookback_15min: int = 3) -> dict | None:
    """Detect OI rapid change в последние 15 мин (3 snapshots × 5 мин).

    Returns:
      {"oi_change_15min_pct": 1.8, "direction": "up"|"down"} or None.

    >1% за 15 мин = большие позиции открываются/закрываются. Если OI растёт
    при росте цены — новый long impulse. Если OI падает при росте —
    short squeeze (короткие закрываются).
    """
    entries = _load_history(symbol)
    if len(entries) < lookback_15min + 1:
        return None
    oi_now = entries[-1].get("oi_native")
    oi_then = entries[-1 - lookback_15min].get("oi_native")
    if oi_now is None or oi_then is None or oi_then <= 0:
        return None
    pct = (oi_now / oi_then - 1) * 100
    if abs(pct) < 0.5:  # noise threshold
        return None
    return {
        "oi_change_15min_pct": round(pct, 2),
        "direction": "up" if pct > 0 else "down",
    }


def detect_flips(symbol: str = "BTCUSDT") -> dict:
    """Detect last funding/premium flip events.

    Returns:
      {
        "funding": {"current": -0.001, "current_sign": "-",
                    "last_flip": {"ts": ..., "value": +0.005, "hours_ago": 12.3},
                    "current_streak_hours": 12.3},
        "premium": {...},
      }
    """
    entries = _load_history(symbol)
    if not entries:
        return {}

    funding_history = [(e["ts"], e["funding"]) for e in entries]
    premium_history = [(e["ts"], e["premium"]) for e in entries]

    out: dict = {}

    # Latest values
    cur_funding = next((v for _, v in reversed(funding_history) if v is not None), None)
    cur_premium = next((v for _, v in reversed(premium_history) if v is not None), None)

    if cur_funding is not None:
        cs = "+" if cur_funding > 0 else ("-" if cur_funding < 0 else "0")
        flip = _find_last_flip(funding_history, cs)
        out["funding"] = {
            "current": cur_funding,
            "current_sign": cs,
            "last_flip": flip,
            "current_streak_hours": flip["hours_ago"] if flip else None,
        }

    if cur_premium is not None:
        cs = "+" if cur_premium > 0 else ("-" if cur_premium < 0 else "0")
        flip = _find_last_flip(premium_history, cs)
        out["premium"] = {
            "current": cur_premium,
            "current_sign": cs,
            "last_flip": flip,
            "current_streak_hours": flip["hours_ago"] if flip else None,
        }

    return out
