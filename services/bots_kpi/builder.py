"""Build KPI table from GinArea snapshots."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SNAP_PATH = ROOT / "ginarea_live" / "snapshots.csv"
ALIASES_PATH = ROOT / "ginarea_tracker" / "bot_aliases.json"


def _load_aliases() -> dict[str, str]:
    if not ALIASES_PATH.exists():
        return {}
    try:
        return json.loads(ALIASES_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _trim_name(name: str, max_len: int = 18) -> str:
    s = str(name).strip()
    return s if len(s) <= max_len else s[: max_len - 1] + "…"


def _per_bot_kpi(bot_snaps: pd.DataFrame) -> dict | None:
    """Compute KPIs for one bot's snapshot rows."""
    if bot_snaps.empty or len(bot_snaps) < 2:
        return None
    first = bot_snaps.iloc[0]
    last = bot_snaps.iloc[-1]
    realized = float(last["profit"]) - float(first["profit"])
    unrealized = float(last["current_profit"])  # latest mark-to-market
    in_count = int(float(last["in_filled_count"]) - float(first["in_filled_count"]))
    out_count = int(float(last["out_filled_count"]) - float(first["out_filled_count"]))
    vol = float(last["trade_volume"]) - float(first["trade_volume"])
    days = (last["ts_utc"] - first["ts_utc"]).total_seconds() / 86400.0
    if days <= 0:
        return None
    prof_per_vol_pct = (realized / vol * 100) if vol > 0 else 0.0
    realized_per_day = realized / days
    return {
        "vol": round(vol, 0),
        "realized": round(realized, 2),
        "unrealized": round(unrealized, 2),
        "in": in_count,
        "out": out_count,
        "prof_per_vol_pct": round(prof_per_vol_pct, 4),
        "per_day": round(realized_per_day, 2),
        "days": round(days, 2),
    }


def build_bots_kpi_report(window_days: float = 7.0) -> str:
    """Build a TG-ready text table of per-bot KPIs over `window_days`.

    Returns markdown-ish formatted text. On data error returns a short error
    message to display in TG (not raised).
    """
    if not SNAP_PATH.exists():
        try:
            shown = SNAP_PATH.relative_to(ROOT)
        except ValueError:
            shown = SNAP_PATH
        return f"❌ /bots_kpi: snapshots not found at {shown}"

    try:
        df = pd.read_csv(SNAP_PATH)
    except Exception as exc:  # noqa: BLE001
        return f"❌ /bots_kpi: read failed: {exc}"

    df["ts_utc"] = pd.to_datetime(df["ts_utc"], utc=True, errors="coerce")
    df = df.dropna(subset=["ts_utc"])
    for col in ("profit", "current_profit", "in_filled_count",
                "out_filled_count", "trade_volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    df = df[df["ts_utc"] >= cutoff]
    if df.empty:
        return f"❌ /bots_kpi: no snapshots in last {window_days:g} day(s)"

    aliases = _load_aliases()
    # Group by bot_id; resolve display name
    rows: list[tuple[str, dict]] = []
    total_vol = 0.0
    total_realized = 0.0
    total_unreal = 0.0
    total_in = 0
    total_out = 0

    for bot_id, sub in df.groupby("bot_id"):
        sub = sub.sort_values("ts_utc")
        # alias from aliases.json (bot_id may be float-stringified)
        try:
            bid_str = str(int(float(bot_id)))
        except (TypeError, ValueError):
            bid_str = str(bot_id)
        alias = aliases.get(bid_str)
        if not alias:
            # try the alias column from the latest snapshot
            alias_col = str(sub.iloc[-1].get("alias") or "").strip()
            if alias_col and alias_col.lower() != "nan":
                alias = alias_col
        if not alias:
            # fall back to bot_name (cleaned of emoji, trimmed)
            raw_name = str(sub.iloc[-1].get("bot_name", "")).strip()
            # strip leading emoji + double-spaces for compactness
            cleaned = "".join(ch for ch in raw_name if ch.isalnum() or ch in " -_+%.")
            cleaned = " ".join(cleaned.split())
            alias = cleaned or f"id-{bid_str[-4:]}"
        display = alias
        kpi = _per_bot_kpi(sub)
        if kpi is None:
            continue
        rows.append((display, kpi))
        total_vol += kpi["vol"]
        total_realized += kpi["realized"]
        total_unreal += kpi["unrealized"]
        total_in += kpi["in"]
        total_out += kpi["out"]

    if not rows:
        return f"❌ /bots_kpi: no bots with usable data in last {window_days:g}d"

    # Filter out idle bots (no volume AND no IN/OUT in window)
    rows = [(n, k) for (n, k) in rows if k["vol"] > 0 or k["in"] > 0 or k["out"] > 0]
    if not rows:
        return f"❌ /bots_kpi: no active bots in last {window_days:g}d"

    # sort by realized DESC
    rows.sort(key=lambda r: -r[1]["realized"])
    sample_days = rows[0][1]["days"] if rows else window_days

    lines: list[str] = []
    lines.append(f"📊 /bots_kpi (последние {sample_days:.1f}d, {len(rows)} ботов)")
    lines.append("")
    lines.append("```")
    lines.append(f"{'bot':<14} {'vol$':>8} {'real$':>8} {'unrl$':>8} "
                 f"{'IN':>4} {'OUT':>4} {'pf/vol%':>7} {'$/d':>6}")
    lines.append("-" * 64)
    for name, k in rows:
        lines.append(f"{_trim_name(name, 14):<14} {k['vol']:>8.0f} "
                     f"{k['realized']:>+8.2f} {k['unrealized']:>+8.2f} "
                     f"{k['in']:>4} {k['out']:>4} "
                     f"{k['prof_per_vol_pct']:>7.4f} {k['per_day']:>+6.2f}")
    lines.append("-" * 64)
    pf_vol_total = (total_realized / total_vol * 100) if total_vol > 0 else 0.0
    per_day_total = total_realized / sample_days if sample_days > 0 else 0.0
    lines.append(f"{'TOTAL':<14} {total_vol:>8.0f} {total_realized:>+8.2f} "
                 f"{total_unreal:>+8.2f} {total_in:>4} {total_out:>4} "
                 f"{pf_vol_total:>7.4f} {per_day_total:>+6.2f}")
    lines.append("```")
    lines.append("")
    if total_unreal < -500:
        lines.append(f"⚠️ Mark-to-market: накопленная просадка {total_unreal:+.0f}$ — "
                     "реализованный профит может быть «съеден» при market-close.")
    return "\n".join(lines)
