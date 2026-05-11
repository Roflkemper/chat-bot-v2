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


_DEFAULT_BACKTEST_EXPECTANCY = {
    "short_pdh_rejection": 0.005,   # PF 1.16 calibrated
    "short_rally_fade": 0.005,      # PF ~1.4 with filter
    "long_pdl_bounce": 0.001,
    "long_dump_reversal": 0.001,
    "long_double_bottom": 0.005,
    "short_double_top": 0.005,
    "long_multi_divergence": 0.0,
    "long_rsi_momentum_ga": 0.0,
    "short_mfi_multi_ga": 0.0,
}

_BACKTEST_EXP_PATH = ROOT / "data" / "config" / "backtest_expectancy.json"


def _load_backtest_expectancy() -> dict[str, float]:
    """Load per-detector expected expectancy from JSON, fall back to defaults."""
    if _BACKTEST_EXP_PATH.exists():
        try:
            data = json.loads(_BACKTEST_EXP_PATH.read_text(encoding="utf-8"))
            return {k: float(v) for k, v in data.items()
                    if isinstance(v, (int, float))}
        except (OSError, ValueError, json.JSONDecodeError):
            pass
    return dict(_DEFAULT_BACKTEST_EXPECTANCY)


def _bootstrap_ci(values: list[float], statistic_fn,
                  n_resamples: int = 1000, alpha: float = 0.05) -> tuple[float, float]:
    """Percentile bootstrap CI for an arbitrary statistic."""
    if not values or len(values) < 3:
        return (0.0, 0.0)
    import random
    n = len(values)
    samples = []
    for _ in range(n_resamples):
        resample = [values[random.randrange(n)] for _ in range(n)]
        samples.append(statistic_fn(resample))
    samples.sort()
    lo = samples[int(n_resamples * alpha / 2)]
    hi = samples[int(n_resamples * (1 - alpha / 2)) - 1]
    return (lo, hi)


def _status(n: int, ci_lo: float, ci_hi: float, live_exp: float,
            bt_exp: float | None) -> str:
    """Status classification:
      INSUFFICIENT — N<30, can't say anything.
      EVALUATING   — 30<=N<100, stats forming.
      STABLE       — N>=100, CI excludes 0 on positive side.
      DEGRADED     — N>=30, CI excludes 0 on negative side OR live drifted >2σ
                     from backtest expected.
      MARGINAL     — N>=30, CI straddles 0 (inconclusive).
    """
    if n < 30:
        return "INSUFFICIENT"
    if ci_lo > 0:  # entirely positive
        return "STABLE" if n >= 100 else "EVALUATING"
    if ci_hi < 0:  # entirely negative — actively losing
        return "DEGRADED"
    # CI straddles 0 — check drift vs backtest
    if bt_exp is not None and bt_exp > 0:
        # Width of CI as proxy for σ
        approx_sigma = max(1e-6, (ci_hi - ci_lo) / 4.0)
        z = abs(live_exp - bt_exp) / approx_sigma
        if z >= 2.0 and live_exp < bt_exp:
            return "DEGRADED"
    return "MARGINAL"


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

    by_det = defaultdict(lambda: {"n": 0, "tp1": 0, "sl": 0, "timeout": 0,
                                    "pnls": []})
    for o in all_outcomes:
        d = by_det[o["setup_type"]]
        d["n"] += 1
        d[o["outcome"].lower() if o["outcome"] != "TP1" else "tp1"] += 1
        d["pnls"].append(float(o["pnl_pct"]))

    # Backtest expected expectancy per detector. Loaded from
    # config/backtest_expectancy.json if present (refresh by running
    # tools/_backtest_detectors_honest.py and updating the json).
    # Falls back to hardcoded defaults from 2026-05-10 research runs.
    BACKTEST_EXPECTANCY = _load_backtest_expectancy()

    rows = []
    for det, c in by_det.items():
        n = c["n"]
        pnls = c["pnls"]
        wr = c["tp1"] / n * 100 if n else 0
        exp = sum(pnls) / n if n else 0
        ci_lo, ci_hi = _bootstrap_ci(pnls, statistic_fn=lambda x: sum(x)/len(x) if x else 0)
        bt_exp = BACKTEST_EXPECTANCY.get(det)
        status = _status(n, ci_lo, ci_hi, exp, bt_exp)
        rows.append({
            "detector": det,
            "n": n,
            "tp1": c["tp1"],
            "sl": c["sl"],
            "timeout": c["timeout"],
            "wr_%": round(wr, 1),
            "exp_%": round(exp, 4),
            "ci95_lo": round(ci_lo, 4),
            "ci95_hi": round(ci_hi, 4),
            "bt_exp_%": bt_exp,
            "status": status,
        })
    df = pd.DataFrame(rows).sort_values("n", ascending=False)
    print("\n=== Setup precision (live, with 95% CI) ===")
    print(df.to_string(index=False))

    # Per-status summary
    statuses = df["status"].value_counts().to_dict()
    print(f"\nStatus breakdown: {statuses}")

    # Highlight DEGRADED detectors
    degraded = df[df["status"] == "DEGRADED"]
    if not degraded.empty:
        print("\n[ALERT] DEGRADED detectors (live exp drifted from backtest):")
        for _, r in degraded.iterrows():
            print(f"  {r['detector']}: live exp {r['exp_%']:+.4f}% vs "
                  f"bt {r['bt_exp_%']}, CI [{r['ci95_lo']:+.4f}, {r['ci95_hi']:+.4f}]")

    # Per (detector, pair) breakdown — surfaces pair-specific drift
    # that aggregate stats hide.
    by_det_pair = defaultdict(lambda: {"n": 0, "tp1": 0, "sl": 0, "timeout": 0,
                                         "pnls": []})
    for o in all_outcomes:
        key = (o["setup_type"], o.get("pair", "?"))
        d = by_det_pair[key]
        d["n"] += 1
        d[o["outcome"].lower() if o["outcome"] != "TP1" else "tp1"] += 1
        d["pnls"].append(float(o["pnl_pct"]))

    pair_rows = []
    for (det, pair), c in by_det_pair.items():
        if c["n"] < 5:
            continue  # too thin to render
        n = c["n"]
        pnls = c["pnls"]
        exp = sum(pnls) / n
        wr = c["tp1"] / n * 100
        pair_rows.append({
            "detector": det,
            "pair": pair,
            "n": n,
            "wr_%": round(wr, 1),
            "exp_%": round(exp, 4),
            "tp1": c["tp1"],
            "sl": c["sl"],
            "timeout": c["timeout"],
        })

    if pair_rows:
        df_pair = pd.DataFrame(pair_rows).sort_values(
            ["detector", "n"], ascending=[True, False],
        )
        print("\n=== Per (detector, pair) breakdown (N>=5) ===")
        print(df_pair.to_string(index=False))

        # Highlight detectors with strong cross-pair divergence:
        # if one pair has positive exp and another has clearly negative,
        # it's a candidate for pair-aware config (DISABLED_DETECTORS by pair).
        divergent = []
        for det in df_pair["detector"].unique():
            sub = df_pair[df_pair["detector"] == det]
            if len(sub) < 2: continue
            min_exp = sub["exp_%"].min()
            max_exp = sub["exp_%"].max()
            if min_exp < -0.05 and max_exp > 0.05:
                divergent.append((det, min_exp, max_exp))
        if divergent:
            print("\n[INSIGHT] detectors with cross-pair divergence:")
            for det, lo, hi in divergent:
                print(f"  {det}: best pair +{hi:.3f}%, worst pair {lo:+.3f}% "
                      f"— consider pair-aware disable")
    return 0


if __name__ == "__main__":
    sys.exit(main())
