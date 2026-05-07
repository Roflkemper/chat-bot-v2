"""Multi-signal confluence backtest.

Hypothesis: одиночные сигналы дают 30-35% (random/worse-than-coin-flip),
но **комбинация 3+ согласованных** может дать 60%+.

Signals tested per direction (LONG / SHORT):
  S1 regime_4h state (BULL/BEAR/RANGE buckets)
  S2 OI direction (oi_delta_1h positive/negative + magnitude)
  S3 funding extreme (long-pays / short-pays / neutral)
  S4 OI/price divergence (z-score: -1.5 = potential squeeze, +1.5 = crowd long)
  S5 taker imbalance (1h: positive → buyers stronger)
  S6 distance to PDH/PDL break (recent structural break)

For each timestamp, count how many signals AGREE on direction.
Then check 4h forward outcome.

Output:
  state/multi_signal_confluence_test.json
  docs/ANALYSIS/MULTI_SIGNAL_CONFLUENCE_2026-05-07.md
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.backtest_advise_history import (
    classify_bar, _enrich_with_indicators, _row_to_inputs, _verdict_from_3tf,
)


def _bucket_regime(state_4h: str) -> str:
    if state_4h in ("STRONG_UP", "SLOW_UP", "DRIFT_UP", "CASCADE_UP"):
        return "BULL"
    if state_4h in ("STRONG_DOWN", "SLOW_DOWN", "DRIFT_DOWN", "CASCADE_DOWN"):
        return "BEAR"
    return "RANGE"


def _signal_votes(features_row: pd.Series, state_4h: str) -> dict:
    """Count signal votes: each signal gives 'long', 'short', or 'neutral'."""
    votes = {"long": 0, "short": 0, "active_signals": []}

    def _add(name: str, side: str | None):
        if side == "long":
            votes["long"] += 1
            votes["active_signals"].append(f"+{name}")
        elif side == "short":
            votes["short"] += 1
            votes["active_signals"].append(f"-{name}")

    # S1 regime
    bucket = _bucket_regime(state_4h)
    if bucket == "BULL":
        _add("regime", "long")
    elif bucket == "BEAR":
        _add("regime", "short")

    # S2 OI direction
    oi_1h = features_row.get("oi_delta_1h")
    if pd.notna(oi_1h):
        if oi_1h > 0.5:
            _add("oi_growing", "long")  # OI rising — new positions, follow trend
        elif oi_1h < -0.5:
            _add("oi_falling", "short")  # OI dropping — closing pressure

    # S3 funding extreme (z-score)
    funding_z = features_row.get("funding_z")
    if pd.notna(funding_z):
        if funding_z > 1.5:
            # Longs paying heavily — too crowded long → bearish
            _add("funding_extreme_long", "short")
        elif funding_z < -1.5:
            # Shorts paying — short squeeze potential → bullish
            _add("funding_extreme_short", "long")

    # S4 OI/price divergence (z-score)
    oi_div_z = features_row.get("oi_price_div_1h_z")
    if pd.notna(oi_div_z):
        if oi_div_z < -1.5:
            # Price up, OI down → squeeze likely (bullish bias)
            _add("oi_div_squeeze", "long")
        elif oi_div_z > 1.5:
            # Price down, OI up → distribution (bearish)
            _add("oi_div_distribution", "short")

    # S5 taker imbalance 1h
    taker_1h = features_row.get("taker_imbalance_1h")
    if pd.notna(taker_1h):
        if taker_1h > 0.55:
            _add("taker_bullish", "long")
        elif taker_1h < 0.45:
            _add("taker_bearish", "short")

    # S6 PDH/PDL break — using dist_to_pdh
    dist_pdh = features_row.get("dist_to_pdh_pct")
    dist_pdl = features_row.get("dist_to_pdl_pct")
    if pd.notna(dist_pdh) and abs(dist_pdh) < 0.1:
        # Right at PDH — break probable
        _add("near_pdh", "long")
    elif pd.notna(dist_pdl) and abs(dist_pdl) < 0.1:
        _add("near_pdl", "short")

    return votes


def main():
    # Load features
    print("Loading features...")
    df = pd.read_parquet("data/forecast_features/full_features_1y.parquet")
    df = df.sort_index()
    print(f"Features: {df.shape}, {df.index.min()} to {df.index.max()}")

    # Load BTC 1h for price + regime classification
    btc = pd.read_csv(ROOT / "backtests/frozen/BTCUSDT_1h_2y.csv")
    btc["ts"] = pd.to_datetime(btc["ts"], unit="ms", utc=True)
    btc = btc.set_index("ts").sort_index()

    # Resample BTC to features frequency (5m parquet → 1h for our analysis)
    # Take 1h snapshot of features
    df_1h = df.resample("1h").last().dropna(subset=["close"])
    print(f"Resampled to 1h: {df_1h.shape}")

    # Build 4h regime classification
    btc_4h = btc.resample("4h").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
    btc_4h_e = _enrich_with_indicators(btc_4h, "4h")

    results = []
    for ts in df_1h.index:
        features_row = df_1h.loc[ts]

        # Get latest 4h regime
        m = btc_4h_e.index <= ts
        if not m.any():
            continue
        row_4h = btc_4h_e[m].iloc[-1]
        if pd.isna(row_4h["ema200"]):
            continue
        state_4h = classify_bar(_row_to_inputs(row_4h))

        # Signal votes
        votes = _signal_votes(features_row, state_4h)

        # Outcome 4h
        ts_4h = ts + timedelta(hours=4)
        try:
            p_now = float(features_row["close"])
            future = btc[btc.index <= ts_4h]
            if len(future) == 0 or p_now == 0:
                continue
            p_4h = float(future.iloc[-1]["close"])
        except (KeyError, IndexError):
            continue

        move_4h = (p_4h / p_now - 1) * 100

        confluence_score = votes["long"] - votes["short"]
        results.append({
            "ts": ts.isoformat(),
            "regime": _bucket_regime(state_4h),
            "long_votes": votes["long"],
            "short_votes": votes["short"],
            "confluence_score": confluence_score,  # -6..+6
            "active_signals": votes["active_signals"],
            "move_4h_pct": round(move_4h, 3),
        })

    print(f"Total samples: {len(results)}")

    # Aggregate by confluence_score
    by_score: dict = defaultdict(lambda: {"moves": [], "n": 0})
    for r in results:
        s = r["confluence_score"]
        by_score[s]["moves"].append(r["move_4h_pct"])
        by_score[s]["n"] += 1

    summary_by_score = {}
    for s, info in sorted(by_score.items()):
        moves = info["moves"]
        if not moves:
            continue
        moves_arr = np.array(moves)
        summary_by_score[str(s)] = {
            "n": len(moves),
            "mean_move_pct": round(float(np.mean(moves_arr)), 3),
            "median_move_pct": round(float(np.median(moves_arr)), 3),
            "pct_up": round(float(np.mean(moves_arr > 0) * 100), 1),
            "pct_strong_up": round(float(np.mean(moves_arr > 0.3) * 100), 1),
            "pct_strong_down": round(float(np.mean(moves_arr < -0.3) * 100), 1),
        }

    # Aggregate by total signals (long + short = "active count")
    by_active: dict = defaultdict(lambda: {"long": [], "short": [], "neutral": []})
    for r in results:
        total = r["long_votes"] + r["short_votes"]
        if r["long_votes"] - r["short_votes"] >= 3:
            by_active[total]["long"].append(r["move_4h_pct"])
        elif r["short_votes"] - r["long_votes"] >= 3:
            by_active[total]["short"].append(r["move_4h_pct"])
        else:
            by_active[total]["neutral"].append(r["move_4h_pct"])

    # Strong confluence (≥3 net) — "highest conviction"
    strong_long = [r for r in results if r["confluence_score"] >= 3]
    strong_short = [r for r in results if r["confluence_score"] <= -3]
    print(f"\nStrong LONG confluence (≥3 net): n={len(strong_long)}")
    print(f"Strong SHORT confluence (≤-3 net): n={len(strong_short)}")

    if strong_long:
        moves = np.array([r["move_4h_pct"] for r in strong_long])
        print(f"  LONG outcome: mean {moves.mean():+.2f}% | pct_up {(moves>0).mean()*100:.0f}% | pct_strong_up {(moves>0.3).mean()*100:.0f}%")
    if strong_short:
        moves = np.array([r["move_4h_pct"] for r in strong_short])
        print(f"  SHORT outcome: mean {moves.mean():+.2f}% | pct_down {(moves<0).mean()*100:.0f}% | pct_strong_down {(moves<-0.3).mean()*100:.0f}%")

    # Save
    out_dir = ROOT / "state"
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "data_window": {
            "start": str(df_1h.index.min()),
            "end": str(df_1h.index.max()),
            "n_samples": len(results),
        },
        "by_confluence_score": summary_by_score,
        "strong_confluence": {
            "long_n": len(strong_long),
            "long_mean_move_pct": round(float(np.mean([r["move_4h_pct"] for r in strong_long])), 3) if strong_long else None,
            "long_pct_up": round(float(np.mean([r["move_4h_pct"] > 0 for r in strong_long]) * 100), 1) if strong_long else None,
            "long_pct_strong_up": round(float(np.mean([r["move_4h_pct"] > 0.3 for r in strong_long]) * 100), 1) if strong_long else None,
            "short_n": len(strong_short),
            "short_mean_move_pct": round(float(np.mean([r["move_4h_pct"] for r in strong_short])), 3) if strong_short else None,
            "short_pct_down": round(float(np.mean([r["move_4h_pct"] < 0 for r in strong_short]) * 100), 1) if strong_short else None,
            "short_pct_strong_down": round(float(np.mean([r["move_4h_pct"] < -0.3 for r in strong_short]) * 100), 1) if strong_short else None,
        },
    }
    (out_dir / "multi_signal_confluence_test.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nSaved: {out_dir / 'multi_signal_confluence_test.json'}")

    # Console summary
    print("\n=== ACCURACY BY CONFLUENCE SCORE ===")
    for s in sorted(by_score.keys()):
        info = summary_by_score.get(str(s), {})
        if info.get("n", 0) >= 30:
            label = "LONG" if s > 0 else ("SHORT" if s < 0 else "NEUTRAL")
            print(
                f"  score {s:+d} ({label}, n={info['n']}): "
                f"mean {info['mean_move_pct']:+.2f}% | "
                f"pct_up {info['pct_up']}% | "
                f"strong_up {info['pct_strong_up']}% | "
                f"strong_down {info['pct_strong_down']}%"
            )


if __name__ == "__main__":
    main()
