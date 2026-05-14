"""GC-confirmation block coverage check.

Reads state/gc_confirmation_audit.jsonl. For each "blocked" or "penalty"
decision, looks at price action over next 60-240 minutes to validate
the block was correct.

A block is CORRECT if price moved AGAINST the setup direction (= setup
would have lost money, GC saved us).
A block is WRONG if price moved IN setup direction (= setup would have
won, GC cost us money).

Output: stats per detector + recommendation:
  - If block_correct_rate >= 60%: GC filter is saving money — keep
  - If 40-60%: marginal, no harm
  - If <40%: GC filter is HURTING — relax HARD_BLOCK
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

AUDIT = ROOT / "state" / "gc_confirmation_audit.jsonl"
DATA_1M = ROOT / "backtests" / "frozen" / "BTCUSDT_1m_2y.csv"
DATA_LIVE = ROOT / "market_live" / "market_1m.csv"

HORIZONS_MIN = (60, 240)


def main() -> int:
    if not AUDIT.exists():
        print("[gc-cover] no audit file"); return 0

    records = []
    with AUDIT.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try:
                rec = json.loads(line)
                records.append(rec)
            except json.JSONDecodeError:
                continue
    if not records:
        print("[gc-cover] empty audit"); return 0
    print(f"[gc-cover] {len(records)} audit records")

    # Decisions of interest: "hard-block (...)" and "penalty -..."
    blocked = [r for r in records if "block" in str(r.get("decision", ""))]
    penalised = [r for r in records if "penalty" in str(r.get("decision", ""))]
    print(f"  blocked: {len(blocked)}, penalty: {len(penalised)}")

    # Load 1m prices for forward returns. Prefer live CSV (covers recent days),
    # fallback to frozen 2y CSV for older audit records.
    df_frozen = pd.read_csv(DATA_1M)
    df_frozen["ts_utc"] = pd.to_datetime(df_frozen["ts"], unit="ms", utc=True)
    frames = [df_frozen[["ts_utc", "close"]]]
    if DATA_LIVE.exists():
        df_live = pd.read_csv(DATA_LIVE)
        df_live["ts_utc"] = pd.to_datetime(df_live["ts_utc"], utc=True, errors="coerce")
        df_live = df_live.dropna(subset=["ts_utc"])
        frames.append(df_live[["ts_utc", "close"]])
    df_1m = pd.concat(frames, ignore_index=True).drop_duplicates("ts_utc").sort_values("ts_utc")
    df_idx = df_1m.set_index("ts_utc")
    closes = df_idx["close"]
    print(f"[gc-cover] price data: {df_idx.index.min()} -> {df_idx.index.max()}  ({len(df_idx):,} bars)")

    def _forward_pct(ts: datetime, minutes: int) -> float | None:
        try:
            target = ts + pd.Timedelta(minutes=minutes)
            p_now = float(closes.loc[closes.index.asof(ts)])
            p_then = float(closes.loc[closes.index.asof(target)])
            if p_now <= 0: return None
            return (p_then / p_now - 1) * 100
        except (KeyError, IndexError):
            return None

    # 2026-05-10: thresholds tuned to setup outcome semantics. Typical detector
    # has TP1 at ~0.5% and SL at ~0.4% from entry. So:
    #   "WRONG_BLOCK"   = setup would have hit TP1 (price moved 0.5%+ favorably)
    #   "CORRECT_BLOCK" = setup would have hit SL (price moved 0.4%+ adversely)
    #   else NEUTRAL    = setup would have timed out anyway (block didn't matter)
    def _classify(side: str, change_pct: float | None,
                  tp_threshold: float = 0.5, sl_threshold: float = 0.4):
        """Return 'CORRECT_BLOCK', 'WRONG_BLOCK', or 'NEUTRAL'."""
        if change_pct is None: return "NO_DATA"
        # LONG setup blocked: correct if SL would have hit (price down <=-SL),
        # wrong if TP1 would have hit (price up >=+TP).
        if side == "long":
            if change_pct <= -sl_threshold: return "CORRECT_BLOCK"
            if change_pct >= tp_threshold: return "WRONG_BLOCK"
            return "NEUTRAL"
        else:
            if change_pct >= sl_threshold: return "CORRECT_BLOCK"
            if change_pct <= -tp_threshold: return "WRONG_BLOCK"
            return "NEUTRAL"

    # Aggregate by detector
    by_det = defaultdict(lambda: {"blocked": 0, "correct": 0, "wrong": 0, "neutral": 0,
                                    "no_data": 0, "penalty": 0})

    for rec in blocked + penalised:
        try:
            ts = datetime.fromisoformat(rec["ts"].replace("Z", "+00:00"))
            if ts.tzinfo is None: ts = ts.replace(tzinfo=timezone.utc)
        except (KeyError, ValueError, AttributeError):
            continue
        det = rec.get("setup_type", "?")
        side = rec.get("side", "")
        is_block = "block" in str(rec.get("decision", ""))
        change = _forward_pct(ts, 240)
        cls = _classify(side, change)
        if is_block:
            by_det[det]["blocked"] += 1
        else:
            by_det[det]["penalty"] += 1
        if cls == "CORRECT_BLOCK": by_det[det]["correct"] += 1
        elif cls == "WRONG_BLOCK": by_det[det]["wrong"] += 1
        elif cls == "NEUTRAL": by_det[det]["neutral"] += 1
        else: by_det[det]["no_data"] += 1

    rows = []
    for det, c in by_det.items():
        n_decisions = c["blocked"] + c["penalty"]
        n_evaluable = c["correct"] + c["wrong"]
        correct_rate = (c["correct"] / n_evaluable * 100) if n_evaluable else 0
        rows.append({
            "detector": det,
            "blocked": c["blocked"],
            "penalty": c["penalty"],
            "correct": c["correct"],
            "wrong": c["wrong"],
            "neutral": c["neutral"],
            "no_data": c["no_data"],
            "correct_rate_%": round(correct_rate, 1),
        })
    df_out = pd.DataFrame(rows).sort_values("blocked", ascending=False)
    if not len(df_out):
        print("[gc-cover] no eligible records"); return 0

    print("\n=== GC block/penalty coverage check ===")
    print(df_out.to_string(index=False))

    # Recommendation
    print("\n=== Recommendations ===")
    for _, r in df_out.iterrows():
        n_eval = r["correct"] + r["wrong"]
        if n_eval < 5:
            continue
        if r["correct_rate_%"] >= 60:
            print(f"  [KEEP] {r['detector']}: GC block correctly saves money "
                  f"({r['correct_rate_%']}% on N={n_eval}).")
        elif r["correct_rate_%"] >= 40:
            print(f"  [MARG] {r['detector']}: GC block marginal ({r['correct_rate_%']}% "
                  f"on N={n_eval}). No harm but no clear benefit.")
        else:
            print(f"  [DROP] {r['detector']}: GC block HURTS "
                  f"({r['correct_rate_%']}% on N={n_eval}). Consider removing from HARD_BLOCK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
