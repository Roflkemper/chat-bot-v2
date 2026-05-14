"""CLI tool: pretty-print last N decisions from manual_decisions.jsonl.

Usage:
    python tools/decision_dump.py          # last 5
    python tools/decision_dump.py 10       # last 10
    python tools/decision_dump.py 1 --full # full JSON of last 1 decision
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from services.decision_command import load_recent_decisions


def _fmt_record(r: dict, full: bool = False) -> str:
    if full:
        return json.dumps(r, ensure_ascii=False, indent=2, default=str)

    lines = []
    ts = (r.get("ts") or "")[:16].replace("T", " ")
    action = r.get("action") or "?"
    schema = r.get("schema_version", "v1")
    lines.append(f"[{ts}]  {action}  (schema={schema})")

    price_btc = r.get("price_btc") or (r.get("market") or {}).get("price_btc")
    session = r.get("session_active") or (r.get("market") or {}).get("session_active") or "—"
    if price_btc:
        lines.append(f"  BTC {price_btc:,.0f}  Session: {session}")

    market = r.get("market") or {}
    rsi = market.get("rsi_1h")
    roc4 = market.get("roc_4h_pct")
    roc24 = market.get("roc_24h_pct")
    if rsi is not None:
        rsi_str = f"  RSI: {rsi:.1f}"
        if roc4 is not None:
            sign = "+" if roc4 >= 0 else ""
            rsi_str += f"  ROC4h: {sign}{roc4:.2f}%"
        if roc24 is not None:
            sign = "+" if roc24 >= 0 else ""
            rsi_str += f"  ROC24h: {sign}{roc24:.2f}%"
        lines.append(rsi_str)

    ict = r.get("ict_levels") or {}
    ict_fields = [
        ("PDH", "dist_to_pdh_pct"), ("PDL", "dist_to_pdl_pct"),
        ("FVG_H", "dist_to_nearest_unmitigated_high_pct"),
        ("FVG_L", "dist_to_nearest_unmitigated_low_pct"),
    ]
    ict_parts = []
    for label, key in ict_fields:
        v = ict.get(key)
        if v is not None:
            sign = "+" if v >= 0 else ""
            ict_parts.append(f"{label} {sign}{v:.2f}%")
    if ict_parts:
        lines.append("  ICT: " + "  ".join(ict_parts))

    bots_detail = r.get("bots_detail") or []
    active = [b for b in bots_detail if b.get("side") not in ("flat", "unknown", None)]
    for b in active:
        alias = b.get("alias") or b.get("id") or "?"
        side = (b.get("side") or "?").upper()
        dist = b.get("distance_to_liq_pct")
        upl = b.get("unrealized_pnl")
        bot_str = f"  {alias} {side}"
        if dist is not None:
            bot_str += f"  liq {dist:.1f}% away"
        if upl is not None:
            sign = "+" if upl >= 0 else ""
            bot_str += f"  UPL {sign}{upl:,.2f}"
        lines.append(bot_str)

    ra = r.get("recent_action") or {}
    hh = ra.get("consec_hourly_higher_highs", 0)
    ll = ra.get("consec_hourly_lower_lows", 0)
    displ = ra.get("displacement_bar_detected", False)
    if hh or ll or displ:
        ra_parts = []
        if hh:
            ra_parts.append(f"HH×{hh}")
        if ll:
            ra_parts.append(f"LL×{ll}")
        if displ:
            ra_parts.append("DISPLACEMENT")
        lines.append("  Action: " + " | ".join(ra_parts))

    notes = r.get("notes") or ""
    if notes:
        short = notes[:100] + ("..." if len(notes) > 100 else "")
        lines.append(f"  Notes: {short}")

    return "\n".join(lines)


def main() -> None:
    args = sys.argv[1:]
    full = "--full" in args
    args = [a for a in args if not a.startswith("--")]
    n = int(args[0]) if args else 5

    records = load_recent_decisions(n)
    if not records:
        print("No decisions recorded yet.")
        return

    print(f"=== Last {len(records)} decision(s) ===\n")
    for r in reversed(records):
        print(_fmt_record(r, full=full))
        print()


if __name__ == "__main__":
    main()
