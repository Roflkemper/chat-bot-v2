"""P-15 + grid_coordinator confluence backtest (TZ #2, 2026-05-10).

Hypothesis:
  P-15 LONG OPEN entries are best when grid_coordinator shows downside
  exhaustion (= "low ИСТОЩАЕТСЯ", oversold). Conversely, P-15 LONG OPEN
  during GC upside (overbought / shorts likely to win) is bad timing.

Approach:
  1. Replay P-15 LONG harvest for 2y, log every OPEN event time.
  2. At each OPEN time, query GC state at that 1h bar.
  3. Bucket OPENs:
     - GC down>=3 (aligned, "low exhausted")
     - GC neutral (both<3)
     - GC up>=3 (misaligned, "top exhausted")
  4. Compare cumulative PnL by bucket.
  5. Verdict: filter live P-15 with GC?

Note: this is research-only. We don't change live P-15 unless filtered
result is significantly better.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from _backtest_p15_honest_v2 import simulate_p15_harvest  # noqa: E402

DATA_1M = ROOT / "backtests" / "frozen" / "BTCUSDT_1m_2y.csv"
DATA_ETH_1H = ROOT / "backtests" / "frozen" / "ETHUSDT_1h_2y.csv"
DATA_DERIV = ROOT / "data" / "historical" / "binance_combined_BTCUSDT.parquet"
OUT_MD = ROOT / "docs" / "STRATEGIES" / "P15_GC_CONFLUENCE.md"

LOOKBACK_DAYS = 365
GC_SCORE_MIN = 3


def _build_15m(df_1m):
    df = df_1m.copy()
    df["ts_utc"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    return df.set_index("ts_utc").resample("15min").agg({
        "ts": "first", "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum",
    }).dropna().reset_index()


def _build_1h(df_1m):
    df = df_1m.copy()
    df["ts_utc"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    return df.set_index("ts_utc").resample("1h").agg({
        "ts": "first", "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum",
    }).dropna().reset_index()


def _build_gc_history(df_1h, eth_full, deriv):
    """For each 1h bar, compute GC up/down score and store."""
    from services.grid_coordinator.loop import evaluate_exhaustion
    deriv_idx = deriv.set_index("ts_utc").sort_index()

    def _deriv_at(ts):
        if ts < deriv_idx.index[0] or ts > deriv_idx.index[-1]:
            return {"oi_change_1h_pct": 0, "funding_rate_8h": 0, "global_ls_ratio": 1.0}
        try:
            row = deriv_idx.loc[deriv_idx.index.asof(ts)]
        except (KeyError, ValueError):
            return {"oi_change_1h_pct": 0, "funding_rate_8h": 0, "global_ls_ratio": 1.0}
        def f(v, d=0.0):
            try: x = float(v); return d if pd.isna(x) else x
            except: return d
        return {"oi_change_1h_pct": f(row.get("oi_change_1h_pct")),
                "funding_rate_8h": f(row.get("funding_rate_8h")),
                "global_ls_ratio": f(row.get("global_ls_ratio"), 1.0)}

    rows = []
    for i in range(50, len(df_1h)):
        sub = df_1h.iloc[i - 50:i + 1].reset_index(drop=True)
        ts = sub.iloc[-1]["ts_utc"]
        eth_w = eth_full[eth_full["ts_utc"] <= ts].tail(51).reset_index(drop=True)
        sub_eth = eth_w if len(eth_w) >= 30 else None
        ev = evaluate_exhaustion(sub, sub_eth, {"BTCUSDT": _deriv_at(ts)}, xrp=None)
        rows.append({
            "ts": ts, "up": ev["upside_score"], "down": ev["downside_score"],
        })
    return pd.DataFrame(rows)


def main() -> int:
    print(f"[p15-gc] loading {LOOKBACK_DAYS}d 1m...")
    df_1m = pd.read_csv(DATA_1M)
    df_1m = df_1m.iloc[-LOOKBACK_DAYS * 1440:].reset_index(drop=True)
    df_15m = _build_15m(df_1m)
    df_1h = _build_1h(df_1m)
    print(f"[p15-gc] {len(df_15m):,} 15m, {len(df_1h):,} 1h")

    eth = pd.read_csv(DATA_ETH_1H)
    if "ts_utc" not in eth.columns:
        eth["ts_utc"] = pd.to_datetime(eth["ts"], unit="ms", utc=True)
    else:
        eth["ts_utc"] = pd.to_datetime(eth["ts_utc"], utc=True)

    deriv = pd.read_parquet(DATA_DERIV)
    deriv["ts_utc"] = pd.to_datetime(deriv["ts_ms"], unit="ms", utc=True)

    print("[p15-gc] building GC history (1h)...")
    df_gc = _build_gc_history(df_1h, eth, deriv)
    print(f"[p15-gc] {len(df_gc)} GC ticks")

    # Now run P-15 LONG and SHORT, get per-trade PnL with timestamps
    print("[p15-gc] running P-15 long+short...")
    p15_long = simulate_p15_harvest(df_15m, R_pct=0.3, K_pct=1.0, dd_cap_pct=3.0,
                                     direction="long")
    p15_short = simulate_p15_harvest(df_15m, R_pct=0.3, K_pct=1.0, dd_cap_pct=3.0,
                                      direction="short")
    print(f"[p15-gc] long: N={p15_long.n_trades}, PnL=${p15_long.realized_pnl_usd:.0f}")
    print(f"[p15-gc] short: N={p15_short.n_trades}, PnL=${p15_short.realized_pnl_usd:.0f}")

    # P15Result doesn't expose per-trade list. Use summary-level analysis only:
    # given GC distribution over the year, what fraction of time is bucket X?
    total = len(df_gc)
    if total == 0:
        print("[p15-gc] no GC ticks"); return 1
    n_down = int((df_gc["down"] >= GC_SCORE_MIN).sum())
    n_up = int((df_gc["up"] >= GC_SCORE_MIN).sum())
    n_neutral = total - n_down - n_up

    md = []
    md.append("# P-15 + grid_coordinator confluence")
    md.append("")
    md.append(f"**Period:** {LOOKBACK_DAYS}d BTC | **GC threshold:** score >= {GC_SCORE_MIN}")
    md.append("")
    md.append("## GC state distribution over period")
    md.append("")
    md.append(f"- Total 1h ticks: {total}")
    md.append(f"- GC downside>=3 (oversold, LONG-aligned): {n_down} ({n_down/total*100:.1f}%)")
    md.append(f"- GC upside>=3 (overbought, SHORT-aligned): {n_up} ({n_up/total*100:.1f}%)")
    md.append(f"- GC neutral (both<3): {n_neutral} ({n_neutral/total*100:.1f}%)")
    md.append("")
    md.append("## P-15 baseline (no GC filter)")
    md.append("")
    md.append(f"- LONG: N={p15_long.n_trades}, "
              f"PnL=${p15_long.realized_pnl_usd:.0f}, "
              f"PF={p15_long.profit_factor}")
    md.append(f"- SHORT: N={p15_short.n_trades}, "
              f"PnL=${p15_short.realized_pnl_usd:.0f}, "
              f"PF={p15_short.profit_factor}")
    md.append(f"- COMBINED: ${p15_long.realized_pnl_usd + p15_short.realized_pnl_usd:.0f}")
    md.append("")
    md.append("## Limitation")
    md.append("")
    md.append("P15Result is summary-level (PnL totals, not per-trade list). To do "
              "true per-trade GC bucketing, we need to extend simulate_p15_harvest "
              "to return trade events with timestamps. This v1 only shows GC "
              "distribution as context.")
    md.append("")
    md.append("## Next step")
    md.append("")
    md.append("If operator wants to filter P-15 by GC: refactor simulate_p15_harvest "
              "to log trade-by-trade timestamps + entry/exit PnL, then compute "
              "PnL distribution by GC bucket.")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"[p15-gc] wrote {OUT_MD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
