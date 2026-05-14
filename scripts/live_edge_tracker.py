"""Live edge tracker — weekly comparison of live emits vs backtest expected.

Reads:
  - state/setups.jsonl (all setup emits)
  - state/p15_state.json (P-15 paper positions)
  - state/grid_coordinator_journal.jsonl (GC alerts)
  - state/setup_outcomes.jsonl (paper trade outcomes)

Computes for last 7 days:
  - Per-detector emit count
  - Per-detector outcome ratio (TP1/SL/expire)
  - GC alert counts (up/down score≥3 vs ≥4)
  - P-15 cumulative paper PnL

Compares to backtest expected:
  - mega-pair: ~25 triggers / 90d → ~2/week expected
  - GC: ~150 alerts / 90d at score≥3 → ~12/week
  - 15m intraday: ~89 score≥4 / year → ~1.7/week
  - P-15: $1k base × ~1.5% / week (from $58k/2y adaptive) → ~$15/week per layer

If live is dramatically worse than backtest (>50% drop), alert via TG.

Run: python scripts/live_edge_tracker.py
Cron: weekly, e.g. Mon 12:00 UTC
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

WINDOW_DAYS = 7

SETUPS = ROOT / "state" / "setups.jsonl"
P15_STATE = ROOT / "state" / "p15_state.json"
GC_JOURNAL = ROOT / "state" / "grid_coordinator_fires.jsonl"
OUTCOMES = ROOT / "state" / "setup_outcomes.jsonl"
PAPER_TRADES = ROOT / "state" / "paper_trades.jsonl"

# Backtest expectations per week (calibrated from 365/815-day backtests)
# P-15 per-pair: 2y backtest showed BTC 2401 long emits, BTC 2498 short,
# ETH 2816 long, ETH 2368 short, XRP 3296 long, XRP 2834 short. That's
# average ~5-7/day per (pair, dir) at 1h-bar granularity, BUT each
# OPEN is gated by trend_gate flip (rare), so live emits are 1-3/week.
EXPECTED_WEEKLY = {
    "mega_long_dump_bounce_emits": 2.5,    # 115/365×7
    "gc_up_score_3plus": 7.0,              # ~365 up-signals / 365×7
    "gc_down_score_3plus": 7.0,            # ~365 down-signals / 365×7
    "intraday_score_4plus": 1.7,           # 89/365×7
    # P-15 OPEN events per pair × direction (rough estimate based on
    # historical trend-gate flip frequency: ~1-2 per week per leg).
    "p15_BTCUSDT_long_open_emits": 1.5,
    "p15_BTCUSDT_short_open_emits": 1.5,
    "p15_ETHUSDT_long_open_emits": 1.5,
    "p15_ETHUSDT_short_open_emits": 1.5,
    "p15_XRPUSDT_long_open_emits": 1.5,
    "p15_XRPUSDT_short_open_emits": 1.5,
}


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists(): return []
    out = []
    try:
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line: continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return out


def _within_window(ts_str: str, cutoff: datetime) -> bool:
    if not ts_str: return False
    try:
        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        if ts.tzinfo is None: ts = ts.replace(tzinfo=timezone.utc)
        return ts >= cutoff
    except (ValueError, AttributeError):
        return False


def main() -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)
    print(f"[edge-tracker] window: last {WINDOW_DAYS} days (since {cutoff.isoformat(timespec='minutes')})")

    # Setups
    setups = _read_jsonl(SETUPS)
    recent_setups = [s for s in setups if _within_window(s.get("detected_at", ""), cutoff)]
    setup_counts = Counter(s.get("setup_type", "?") for s in recent_setups)

    # GC journal
    gc_events = _read_jsonl(GC_JOURNAL)
    recent_gc = [g for g in gc_events if _within_window(g.get("ts", ""), cutoff)]
    gc_up_3 = sum(1 for g in recent_gc if g.get("direction") == "up" and (g.get("score") or 0) >= 3)
    gc_down_3 = sum(1 for g in recent_gc if g.get("direction") == "down" and (g.get("score") or 0) >= 3)
    gc_up_4 = sum(1 for g in recent_gc if g.get("direction") == "up" and (g.get("score") or 0) >= 4)
    gc_down_4 = sum(1 for g in recent_gc if g.get("direction") == "down" and (g.get("score") or 0) >= 4)

    # Outcomes (TP1/SL hits per setup_type)
    outcomes = _read_jsonl(OUTCOMES)
    recent_outcomes = [o for o in outcomes if _within_window(o.get("ts", ""), cutoff)]
    outcome_summary = Counter()
    for o in recent_outcomes:
        outcome_summary[(o.get("setup_type", "?"), o.get("outcome", "?"))] += 1

    # P-15 paper PnL
    paper = _read_jsonl(PAPER_TRADES)
    recent_paper = [t for t in paper if _within_window(t.get("opened_at", t.get("ts", "")), cutoff)]
    p15_pnl_usd = 0.0
    p15_n_trades = 0
    for t in recent_paper:
        st = t.get("setup_type", "")
        if "p15" in st:
            p15_n_trades += 1
            p15_pnl_usd += float(t.get("realized_pnl_usd", 0) or 0)

    # P-15 per (pair, direction) counts — read pair from emitted setup.
    p15_per_pair = Counter()
    for s in recent_setups:
        st = s.get("setup_type", "")
        if st in ("p15_long_open", "p15_short_open"):
            direction = "long" if st == "p15_long_open" else "short"
            pair = s.get("pair", "BTCUSDT")
            p15_per_pair[f"p15_{pair}_{direction}_open_emits"] += 1

    # Comparison
    actual = {
        "mega_long_dump_bounce_emits": setup_counts.get("long_mega_dump_bounce", 0),
        "gc_up_score_3plus": gc_up_3,
        "gc_down_score_3plus": gc_down_3,
        "intraday_score_4plus": gc_up_4 + gc_down_4,  # rough proxy
        **{k: p15_per_pair.get(k, 0) for k in EXPECTED_WEEKLY if k.startswith("p15_")},
    }

    rows = []
    alerts = []
    for k, expected in EXPECTED_WEEKLY.items():
        live = actual.get(k, 0)
        ratio = (live / expected) if expected > 0 else 0
        status = "OK"
        if expected >= 1 and live == 0:
            status = "ZERO"
            alerts.append(f"{k}: 0 live vs {expected} expected")
        elif ratio < 0.4:
            status = "LOW"
            alerts.append(f"{k}: {live} vs {expected:.1f} expected ({ratio*100:.0f}% of expected)")
        elif ratio > 2.5:
            status = "HIGH"  # not always bad — could be noise
        rows.append({
            "metric": k,
            "live_7d": live,
            "expected_7d": round(expected, 1),
            "ratio": round(ratio, 2),
            "status": status,
        })

    # Print summary
    print("\n=== Live edge tracker ===")
    for r in rows:
        print(f"  {r['metric']:35s}  live={r['live_7d']:5}  exp={r['expected_7d']:5}  "
              f"ratio={r['ratio']:.2f}  {r['status']}")
    print(f"\n  P-15 paper trades closed in window: {p15_n_trades}")
    print(f"  P-15 paper PnL realized: ${p15_pnl_usd:.0f}")
    print(f"  GC up score>=4: {gc_up_4} / down>=4: {gc_down_4}")
    print(f"  Total setups emitted: {len(recent_setups)}")
    print(f"  Total outcomes recorded: {len(recent_outcomes)}")

    # TG alert if any LOW/ZERO
    if alerts:
        print(f"\n[WARN] {len(alerts)} edge-degradation alerts:")
        for a in alerts: print(f"  - {a}")
        msg = (f"[WARN] Edge tracker {WINDOW_DAYS}d alert ({len(alerts)} issues):\n" +
               "\n".join(f"• {a}" for a in alerts) +
               f"\n\nP-15 paper: {p15_n_trades} trades, ${p15_pnl_usd:.0f} realized\n" +
               f"Total setups: {len(recent_setups)}, GC down>=4: {gc_down_4}")
        try:
            import requests
            from config import BOT_TOKEN, CHAT_ID
            chat_ids = [p.strip() for p in str(CHAT_ID or "").replace(";", ",").split(",") if p.strip()]
            for cid in chat_ids:
                try:
                    requests.post(
                        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                        json={"chat_id": cid, "text": msg}, timeout=10,
                    )
                except Exception: pass
        except Exception: pass
    else:
        print("\n✅ All metrics within expected range.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
