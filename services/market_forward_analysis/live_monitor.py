"""Live Brier tracking and alert triggers for self-monitoring.

Two-stage flow:
  1. record_prediction(timestamp, regime, horizon, prob_up, ...)  -> appended pending
  2. resolve_pending(now)  -> for each pending whose horizon has elapsed,
     compute outcome from actual price series and append a resolved record
  3. rolling_brier(regime, horizon, n=100) -> mean Brier over last n resolved
  4. check_alerts(matrix) -> list of cells where rolling Brier exceeds threshold
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

_ROOT = Path(__file__).resolve().parents[2]
_LOG_PATH = _ROOT / "data" / "calibration" / "live_brier_log.jsonl"

_HORIZON_HOURS = {"1h": 1, "4h": 4, "1d": 24}
_ALERT_THRESHOLD = 0.28  # rolling Brier above this for a numeric cell -> alert


def _ensure_dir() -> None:
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def _append(rec: dict) -> None:
    _ensure_dir()
    with _LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, default=str) + "\n")


def _read_all() -> list[dict]:
    if not _LOG_PATH.exists():
        return []
    out = []
    with _LOG_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def record_prediction(
    timestamp: datetime,
    regime: str,
    horizon: str,
    prob_up: float,
    entry_price: float,
) -> None:
    """Record a numeric prediction for later resolution."""
    rec = {
        "kind": "pending",
        "timestamp": timestamp.isoformat(),
        "regime": regime,
        "horizon": horizon,
        "prob_up": float(prob_up),
        "entry_price": float(entry_price),
        "resolves_at": (timestamp + timedelta(hours=_HORIZON_HOURS[horizon])).isoformat(),
    }
    _append(rec)


def resolve_pending(now: datetime, price_series: pd.Series) -> int:
    """Resolve any pending predictions whose horizon has elapsed.

    price_series: DatetimeIndex (UTC) -> close price.
    Returns count of resolutions.
    """
    rows = _read_all()
    # Already-resolved predictions tracked by (timestamp, horizon) pair
    resolved_keys = {
        (r["timestamp"], r["horizon"]) for r in rows if r.get("kind") == "resolved"
    }
    n_resolved = 0
    for r in rows:
        if r.get("kind") != "pending":
            continue
        key = (r["timestamp"], r["horizon"])
        if key in resolved_keys:
            continue
        resolves_at = datetime.fromisoformat(r["resolves_at"])
        if now < resolves_at:
            continue
        # Find closing price closest to resolves_at
        try:
            idx = price_series.index.get_indexer([resolves_at], method="nearest")[0]
            close_at_horizon = float(price_series.iloc[idx])
        except (KeyError, IndexError):
            continue
        entry = float(r["entry_price"])
        pct = (close_at_horizon - entry) / entry * 100
        actual_up = 1.0 if pct > 0.3 else 0.0
        prob_up = float(r["prob_up"])
        brier = (prob_up - actual_up) ** 2
        _append({
            "kind": "resolved",
            "timestamp": r["timestamp"],
            "regime": r["regime"],
            "horizon": r["horizon"],
            "prob_up": prob_up,
            "actual_up": actual_up,
            "actual_pct": round(pct, 3),
            "brier": round(brier, 4),
        })
        n_resolved += 1
    return n_resolved


def rolling_brier(regime: str, horizon: str, n: int = 100) -> Optional[float]:
    """Mean Brier over the last n resolved predictions for (regime, horizon)."""
    rows = _read_all()
    matching = [
        r for r in rows
        if r.get("kind") == "resolved"
        and r.get("regime") == regime
        and r.get("horizon") == horizon
    ]
    if not matching:
        return None
    last = matching[-n:]
    return sum(r["brier"] for r in last) / len(last)


def check_alerts(numeric_cells: dict[str, dict[str, str]]) -> list[dict]:
    """Return list of alert dicts for numeric cells whose rolling Brier > threshold.

    numeric_cells: {regime: {horizon: mode}} — only "numeric" cells are checked.
    """
    alerts = []
    for regime, hz_modes in numeric_cells.items():
        for hz, mode in hz_modes.items():
            if mode != "numeric":
                continue
            rb = rolling_brier(regime, hz, n=100)
            if rb is not None and rb > _ALERT_THRESHOLD:
                alerts.append({
                    "regime": regime,
                    "horizon": hz,
                    "rolling_brier": round(rb, 4),
                    "threshold": _ALERT_THRESHOLD,
                    "msg": f"Live Brier degraded: {regime}-{hz} = {rb:.4f} > {_ALERT_THRESHOLD}",
                })
    return alerts
