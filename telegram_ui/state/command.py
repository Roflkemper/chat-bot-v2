"""Telegram /state command handler."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
STATE_JSON = ROOT / "docs" / "STATE" / "state_latest.json"
SNAPSHOT_SCRIPT = ROOT / "scripts" / "state_snapshot.py"
STALE_THRESHOLD_MIN = 15
REFRESH_TIMEOUT_SEC = 25


def _age_minutes(path: Path) -> float:
    if not path.exists():
        return 999.0
    return (time.time() - path.stat().st_mtime) / 60


def _load_state() -> dict | None:
    if not STATE_JSON.exists():
        return None
    try:
        return json.loads(STATE_JSON.read_text(encoding="utf-8"))
    except Exception:
        return None


def _refresh_snapshot() -> bool:
    try:
        result = subprocess.run(
            [sys.executable, str(SNAPSHOT_SCRIPT), "--no-api"],
            timeout=REFRESH_TIMEOUT_SEC,
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        )
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        return False
    except Exception:
        return False


def _fmt(v: object, digits: int = 2) -> str:
    if v is None:
        return "N/A"
    try:
        return format(float(v), f".{digits}f")
    except (TypeError, ValueError):
        return "N/A"


def handle_state_command() -> str:
    age = _age_minutes(STATE_JSON)
    refreshed = False

    if age > STALE_THRESHOLD_MIN:
        refreshed = _refresh_snapshot()
        age = _age_minutes(STATE_JSON)

    state = _load_state()
    if state is None:
        return "❌ State unavailable: state_latest.json not found and snapshot failed."

    ts_str = state.get("ts", "")
    try:
        ts_local = datetime.fromisoformat(ts_str).astimezone().strftime("%H:%M")
    except Exception:
        ts_local = ts_str[:16]

    age_int = int(age)
    age_icon = "✅" if age_int < 5 else ("⚠️" if age_int < 30 else "🔴")

    ex = state.get("exposure") or {}
    net = ex.get("net_btc")
    shorts = ex.get("shorts_btc")
    longs = ex.get("longs_btc")
    sl = ex.get("nearest_short_liq") or {}
    ll = ex.get("nearest_long_liq") or {}

    sl_price = sl.get("price")
    sl_pct = sl.get("distance_pct")
    ll_price = ll.get("price")
    ll_pct = ll.get("distance_pct")

    agm_24h = state.get("agm_24h") or []
    tighten_total = sum(a.get("tighten_count", 0) for a in agm_24h)
    release_total = sum(a.get("release_count", 0) for a in agm_24h)

    anomalies = state.get("anomalies") or []
    anom_str = f"\n⚠️ Аномалии: {len(anomalies)}" if anomalies else ""

    sl_str = f"${int(sl_price):,}" if sl_price else "N/A"
    if sl_pct is not None:
        sl_str += f" (+{sl_pct}%)"
    ll_str = f"${int(ll_price):,}" if ll_price else "N/A"
    if ll_pct is not None:
        ll_str += f" ({ll_pct}%)"

    net_str = _fmt(net, 4) + " BTC" if net is not None else "N/A"
    notional = ex.get("net_notional_usd")
    if notional is not None:
        net_str += f" (${int(notional):,})"

    lines = [
        f"📊 State @ {ts_local}",
        "",
        f"Net: {net_str}",
        f"Shorts: {_fmt(shorts, 4)} BTC | Longs: {_fmt(longs, 4)} BTC",
        "",
        "⚠️ Nearest liq:",
        f"  Shorts: {sl_str}",
        f"  Longs:  {ll_str}",
        "",
        f"AGM 24h: {tighten_total} Tighten, {release_total} Release",
        f"Snapshot age: {age_int} min {age_icon}",
    ]
    if anom_str:
        lines.append(anom_str)

    return "\n".join(lines)
