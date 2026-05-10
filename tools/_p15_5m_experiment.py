"""P-15 5m TF experiment (TZ #12, 2026-05-10).

Idea: P-15 на 15m даёт +$67k/2y (validated TZ commit c0de5bb), 1h = +$19k.
Question: даст ли 5m TF +$200k или fees съедят edge?

Approach: clone simulate_p15_harvest, add 5m TF, run on last 30 days.
Compare per-trade economics:
  - 15m baseline params (R=0.3 K=1.0 dd=3.0)
  - 5m candidate (R=0.1 K=0.3 dd=1.5) — scaled down to TF
  - 5m conservative (R=0.15 K=0.5 dd=2.0)

Honest fee model: maker rebate -0.0125% IN + taker 0.075% + slippage 0.02% OUT.
Round-trip 0.165%. 5m faster cycles = more fee paid per unit time.

If 5m harvest_pf < 1.3 OR avg_pnl_per_trade after fees < $0 → 5m is NOT worth.
If 5m total_pnl > 1.5 × 15m on same window → STRONG candidate to try paper.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from _backtest_p15_honest_v2 import simulate_p15_harvest  # noqa: E402

DATA_1M = ROOT / "backtests" / "frozen" / "BTCUSDT_1m_2y.csv"
LOOKBACK_DAYS = 30


def _build_5m_from_1m(df_1m: pd.DataFrame) -> pd.DataFrame:
    df = df_1m.copy()
    df["ts_utc"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    return df.set_index("ts_utc").resample("5min").agg({
        "ts": "first", "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum",
    }).dropna().reset_index()


def _build_15m_from_1m(df_1m: pd.DataFrame) -> pd.DataFrame:
    df = df_1m.copy()
    df["ts_utc"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    return df.set_index("ts_utc").resample("15min").agg({
        "ts": "first", "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum",
    }).dropna().reset_index()


def main() -> int:
    print(f"[5m-exp] loading {LOOKBACK_DAYS}d 1m...")
    df_1m = pd.read_csv(DATA_1M)
    df_1m = df_1m.iloc[-LOOKBACK_DAYS * 1440:].reset_index(drop=True)
    print(f"[5m-exp] {len(df_1m):,} 1m bars")

    df_5m = _build_5m_from_1m(df_1m)
    df_15m = _build_15m_from_1m(df_1m)
    print(f"[5m-exp] {len(df_5m):,} 5m bars  /  {len(df_15m):,} 15m bars")

    runs = [
        ("15m baseline (R0.3 K1.0 dd3)", df_15m, 0.3, 1.0, 3.0),
        ("5m scaled (R0.1 K0.3 dd1.5)", df_5m, 0.1, 0.3, 1.5),
        ("5m conservative (R0.15 K0.5 dd2)", df_5m, 0.15, 0.5, 2.0),
        ("5m wider (R0.2 K0.6 dd2.5)", df_5m, 0.2, 0.6, 2.5),
    ]
    rows = []
    for name, df, R, K, dd in runs:
        for direction in ("short", "long"):
            res = simulate_p15_harvest(df, R_pct=R, K_pct=K, dd_cap_pct=dd, direction=direction)
            avg_per_trade = res.realized_pnl_usd / res.n_trades if res.n_trades else 0
            rows.append({
                "config": name,
                "dir": direction,
                "n": res.n_trades,
                "wr%": round(res.win_rate_pct, 1),
                "pf": round(res.profit_factor, 2),
                "pnl$": round(res.realized_pnl_usd, 2),
                "avg$/trade": round(avg_per_trade, 3),
                "max_dd$": round(res.max_drawdown_usd, 2),
            })
    df_out = pd.DataFrame(rows)
    print("\n=== 5m P-15 experiment results (30d) ===")
    print(df_out.to_string(index=False))

    # Summary
    md = ROOT / "docs" / "STRATEGIES" / "P15_5M_EXPERIMENT.md"
    md.parent.mkdir(parents=True, exist_ok=True)
    md.write_text(
        f"# P-15 5m TF experiment\n\n"
        f"**Date:** 2026-05-10\n"
        f"**Lookback:** {LOOKBACK_DAYS} days BTC\n"
        f"**Engine:** simulate_p15_harvest (honest fees 0.165% RT)\n\n"
        f"## Results\n\n"
        f"{df_out.to_markdown(index=False)}\n\n"
        f"## Verdict\n\n"
        f"See PnL$ column compared to 15m baseline. If 5m PnL > 1.5× 15m AND "
        f"PF >= 1.3 AND avg$/trade > 0 — candidate worth paper trial. Else: "
        f"5m fees eat the edge — keep 15m.\n",
        encoding="utf-8",
    )
    print(f"\n[5m-exp] wrote {md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
