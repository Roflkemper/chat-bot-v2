"""Setup precision tracker.

Closes the loop on each emitted setup: was it TP1/SL/TIMEOUT?
Computes per-detector real win-rate + expectancy and compares to
backtest expectations. Catches drift earlier than edge_tracker.

Reads:
  state/setups.jsonl                     — every emitted setup
  state/setup_outcomes.jsonl             — already-evaluated (skip)
  market_live/market_1m.csv  +  frozen   — price source

Writes:
  state/setup_outcomes.jsonl  — one line per evaluated setup
  stdout                      — per-detector summary

Outcome rules:
  Walk minutes from detected_at to detected_at+window_minutes.
  - LONG: TP1 if high >= tp1; SL if low <= stop; first one wins.
  - SHORT: TP1 if low <= tp1; SL if high >= stop; first one wins.
  - Else: TIMEOUT, pnl = (last_close - entry) * sign.
  Slippage/fees: 0.165% RT round-trip.

Run weekly via cron + on-demand for live monitoring.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SETUPS = ROOT / "state" / "setups.jsonl"
OUTCOMES = ROOT / "state" / "setup_precision_outcomes.jsonl"
DATA_FROZEN = ROOT / "backtests" / "frozen" / "BTCUSDT_1m_2y.csv"
DATA_LIVE = ROOT / "market_live" / "market_1m.csv"

FEES_RT_PCT = 0.165


def _load_prices() -> pd.DataFrame:
    frames = []
    if DATA_FROZEN.exists():
        df = pd.read_csv(DATA_FROZEN)
        df["ts_utc"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
        frames.append(df[["ts_utc", "high", "low", "close"]])
    if DATA_LIVE.exists():
        df = pd.read_csv(DATA_LIVE)
        df["ts_utc"] = pd.to_datetime(df["ts_utc"], utc=True, errors="coerce")
        df = df.dropna(subset=["ts_utc"])
        frames.append(df[["ts_utc", "high", "low", "close"]])
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True).drop_duplicates("ts_utc")
    return out.sort_values("ts_utc").set_index("ts_utc")


def _evaluate(setup: dict, prices: pd.DataFrame) -> dict | None:
    try:
        det_at = datetime.fromisoformat(setup["detected_at"].replace("Z", "+00:00"))
        if det_at.tzinfo is None:
            det_at = det_at.replace(tzinfo=timezone.utc)
    except (KeyError, ValueError):
        return None
    entry = float(setup.get("entry_price") or 0)
    stop = float(setup.get("stop_price") or 0)
    tp1 = float(setup.get("tp1_price") or 0)
    if entry <= 0 or stop <= 0 or tp1 <= 0:
        return None

    side = "long" if tp1 > entry else "short"
    window_min = int(setup.get("window_minutes") or 120)
    end_at = det_at + timedelta(minutes=window_min)

    if prices.index.max() < end_at:
        return None  # not enough forward data yet

    forward = prices.loc[(prices.index >= det_at) & (prices.index <= end_at)]
    if forward.empty:
        return None

    outcome = "TIMEOUT"
    exit_price = float(forward["close"].iloc[-1])
    for ts, row in forward.iterrows():
        if side == "long":
            if row["high"] >= tp1:
                outcome = "TP1"; exit_price = tp1; break
            if row["low"] <= stop:
                outcome = "SL"; exit_price = stop; break
        else:
            if row["low"] <= tp1:
                outcome = "TP1"; exit_price = tp1; break
            if row["high"] >= stop:
                outcome = "SL"; exit_price = stop; break

    if side == "long":
        pnl_pct = (exit_price - entry) / entry * 100 - FEES_RT_PCT
    else:
        pnl_pct = (entry - exit_price) / entry * 100 - FEES_RT_PCT

    return {
        "setup_id": setup.get("setup_id"),
        "setup_type": setup.get("setup_type"),
        "pair": setup.get("pair"),
        "side": side,
        "detected_at": setup.get("detected_at"),
        "outcome": outcome,
        "entry": entry,
        "exit": round(exit_price, 4),
        "pnl_pct": round(pnl_pct, 4),
    }


def main() -> int:
    if not SETUPS.exists():
        print("[precision] no setups.jsonl"); return 0
    prices = _load_prices()
    if prices.empty:
        print("[precision] no price data"); return 1
    print(f"[precision] price range: {prices.index.min()} -> {prices.index.max()}")

    seen = set()
    if OUTCOMES.exists():
        with OUTCOMES.open(encoding="utf-8") as f:
            for line in f:
                try:
                    seen.add(json.loads(line).get("setup_id"))
                except json.JSONDecodeError:
                    continue

    new_outcomes = []
    skipped = 0
    skipped_non_trade = 0
    with SETUPS.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try:
                setup = json.loads(line)
            except json.JSONDecodeError:
                continue
            if setup.get("setup_id") in seen:
                continue
            # Skip non-trade setups (grid management): they emit grid_action
            # and have recommended_size_btc=0.0. Their TP/SL are target levels
            # for grid bots, not entry/exit for a discrete trade.
            if (setup.get("grid_action")
                    or float(setup.get("recommended_size_btc") or 0) <= 0):
                skipped_non_trade += 1
                continue
            # Skip P-15 lifecycle (separate engine)
            stype = setup.get("setup_type") or ""
            if stype.startswith("p15_"):
                skipped_non_trade += 1
                continue
            res = _evaluate(setup, prices)
            if res is None:
                skipped += 1
                continue
            new_outcomes.append(res)

    if new_outcomes:
        OUTCOMES.parent.mkdir(parents=True, exist_ok=True)
        with OUTCOMES.open("a", encoding="utf-8") as f:
            for r in new_outcomes:
                f.write(json.dumps(r) + "\n")
    print(f"[precision] +{len(new_outcomes)} new outcomes, "
          f"skipped {skipped} (insufficient forward), "
          f"skipped {skipped_non_trade} (non-trade/p15)")

    # Aggregate
    all_outcomes = []
    if OUTCOMES.exists():
        with OUTCOMES.open(encoding="utf-8") as f:
            for line in f:
                try: all_outcomes.append(json.loads(line))
                except json.JSONDecodeError: continue
    if not all_outcomes:
        print("[precision] no outcomes yet"); return 0

    by_det = defaultdict(lambda: {"n": 0, "tp1": 0, "sl": 0, "timeout": 0, "pnl_sum": 0.0})
    for o in all_outcomes:
        d = by_det[o["setup_type"]]
        d["n"] += 1
        d[o["outcome"].lower() if o["outcome"] != "TP1" else "tp1"] += 1
        d["pnl_sum"] += o["pnl_pct"]

    rows = []
    for det, c in by_det.items():
        wr = c["tp1"] / c["n"] * 100 if c["n"] else 0
        rows.append({
            "detector": det,
            "n": c["n"],
            "tp1": c["tp1"],
            "sl": c["sl"],
            "timeout": c["timeout"],
            "wr_%": round(wr, 1),
            "pnl_sum_%": round(c["pnl_sum"], 2),
            "expectancy_%": round(c["pnl_sum"] / max(c["n"], 1), 4),
        })
    df = pd.DataFrame(rows).sort_values("n", ascending=False)
    print("\n=== Setup precision (live) ===")
    print(df.to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
