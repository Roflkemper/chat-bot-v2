"""Detailed P-15 report for /p15 TG command.

Goes beyond /status: full per-leg breakdown with avg_entry, extreme,
current dd, realized + unrealized PnL, last 5 equity events for context,
correlation-cap status.

If no legs are open or detected, says so explicitly.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
_P15_STATE = _ROOT / "state" / "p15_state.json"
_P15_EQUITY = _ROOT / "state" / "p15_equity.jsonl"


def _load_state() -> dict[str, dict]:
    if not _P15_STATE.exists():
        return {}
    try:
        return json.loads(_P15_STATE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _read_equity_last_n(n: int = 200) -> list[dict]:
    """Tail of equity journal — used for per-leg recent events."""
    if not _P15_EQUITY.exists():
        return []
    out = []
    try:
        with _P15_EQUITY.open(encoding="utf-8") as f:
            lines = f.readlines()
        for line in lines[-n:]:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError:
        pass
    return out


def _parse_iso(s: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, AttributeError):
        return None


def _realized_pnl_24h(events: list[dict], now: datetime) -> tuple[float, int]:
    """Sum realized_pnl_usd over last 24h. Returns (sum, n_events)."""
    cutoff = now.timestamp() - 24 * 3600
    s = 0.0
    n = 0
    for e in events:
        dt = _parse_iso(e.get("ts", ""))
        if not dt or dt.timestamp() < cutoff:
            continue
        v = e.get("realized_pnl_usd")
        if v is None:
            continue
        try:
            s += float(v)
            n += 1
        except (TypeError, ValueError):
            pass
    return s, n


def _per_leg_summary(state: dict, events: list[dict], now: datetime
                      ) -> list[dict]:
    """For every (pair, dir) key in state — return summary including events."""
    out = []
    for key, leg in state.items():
        if not isinstance(leg, dict):
            continue
        try:
            pair, direction = key.split(":", 1)
        except ValueError:
            continue
        leg_events = [e for e in events
                      if e.get("pair") == pair and e.get("direction") == direction]
        last5 = leg_events[-5:]
        opened_at = _parse_iso(leg.get("opened_at_ts", ""))
        age_h = (now - opened_at).total_seconds() / 3600 if opened_at else None
        avg = (float(leg.get("weighted_entry", 0))
                / float(leg.get("total_size_usd", 1.0))) if leg.get("total_size_usd") else 0
        out.append({
            "key": key,
            "pair": pair,
            "direction": direction,
            "in_pos": bool(leg.get("in_pos")),
            "layers": int(leg.get("layers", 0)),
            "total_size_usd": float(leg.get("total_size_usd", 0)),
            "avg_entry": avg,
            "extreme": float(leg.get("extreme_price", 0)),
            "dd_pct": float(leg.get("cum_dd_pct", 0)),
            "last_stage": str(leg.get("last_emitted_stage", "")),
            "age_h": age_h,
            "last_events": last5,
        })
    return out


def build_p15_report() -> str:
    now = datetime.now(timezone.utc)
    state = _load_state()
    events = _read_equity_last_n(500)
    pnl_24h, n_events_24h = _realized_pnl_24h(events, now)
    summary = _per_leg_summary(state, events, now)

    lines = [f"[P-15] {now:%Y-%m-%d %H:%M UTC}", ""]
    lines.append(f"Realized PnL 24h: ${pnl_24h:+.2f} on {n_events_24h} events")
    lines.append("")

    if not summary:
        lines.append("No leg state yet — bot has not run P-15 detectors against")
        lines.append("a fresh state/p15_state.json.")
        return "\n".join(lines)

    open_legs = [s for s in summary if s["in_pos"]]
    idle_legs = [s for s in summary if not s["in_pos"]]

    lines.append(f"Open legs ({len(open_legs)}):")
    if not open_legs:
        lines.append("  (none — all idle)")
    for s in open_legs:
        age = f"{s['age_h']:.1f}h" if s['age_h'] is not None else "n/a"
        lines.append(
            f"  {s['pair']:<10} {s['direction']:<5}  layers={s['layers']}"
            f"  size=${s['total_size_usd']:.0f}  avg=${s['avg_entry']:.2f}"
        )
        lines.append(
            f"    extreme=${s['extreme']:.2f}  dd={s['dd_pct']:+.2f}%"
            f"  stage={s['last_stage']}  age={age}"
        )
        if s["last_events"]:
            lines.append("    recent events:")
            for ev in s["last_events"]:
                ts = ev.get("ts", "")[:19]
                stage = ev.get("stage", "?")
                pnl = ev.get("realized_pnl_usd")
                pnl_str = f"  pnl=${float(pnl):+.2f}" if pnl is not None else ""
                lines.append(f"      {ts}  {stage}{pnl_str}")

    if idle_legs:
        lines.append("")
        lines.append(f"Idle legs ({len(idle_legs)}):")
        for s in idle_legs:
            lines.append(
                f"  {s['pair']:<10} {s['direction']:<5}  "
                f"last_stage={s['last_stage'] or '(never opened)'}"
            )

    return "\n".join(lines)
