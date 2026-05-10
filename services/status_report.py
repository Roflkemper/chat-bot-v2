"""On-demand /status report for Telegram.

Aggregates:
  - heartbeat freshness (age since last heartbeat.tick in logs)
  - process pids (app_runner, tracker, collectors, state_snapshot)
  - last emitted setup (type, pair, age)
  - last GC fire (direction, score, age)
  - P-15 open legs per (pair, direction) with layers/DD/age
  - restarts last hour count
  - top emit_type last 24h

Designed for /status TG command — readable in ~15 lines.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_APP_LOG = _ROOT / "logs" / "app.log"
_SETUPS = _ROOT / "state" / "setups.jsonl"
_GC_FIRES = _ROOT / "state" / "grid_coordinator_fires.jsonl"
_P15_STATE = _ROOT / "state" / "p15_state.json"
_APP_RUNNER_STARTS = _ROOT / "state" / "app_runner_starts.jsonl"


def _read_last_lines(path: Path, n: int = 50) -> list[str]:
    """Tail-style read of last n lines without loading whole file."""
    if not path.exists():
        return []
    try:
        size = path.stat().st_size
        with path.open("rb") as f:
            # Read last ~64KB and split lines.
            offset = max(0, size - 65536)
            f.seek(offset)
            chunk = f.read()
        lines = chunk.decode("utf-8", errors="ignore").splitlines()
        return lines[-n:]
    except OSError:
        return []


def _parse_iso(s: str) -> datetime | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _age_minutes(dt: datetime | None, now: datetime) -> float | None:
    if dt is None:
        return None
    return (now - dt).total_seconds() / 60


def _heartbeat_age(now: datetime) -> tuple[float | None, str | None]:
    """Find last 'heartbeat.tick' line in app.log; return (age_min, raw_ts_str)."""
    if not _APP_LOG.exists():
        return None, None
    try:
        # Last 200 lines is usually enough — heartbeat every 60s.
        lines = _read_last_lines(_APP_LOG, n=200)
        for line in reversed(lines):
            if "heartbeat.tick" not in line:
                continue
            # Format: "2026-05-10 23:30:54,647 | INFO | ..."
            ts_match = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
            if ts_match:
                # Local time → convert to UTC by reading the embedded t=
                t_match = re.search(r"t=([\d\-T:+Z]+)", line)
                if t_match:
                    dt = _parse_iso(t_match.group(1))
                    if dt:
                        return _age_minutes(dt, now), t_match.group(1)
                return None, ts_match.group(1)
        return None, None
    except OSError:
        return None, None


def _processes_status() -> dict[str, int | None]:
    try:
        import psutil
    except ImportError:
        return {"app_runner": None, "tracker": None, "collectors": None, "state_snapshot": None}
    out = {"app_runner": None, "tracker": None, "collectors": None, "state_snapshot": None}
    needles = {
        "app_runner": "app_runner.py",
        "tracker": "ginarea_tracker",
        "collectors": "market_collector.collector",
        "state_snapshot": "state_snapshot_loop.py",
    }
    for proc in psutil.process_iter(["pid", "cmdline", "name"]):
        try:
            cl = " ".join(proc.info.get("cmdline") or [])
            for key, needle in needles.items():
                if out[key] is None and needle in cl and ".venv" in cl:
                    out[key] = proc.info["pid"]
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return out


def _last_setup(now: datetime) -> dict | None:
    if not _SETUPS.exists():
        return None
    last_line = None
    try:
        lines = _read_last_lines(_SETUPS, n=5)
        for line in reversed(lines):
            line = line.strip()
            if line:
                last_line = line
                break
        if last_line is None:
            return None
        rec = json.loads(last_line)
        dt = _parse_iso(rec.get("detected_at", ""))
        return {
            "type": rec.get("setup_type", "?"),
            "pair": rec.get("pair", "?"),
            "age_min": _age_minutes(dt, now),
            "strength": rec.get("strength"),
            "conf": rec.get("confidence_pct"),
        }
    except (OSError, json.JSONDecodeError):
        return None


def _last_gc_fire(now: datetime) -> dict | None:
    if not _GC_FIRES.exists():
        return None
    try:
        lines = _read_last_lines(_GC_FIRES, n=5)
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            dt = _parse_iso(rec.get("ts", ""))
            return {
                "direction": rec.get("direction"),
                "score": rec.get("score"),
                "age_min": _age_minutes(dt, now),
            }
        return None
    except (OSError, json.JSONDecodeError):
        return None


def _p15_legs(now: datetime) -> list[dict]:
    if not _P15_STATE.exists():
        return []
    try:
        raw = json.loads(_P15_STATE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    out = []
    for key, leg in raw.items():
        if not isinstance(leg, dict):
            continue
        if not leg.get("in_pos"):
            continue
        try:
            pair, direction = key.split(":", 1)
        except ValueError:
            continue
        opened_at = _parse_iso(leg.get("opened_at_ts", ""))
        out.append({
            "key": key,
            "pair": pair,
            "direction": direction,
            "layers": int(leg.get("layers", 0)),
            "size_usd": float(leg.get("total_size_usd", 0)),
            "dd_pct": float(leg.get("cum_dd_pct", 0)),
            "age_min": _age_minutes(opened_at, now),
        })
    return out


def _restarts_last_hour(now: datetime) -> int:
    if not _APP_RUNNER_STARTS.exists():
        return 0
    cutoff = now - timedelta(hours=1)
    n = 0
    try:
        with _APP_RUNNER_STARTS.open(encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                dt = _parse_iso(rec.get("ts", ""))
                if dt and dt >= cutoff:
                    n += 1
        return n
    except OSError:
        return 0


def build_status_report() -> str:
    now = datetime.now(timezone.utc)
    hb_age, hb_ts = _heartbeat_age(now)
    procs = _processes_status()
    last_setup = _last_setup(now)
    last_gc = _last_gc_fire(now)
    legs = _p15_legs(now)
    restarts = _restarts_last_hour(now)

    lines = [f"[STATUS] {now:%Y-%m-%d %H:%M UTC}", ""]

    # Heartbeat
    if hb_age is not None:
        emoji = "[OK]" if hb_age < 5 else ("[WARN]" if hb_age < 15 else "[STALE]")
        lines.append(f"Heartbeat: {emoji} age {hb_age:.1f}min  last={hb_ts}")
    else:
        lines.append("Heartbeat: [UNKNOWN] no recent ticks in app.log")

    # Processes
    proc_parts = []
    for name, pid in procs.items():
        proc_parts.append(f"{name}={pid if pid else 'DOWN'}")
    lines.append("Procs: " + " | ".join(proc_parts))
    lines.append(f"Restarts last 1h: {restarts}")
    lines.append("")

    # Last setup
    if last_setup:
        lines.append(
            f"Last setup: {last_setup['type']} {last_setup['pair']}  "
            f"age {last_setup['age_min']:.0f}min  "
            f"s{last_setup['strength']}/c{last_setup['conf']:.0f}%"
        )
    else:
        lines.append("Last setup: (none)")

    # Last GC fire
    if last_gc:
        lines.append(
            f"Last GC fire: {last_gc['direction']} score={last_gc['score']}  "
            f"age {last_gc['age_min']:.0f}min"
        )
    else:
        lines.append("Last GC fire: (none yet)")
    lines.append("")

    # P-15 open legs
    if legs:
        lines.append(f"P-15 open legs ({len(legs)}):")
        for leg in legs:
            lines.append(
                f"  {leg['pair']} {leg['direction']:>5}  "
                f"layers={leg['layers']}  ${leg['size_usd']:.0f}  "
                f"DD={leg['dd_pct']:.2f}%  age={leg['age_min']:.0f}min"
            )
    else:
        lines.append("P-15 open legs: 0 (all idle)")

    return "\n".join(lines)
