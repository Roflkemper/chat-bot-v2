"""Deterministic virtual paper trader for self-monitoring of forecast signals.

Rules (per TZ-FINAL):
  Entry:
    numeric prob_down >= 0.55 on 1h AND regime in {MARKDOWN, RANGE} → short
    numeric prob_up   >= 0.55 on 1h AND regime in {MARKUP,   RANGE} → long
    Otherwise: no signal
    Max 1 open position at a time
  Sizing:
    SL  = entry - 1.2 * ATR  (or +1.2*ATR for short)
    TP1 = 1.5 R from entry  (50% close)
    TP2 = 3.0 R from entry  (50% close)
    Time exit: 4h on 1h-signal, 16h on 4h-signal
  Storage: data/virtual_trader/positions_log.jsonl  (append-only)
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[2]
_LOG_DIR  = _ROOT / "data" / "virtual_trader"
_LOG_PATH = _LOG_DIR / "positions_log.jsonl"

_ENTRY_THRESHOLD = 0.55
_SL_ATR_MULT = 1.2
_TP1_R = 1.5
_TP2_R = 3.0
_TTL_BY_SIGNAL = {"1h": timedelta(hours=4), "4h": timedelta(hours=16)}


@dataclass
class Position:
    position_id: str
    direction: str            # "long" | "short"
    entry_time: str           # iso
    entry_price: float
    sl: float
    tp1: float
    tp2: float
    atr: float
    signal_source: str        # e.g. "1h numeric prob_down=0.58 in MARKDOWN"
    ttl_iso: str
    status: str = "open"      # "open" | "tp1_hit" | "closed_tp2" | "closed_sl" | "closed_time"
    half_closed: bool = False
    exit_time: Optional[str] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None  # "tp1" | "tp2" | "sl" | "time"
    r_realized: Optional[float] = None  # weighted by partial fills

    def risk_distance(self) -> float:
        return abs(self.entry_price - self.sl)


def _ensure_log_dir() -> None:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)


def _append(rec: dict) -> None:
    _ensure_log_dir()
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


# ── Signal evaluation ────────────────────────────────────────────────────────

def evaluate_signal(
    forecasts: dict,
    regime: str,
    bar_time: datetime,
    bar_price: float,
    bar_atr: float,
) -> Optional[Position]:
    """Apply entry rules. Returns a new Position if a signal fires, else None."""
    fr_1h = forecasts.get("1h")
    if fr_1h is None or fr_1h.mode != "numeric":
        return None

    prob_up = float(fr_1h.value)
    prob_down = 1.0 - prob_up

    direction: Optional[str] = None
    reason = ""

    if prob_down >= _ENTRY_THRESHOLD and regime in {"MARKDOWN", "RANGE"}:
        direction = "short"
        reason = f"1h numeric prob_down={prob_down:.2f} in {regime}"
    elif prob_up >= _ENTRY_THRESHOLD and regime in {"MARKUP", "RANGE"}:
        direction = "long"
        reason = f"1h numeric prob_up={prob_up:.2f} in {regime}"

    if direction is None:
        return None

    risk = _SL_ATR_MULT * bar_atr
    if direction == "long":
        sl  = bar_price - risk
        tp1 = bar_price + _TP1_R * risk
        tp2 = bar_price + _TP2_R * risk
    else:
        sl  = bar_price + risk
        tp1 = bar_price - _TP1_R * risk
        tp2 = bar_price - _TP2_R * risk

    ttl = bar_time + _TTL_BY_SIGNAL["1h"]
    return Position(
        position_id=f"{bar_time.strftime('%Y%m%dT%H%M%S')}_{direction}",
        direction=direction,
        entry_time=bar_time.isoformat(),
        entry_price=bar_price,
        sl=sl, tp1=tp1, tp2=tp2,
        atr=bar_atr,
        signal_source=reason,
        ttl_iso=ttl.isoformat(),
    )


# ── Position lifecycle ───────────────────────────────────────────────────────

def update_position(pos: Position, bar_time: datetime, bar_high: float, bar_low: float) -> Position:
    """Step a position forward through one bar. Returns updated Position.

    Order of resolution within a single bar (deterministic):
      1. SL hit (worst case for trader)
      2. TP2 hit (best case)
      3. TP1 hit (partial)
      4. Time exit
    """
    if pos.status in {"closed_sl", "closed_tp2", "closed_time"}:
        return pos

    ttl = datetime.fromisoformat(pos.ttl_iso)
    risk = pos.risk_distance()

    if pos.direction == "long":
        sl_hit = bar_low <= pos.sl
        tp1_hit = bar_high >= pos.tp1
        tp2_hit = bar_high >= pos.tp2
    else:  # short
        sl_hit = bar_high >= pos.sl
        tp1_hit = bar_low <= pos.tp1
        tp2_hit = bar_low <= pos.tp2

    if sl_hit:
        pos.status = "closed_sl"
        pos.exit_time = bar_time.isoformat()
        pos.exit_price = pos.sl
        pos.exit_reason = "sl"
        # If half closed at TP1, only second half loses
        if pos.half_closed:
            pos.r_realized = 0.5 * _TP1_R + 0.5 * (-1.0)
        else:
            pos.r_realized = -1.0
        return pos

    if tp2_hit:
        pos.status = "closed_tp2"
        pos.exit_time = bar_time.isoformat()
        pos.exit_price = pos.tp2
        pos.exit_reason = "tp2"
        if pos.half_closed:
            pos.r_realized = 0.5 * _TP1_R + 0.5 * _TP2_R
        else:
            # If TP1 wasn't recorded as half-close prior, treat as full TP2 hit
            pos.r_realized = _TP2_R
        return pos

    if tp1_hit and not pos.half_closed:
        pos.half_closed = True
        pos.status = "tp1_hit"
        # Don't close fully; TP2 or SL still active for second half

    if bar_time >= ttl:
        pos.status = "closed_time"
        pos.exit_time = bar_time.isoformat()
        # Time exit: assume mid of bar as estimate (simple deterministic)
        pos.exit_price = (bar_high + bar_low) / 2.0
        pos.exit_reason = "time"
        # Compute realized R from exit_price
        if pos.direction == "long":
            move = pos.exit_price - pos.entry_price
        else:
            move = pos.entry_price - pos.exit_price
        unrealized_r = move / risk
        if pos.half_closed:
            pos.r_realized = 0.5 * _TP1_R + 0.5 * unrealized_r
        else:
            pos.r_realized = unrealized_r
        return pos

    return pos


# ── Storage and stats ────────────────────────────────────────────────────────

class VirtualTrader:
    """Stateful trader. One open position max. Persists log to JSONL."""

    def __init__(self) -> None:
        self.open_pos: Optional[Position] = None
        self._restore()

    def _restore(self) -> None:
        rows = _read_all()
        for r in reversed(rows):
            if r.get("status") not in {"closed_sl", "closed_tp2", "closed_time"}:
                # Resurrect open
                self.open_pos = Position(**{k: v for k, v in r.items() if k in Position.__dataclass_fields__})
                break

    def evaluate_and_open(self, forecasts, regime, bar_time, bar_price, bar_atr) -> Optional[Position]:
        if self.open_pos is not None:
            return None
        pos = evaluate_signal(forecasts, regime, bar_time, bar_price, bar_atr)
        if pos is not None:
            self.open_pos = pos
            _append(asdict(pos))
        return pos

    def step(self, bar_time, bar_high, bar_low) -> Optional[Position]:
        if self.open_pos is None:
            return None
        updated = update_position(self.open_pos, bar_time, bar_high, bar_low)
        if updated.status in {"closed_sl", "closed_tp2", "closed_time"}:
            _append(asdict(updated))
            self.open_pos = None
        else:
            self.open_pos = updated
        return updated

    def stats(self, window_days: int = 7, now: Optional[datetime] = None) -> dict:
        now = now or datetime.now(timezone.utc)
        cutoff = now - timedelta(days=window_days)
        rows = _read_all()
        # Group: latest record per position_id
        latest: dict[str, dict] = {}
        for r in rows:
            pid = r.get("position_id")
            if pid:
                latest[pid] = r
        wins = losses = open_n = 0
        rr_realized = []
        for r in latest.values():
            entry_time = datetime.fromisoformat(r["entry_time"])
            if entry_time < cutoff:
                continue
            status = r.get("status")
            r_real = r.get("r_realized")
            if status == "open" or status == "tp1_hit":
                open_n += 1
            elif r_real is not None:
                if r_real > 0:
                    wins += 1
                else:
                    losses += 1
                rr_realized.append(r_real)
        avg_rr = sum(rr_realized) / len(rr_realized) if rr_realized else 0.0
        signals = wins + losses + open_n
        return {
            "signals": signals,
            "wins": wins,
            "losses": losses,
            "open": open_n,
            "avg_rr": round(avg_rr, 2),
        }
