"""Read-only summary of GinArea bot states for /ginarea TG command.

Pulls the latest row per bot from ginarea_live/snapshots.csv and renders
a compact text card. Does NOT call any GinArea API — only reads the
tracker output.

Status codes (column `status` in snapshots.csv):
  1 = active and trading
  2 = trading but at a loss
  3 = paused / awaiting condition
  0 = stopped

Fields shown per bot:
  alias, status emoji, position BTC, current profit %, drawdown,
  average entry price, distance to liquidation %.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parents[1]
_SNAPSHOTS = _ROOT / "ginarea_live" / "snapshots.csv"

_STATUS_EMOJI = {
    "1": "[OK]",
    "2": "[DOWN]",
    "3": "[PAUSE]",
    "0": "[STOP]",
}


def _latest_snapshot_per_bot() -> list[dict]:
    """Reads the entire CSV and returns the last row for each bot_id.

    The file is large (~350k rows). We walk once and overwrite an in-memory
    dict on each row, ending with the latest snapshot per bot.
    """
    if not _SNAPSHOTS.exists():
        return []
    latest: dict[str, dict] = {}
    try:
        with _SNAPSHOTS.open(encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                bid = row.get("bot_id") or ""
                if not bid:
                    continue
                latest[bid] = row
    except OSError:
        return []
    return list(latest.values())


def _safe_float(v) -> Optional[float]:
    try:
        return float(v) if v not in (None, "", "nan") else None
    except (TypeError, ValueError):
        return None


def _format_row(row: dict, current_btc_price: Optional[float] = None) -> str:
    alias = (row.get("alias") or "?").strip()
    status = str(row.get("status") or "?").split(".")[0]
    emoji = _STATUS_EMOJI.get(status, f"[{status}]")
    pos = _safe_float(row.get("position"))
    # current_profit in snapshots.csv is unrealized USD (verified
    # against adaptive_grid_manager comments). NOT a percentage.
    unrealized_usd = _safe_float(row.get("current_profit"))
    avg = _safe_float(row.get("average_price"))
    liq = _safe_float(row.get("liquidation_price"))

    parts = [f"{emoji} {alias:<14}"]
    if pos is not None:
        parts.append(f"pos={pos:+.4f}BTC")
    if unrealized_usd is not None:
        parts.append(f"unrz=${unrealized_usd:+,.0f}")
    if avg is not None and avg > 0:
        parts.append(f"avg=${avg:,.0f}")
    if liq is not None and liq > 0 and current_btc_price:
        dist_pct = abs(liq - current_btc_price) / current_btc_price * 100
        parts.append(f"liq=${liq:,.0f}({dist_pct:.1f}%)")

    return "  ".join(parts)


def _current_btc_price() -> Optional[float]:
    """Best-effort: read latest 1m close from market_live."""
    p = _ROOT / "market_live" / "market_1m.csv"
    if not p.exists():
        return None
    try:
        with p.open(encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) < 2:
            return None
        # CSV with header: ts_utc,open,high,low,close,volume
        last = lines[-1].strip().split(",")
        return float(last[4])
    except (OSError, ValueError, IndexError):
        return None


def build_ginarea_report() -> str:
    """Renders /ginarea text card."""
    now = datetime.now(timezone.utc)
    rows = _latest_snapshot_per_bot()
    btc_price = _current_btc_price()

    lines = [f"[GINAREA] {now:%Y-%m-%d %H:%M UTC}"]
    if btc_price:
        lines.append(f"BTC ${btc_price:,.0f}")
    lines.append("")

    if not rows:
        lines.append("No bot snapshots available — tracker may be down.")
        return "\n".join(lines)

    # Sort: active first, then by alias
    def sort_key(r):
        status = str(r.get("status") or "9")
        s = status.split(".")[0]
        order = {"1": 0, "2": 1, "3": 2, "0": 3}.get(s, 9)
        return (order, r.get("alias") or "")

    rows.sort(key=sort_key)
    n_active = sum(1 for r in rows if str(r.get("status") or "").startswith("1"))
    n_drawdown = sum(1 for r in rows if str(r.get("status") or "").startswith("2"))
    n_paused = sum(1 for r in rows if str(r.get("status") or "").startswith("3"))

    lines.append(f"Bots: {len(rows)} total — active={n_active} dd={n_drawdown} paused={n_paused}")
    lines.append("")

    for row in rows[:20]:  # cap to 20
        lines.append(_format_row(row, btc_price))

    # Total position + profit summary
    total_pos = sum(_safe_float(r.get("position")) or 0 for r in rows)
    total_unrz_usd = sum(_safe_float(r.get("current_profit")) or 0 for r in rows)

    lines.append("")
    lines.append(f"Total net position: {total_pos:+.4f} BTC")
    lines.append(f"Total unrealized PnL: ${total_unrz_usd:+,.2f}")

    return "\n".join(lines)
