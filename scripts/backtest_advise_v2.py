"""Backtest /advise v2 with cross-asset rules + regime-conditional analysis.

Extends scripts/backtest_advise_history.py:
1. Loads BTC + ETH + XRP simultaneously (1h aligned).
2. Applies 3 new cross-asset rules from CROSS_ASSET_FINDINGS_2026-05-07:
   - Rule X1 (Pattern A.1): BTC +1%/h & ETH flat → LONG_BTC bias
   - Rule X2 (Pattern C.2): ETH -1.5%/h & BTC quiet → AVOID_ETH_LONG (we apply as SHORT_ETH bias for backtest)
   - Rule X3 (Pattern A.2): BTC -1%/h & ETH flat → FADE_ALTS at 24h
3. Combined verdict: cross-asset rule overrides 3tf verdict if active.
4. Output split by regime state (4h state) — accuracy per regime separately.
5. Compares: baseline (3tf only) vs new (3tf + cross-asset) accuracy.

Run: python scripts/backtest_advise_v2.py --days 365
Output: state/advise_backtest_v2_365d.{jsonl,summary.json}
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Reuse helpers from v1 backtest
from scripts.backtest_advise_history import (
    ClassifierInputs, classify_bar, _enrich_with_indicators, _row_to_inputs,
    _verdict_from_3tf,
)


# ── CROSS-ASSET RULES ──────────────────────────────────────────────────

# Thresholds match docs/ANALYSIS/CROSS_ASSET_FINDINGS_2026-05-07.md
RULE_X1_BTC_THRESHOLD = 0.01     # +1% in 1h
RULE_X1_ETH_QUIET = 0.003        # |<0.3%|

RULE_X2_ETH_THRESHOLD = -0.015   # -1.5% in 1h
RULE_X2_BTC_QUIET = 0.005        # |<0.5%|

RULE_X3_BTC_THRESHOLD = -0.01    # -1% in 1h
RULE_X3_ETH_QUIET = 0.003


def _cross_asset_signal(btc_1h_ret: float, eth_1h_ret: float) -> str | None:
    """Apply 3 cross-asset rules in priority order. Returns signal or None."""
    if pd.isna(btc_1h_ret) or pd.isna(eth_1h_ret):
        return None

    # Rule X1: BTC up + ETH flat → LONG_BTC continuation
    if btc_1h_ret > RULE_X1_BTC_THRESHOLD and abs(eth_1h_ret) < RULE_X1_ETH_QUIET:
        return "X1_LONG_BTC"

    # Rule X2: ETH down + BTC quiet → ETH continues down (strong)
    if eth_1h_ret < RULE_X2_ETH_THRESHOLD and abs(btc_1h_ret) < RULE_X2_BTC_QUIET:
        return "X2_SHORT_ETH"

    # Rule X3: BTC down + ETH flat → alts catch up at 24h
    if btc_1h_ret < RULE_X3_BTC_THRESHOLD and abs(eth_1h_ret) < RULE_X3_ETH_QUIET:
        return "X3_FADE_ALTS_24H"

    return None


def _eval_cross_asset_outcome(signal: str, btc_now: float, eth_now: float,
                               btc_4h: float, eth_4h: float,
                               btc_24h: float, eth_24h: float) -> tuple[bool | None, bool | None]:
    """Return (correct_at_relevant_horizon, None_for_other).

    Criterion matches CROSS_ASSET_FINDINGS_2026-05-07 — direction agreement
    (not 0.3% magnitude threshold which was too strict).
    """
    btc_move_4h = (btc_4h / btc_now - 1) * 100
    eth_move_4h = (eth_4h / eth_now - 1) * 100
    eth_move_24h = (eth_24h / eth_now - 1) * 100

    if signal == "X1_LONG_BTC":
        # Pattern A.1: BTC rallied + ETH lagged → BTC continues up
        # Original: 91% pct_up. So: correct = btc_move_4h > 0
        return (btc_move_4h > 0, None)
    if signal == "X2_SHORT_ETH":
        # Pattern C.2: ETH dropped + BTC quiet → ETH continues down
        # Original: 85.3% (= 1-pct_up where pct_up=14.7%). So: correct = eth_move_4h < 0
        return (eth_move_4h < 0, None)
    if signal == "X3_FADE_ALTS_24H":
        # Pattern A.2: BTC dropped + ETH lagged → ETH/XRP catch up at 24h
        # Original: ETH 24h mean -1.17%. So: correct = eth_move_24h < 0
        return (None, eth_move_24h < 0)
    return (None, None)


# ── REGIME SEGMENTATION ────────────────────────────────────────────────

def _bucket_regime(state_4h: str) -> str:
    if state_4h in ("STRONG_UP", "SLOW_UP", "DRIFT_UP", "CASCADE_UP"):
        return "BULL"
    if state_4h in ("STRONG_DOWN", "SLOW_DOWN", "DRIFT_DOWN", "CASCADE_DOWN"):
        return "BEAR"
    return "RANGE"


# ── BASELINE VERDICT EVAL (replica of v1 backtest) ────────────────────

def _baseline_verdict_eval(verdict: str, price_then: float, price_4h: float, price_24h: float):
    move_4h = (price_4h / price_then - 1) * 100
    move_24h = (price_24h / price_then - 1) * 100

    def _eval(v, move):
        if v in ("BULL_CONFLUENCE", "MACRO_BULL_MICRO_PULLBACK"):
            return move >= 0.3
        if v in ("BEAR_CONFLUENCE", "MACRO_BEAR_MICRO_RALLY"):
            return move <= -0.3
        if v == "RANGE":
            return abs(move) < 0.5
        return None

    return _eval(verdict, move_4h), _eval(verdict, move_24h)


# ── MAIN ───────────────────────────────────────────────────────────────

def run_backtest_v2(days: int, step_hours: int = 4, output_dir: Path = Path("state")) -> dict:
    btc = pd.read_csv(ROOT / "backtests/frozen/BTCUSDT_1h_2y.csv")
    eth = pd.read_csv(ROOT / "backtests/frozen/ETHUSDT_1h_2y.csv")
    xrp = pd.read_csv(ROOT / "backtests/frozen/XRPUSDT_1h_2y.csv")

    for d in (btc, eth, xrp):
        d["ts"] = pd.to_datetime(d["ts"], unit="ms", utc=True)
    btc = btc.set_index("ts").sort_index()
    eth = eth.set_index("ts").sort_index()[["close"]].rename(columns={"close": "eth_close"})
    xrp = xrp.set_index("ts").sort_index()[["close"]].rename(columns={"close": "xrp_close"})

    # Inner join on common ts
    df = btc.join([eth, xrp], how="inner")

    # Filter to last N days
    cutoff = df.index.max() - timedelta(days=days)
    df = df[df.index >= cutoff].copy()
    print(f"Aligned 3 symbols: {len(df)} bars from {df.index.min()} to {df.index.max()}")

    # 1h returns
    df["btc_ret_1h"] = np.log(df["close"] / df["close"].shift(1))
    df["eth_ret_1h"] = np.log(df["eth_close"] / df["eth_close"].shift(1))
    df["xrp_ret_1h"] = np.log(df["xrp_close"] / df["xrp_close"].shift(1))

    # Build BTC indicators for regime classification
    df_btc_idx = btc.loc[df.index].copy()
    df_btc_idx_e = _enrich_with_indicators(df_btc_idx, "1h")
    df_4h_resample = btc.resample("4h").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
    df_4h_e = _enrich_with_indicators(df_4h_resample, "4h")

    skip_warmup = 200
    indices = df.index[skip_warmup::step_hours]

    results = []
    for ts in indices:
        try:
            row = df.loc[ts]
        except KeyError:
            continue
        try:
            row_1h = df_btc_idx_e.loc[ts]
        except KeyError:
            continue
        row_4h_idx = df_4h_e.index <= ts
        if not row_4h_idx.any():
            continue
        row_4h = df_4h_e[row_4h_idx].iloc[-1]

        if pd.isna(row_4h["ema200"]) or pd.isna(row_1h["ema200"]):
            continue

        state_4h = classify_bar(_row_to_inputs(row_4h))
        state_1h = classify_bar(_row_to_inputs(row_1h))
        state_15m = state_1h  # using 1h as 15m proxy
        baseline_verdict = _verdict_from_3tf(state_4h, state_1h, state_15m)
        regime_bucket = _bucket_regime(state_4h)

        # Cross-asset rule signal
        cross_signal = _cross_asset_signal(row["btc_ret_1h"], row["eth_ret_1h"])

        # Outcomes
        ts_4h = ts + timedelta(hours=4)
        ts_24h = ts + timedelta(hours=24)
        future = df[df.index <= ts_24h]
        if len(future) < 25 or (df.index <= ts_4h).sum() == 0:
            continue
        try:
            r_4h = df.loc[df.index <= ts_4h].iloc[-1]
            r_24h = df.loc[df.index <= ts_24h].iloc[-1]
        except IndexError:
            continue

        btc_now = float(row["close"])
        eth_now = float(row["eth_close"])
        btc_4h = float(r_4h["close"])
        eth_4h = float(r_4h["eth_close"])
        btc_24h = float(r_24h["close"])
        eth_24h = float(r_24h["eth_close"])

        baseline_4h, baseline_24h = _baseline_verdict_eval(baseline_verdict, btc_now, btc_4h, btc_24h)

        cross_4h, cross_24h = (None, None)
        if cross_signal:
            cross_4h, cross_24h = _eval_cross_asset_outcome(
                cross_signal, btc_now, eth_now, btc_4h, eth_4h, btc_24h, eth_24h,
            )

        results.append({
            "ts": ts.isoformat(),
            "btc_price": round(btc_now, 2),
            "eth_price": round(eth_now, 2),
            "state_4h": state_4h,
            "state_1h": state_1h,
            "regime_bucket": regime_bucket,
            "baseline_verdict": baseline_verdict,
            "btc_ret_1h_pct": round(row["btc_ret_1h"] * 100, 3) if not pd.isna(row["btc_ret_1h"]) else None,
            "eth_ret_1h_pct": round(row["eth_ret_1h"] * 100, 3) if not pd.isna(row["eth_ret_1h"]) else None,
            "cross_signal": cross_signal,
            "btc_move_4h_pct": round((btc_4h / btc_now - 1) * 100, 2),
            "btc_move_24h_pct": round((btc_24h / btc_now - 1) * 100, 2),
            "eth_move_4h_pct": round((eth_4h / eth_now - 1) * 100, 2),
            "eth_move_24h_pct": round((eth_24h / eth_now - 1) * 100, 2),
            "baseline_correct_4h": baseline_4h,
            "baseline_correct_24h": baseline_24h,
            "cross_correct_4h": cross_4h,
            "cross_correct_24h": cross_24h,
        })

    # Aggregate
    summary = {
        "days": days,
        "step_hours": step_hours,
        "total_calls": len(results),
        "data_window": {
            "start": str(df.index.min()),
            "end": str(df.index.max()),
        },
    }

    # Baseline accuracy by verdict, split by regime
    baseline_table: dict = defaultdict(lambda: {"4h": [], "24h": []})
    for r in results:
        key = (r["baseline_verdict"], r["regime_bucket"])
        if r["baseline_correct_4h"] is not None:
            baseline_table[key]["4h"].append(r["baseline_correct_4h"])
        if r["baseline_correct_24h"] is not None:
            baseline_table[key]["24h"].append(r["baseline_correct_24h"])

    summary["baseline_by_verdict_and_regime"] = {}
    for (v, r), buckets in baseline_table.items():
        key = f"{v}__{r}"
        summary["baseline_by_verdict_and_regime"][key] = {
            "4h": {
                "n": len(buckets["4h"]),
                "correct_pct": round(np.mean(buckets["4h"]) * 100, 1) if buckets["4h"] else None,
            },
            "24h": {
                "n": len(buckets["24h"]),
                "correct_pct": round(np.mean(buckets["24h"]) * 100, 1) if buckets["24h"] else None,
            },
        }

    # Cross-asset rule accuracy
    cross_table: dict = defaultdict(list)
    cross_table_by_regime: dict = defaultdict(list)
    for r in results:
        if r["cross_signal"] is None:
            continue
        # Each rule has its own primary horizon
        if r["cross_correct_4h"] is not None:
            cross_table[r["cross_signal"]].append(r["cross_correct_4h"])
            cross_table_by_regime[(r["cross_signal"], r["regime_bucket"])].append(r["cross_correct_4h"])
        if r["cross_correct_24h"] is not None:
            cross_table[r["cross_signal"]].append(r["cross_correct_24h"])
            cross_table_by_regime[(r["cross_signal"], r["regime_bucket"])].append(r["cross_correct_24h"])

    summary["cross_asset_rules"] = {}
    for sig, lst in cross_table.items():
        summary["cross_asset_rules"][sig] = {
            "n": len(lst),
            "correct_pct": round(np.mean(lst) * 100, 1) if lst else None,
        }

    summary["cross_asset_rules_by_regime"] = {}
    for (sig, regime), lst in cross_table_by_regime.items():
        key = f"{sig}__{regime}"
        summary["cross_asset_rules_by_regime"][key] = {
            "n": len(lst),
            "correct_pct": round(np.mean(lst) * 100, 1) if lst else None,
        }

    # Verdict distribution
    summary["verdict_distribution"] = dict(Counter(r["baseline_verdict"] for r in results))
    summary["regime_distribution"] = dict(Counter(r["regime_bucket"] for r in results))
    summary["cross_signal_distribution"] = dict(Counter(r["cross_signal"] for r in results if r["cross_signal"]))

    # Write
    output_dir.mkdir(parents=True, exist_ok=True)
    detail = output_dir / f"advise_backtest_v2_{days}d.jsonl"
    with detail.open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    summary_path = output_dir / f"advise_backtest_v2_{days}d.summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=365)
    p.add_argument("--step-hours", type=int, default=4)
    args = p.parse_args()

    summary = run_backtest_v2(args.days, args.step_hours)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
