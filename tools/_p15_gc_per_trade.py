"""P-15 + GC per-trade analysis (TZ #1 finalization, 2026-05-10).

Extends simulate_p15_harvest to return per-trade list with timestamps so we
can bucket trade PnL by GC state at entry time.

Hypothesis: P-15 LONG entries during GC downside-exhaustion (oversold = ready
to bounce) outperform entries during GC neutral or upside.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from _backtest_p15_honest_v2 import (  # noqa: E402
    ema, _trend_gate_short, _trend_gate_long, _trade_pnl,
    MAKER_REBATE, TAKER_FEE, SLIPPAGE_PCT,
)

OUT_MD = ROOT / "docs" / "STRATEGIES" / "P15_GC_PER_TRADE.md"

DATA_1M = ROOT / "backtests" / "frozen" / "BTCUSDT_1m_2y.csv"
DATA_ETH = ROOT / "backtests" / "frozen" / "ETHUSDT_1h_2y.csv"
DATA_DERIV = ROOT / "data" / "historical" / "binance_combined_BTCUSDT.parquet"

LOOKBACK_DAYS = 365
GC_SCORE_MIN = 3


def simulate_p15_per_trade(df: pd.DataFrame, R_pct: float, K_pct: float,
                            dd_cap_pct: float, direction: str,
                            base_size_usd: float = 1000.0,
                            max_reentries: int = 10) -> list[dict]:
    """Simulate P-15 returning list of trades with entry/exit timestamps.

    Each trade dict: {
      entry_ts, entry_price, exit_ts, exit_price, qty_btc, direction,
      pnl_usd, exit_reason ('harvest', 'dd_cap', 'gate_flip', 'final')
    }
    """
    df_1h = df.resample("1h", on="ts_utc").agg({
        "open": "first", "high": "max", "low": "min", "close": "last",
        "volume": "sum",
    }).dropna()
    if len(df_1h) < 250:
        return []

    ts_idx = df_1h.index
    close_1h = df_1h["close"].values
    high_1h = df_1h["high"].values
    low_1h = df_1h["low"].values
    e50 = ema(df_1h["close"], 50).values
    e200 = ema(df_1h["close"], 200).values

    fee_in = MAKER_REBATE
    fee_out = TAKER_FEE + SLIPPAGE_PCT

    base_qty_btc = base_size_usd / close_1h[200] if close_1h[200] > 0 else 0.001

    trades = []
    in_trend = False
    total_qty_btc = 0.0
    weighted_entry = 0.0
    extreme = 0.0
    cum_dd = 0.0
    n_re = 0
    open_ts = None
    open_price = 0.0  # avg entry across all current legs

    for i in range(200, len(close_1h)):
        ts = ts_idx[i]
        if direction == "short":
            gate = _trend_gate_short(e50[i], e200[i], close_1h[i])
        else:
            gate = _trend_gate_long(e50[i], e200[i], close_1h[i])
        c = close_1h[i]
        h = high_1h[i]
        l = low_1h[i]

        if not in_trend and gate:
            in_trend = True
            total_qty_btc = base_qty_btc
            weighted_entry = c * total_qty_btc
            extreme = c
            n_re = 0
            cum_dd = 0.0
            open_ts = ts
            open_price = c
            continue

        if in_trend:
            avg_entry = weighted_entry / total_qty_btc if total_qty_btc > 0 else c
            if direction == "short":
                extreme = max(extreme, h)
                adverse_pct = (extreme - avg_entry) / avg_entry * 100
                retrace_pct = (extreme - l) / extreme * 100
                exit_at = extreme * (1 - R_pct / 100)
                reentry_at = exit_at * (1 + K_pct / 100)
            else:
                extreme = min(extreme, l)
                adverse_pct = (avg_entry - extreme) / avg_entry * 100
                retrace_pct = (h - extreme) / extreme * 100
                exit_at = extreme * (1 + R_pct / 100)
                reentry_at = exit_at * (1 - K_pct / 100)

            cum_dd = max(cum_dd, adverse_pct)

            # DD cap
            if cum_dd >= dd_cap_pct:
                pnl = _trade_pnl(avg_entry, c, total_qty_btc, direction, fee_in, fee_out)
                trades.append({
                    "entry_ts": open_ts, "exit_ts": ts,
                    "entry_price": avg_entry, "exit_price": c,
                    "qty_btc": total_qty_btc, "direction": direction,
                    "pnl_usd": pnl, "exit_reason": "dd_cap",
                })
                in_trend = False
                total_qty_btc = 0.0; weighted_entry = 0.0; open_ts = None
                continue

            if not gate:
                pnl = _trade_pnl(avg_entry, c, total_qty_btc, direction, fee_in, fee_out)
                trades.append({
                    "entry_ts": open_ts, "exit_ts": ts,
                    "entry_price": avg_entry, "exit_price": c,
                    "qty_btc": total_qty_btc, "direction": direction,
                    "pnl_usd": pnl, "exit_reason": "gate_flip",
                })
                in_trend = False
                total_qty_btc = 0.0; weighted_entry = 0.0; open_ts = None
                continue

            if retrace_pct >= R_pct and n_re < max_reentries:
                harvest_qty = total_qty_btc * 0.5
                pnl = _trade_pnl(avg_entry, exit_at, harvest_qty, direction, fee_in, fee_out)
                # The harvest is a partial close — log as a trade with current open_ts
                # but we keep the position open. Set entry_ts of THIS trade to the
                # original open or last reentry, exit_ts now.
                trades.append({
                    "entry_ts": open_ts, "exit_ts": ts,
                    "entry_price": avg_entry, "exit_price": exit_at,
                    "qty_btc": harvest_qty, "direction": direction,
                    "pnl_usd": pnl, "exit_reason": "harvest",
                })
                total_qty_btc -= harvest_qty
                weighted_entry -= avg_entry * harvest_qty
                weighted_entry += reentry_at * base_qty_btc
                total_qty_btc += base_qty_btc
                n_re += 1
                extreme = reentry_at
                # New leg's entry timestamp is "now" — operationally it's a re-entry
                open_ts = ts

    # Final: close remainder
    if in_trend and total_qty_btc > 0:
        ts = ts_idx[-1]
        c = close_1h[-1]
        avg_entry = weighted_entry / total_qty_btc
        pnl = _trade_pnl(avg_entry, c, total_qty_btc, direction, fee_in, fee_out)
        trades.append({
            "entry_ts": open_ts, "exit_ts": ts,
            "entry_price": avg_entry, "exit_price": c,
            "qty_btc": total_qty_btc, "direction": direction,
            "pnl_usd": pnl, "exit_reason": "final",
        })

    return trades


def main() -> int:
    print(f"[p15-gc-pt] loading {LOOKBACK_DAYS}d 1m...")
    df_1m = pd.read_csv(DATA_1M)
    df_1m["ts_utc"] = pd.to_datetime(df_1m["ts"], unit="ms", utc=True)
    df_1m = df_1m.iloc[-LOOKBACK_DAYS * 1440:].reset_index(drop=True)

    # P-15 expects 15m TF — resample inside simulate
    df_15m = df_1m.set_index("ts_utc").resample("15min").agg({
        "ts": "first", "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum",
    }).dropna().reset_index()

    print("[p15-gc-pt] running P-15 long+short with per-trade tracking...")
    trades_long = simulate_p15_per_trade(df_15m, 0.3, 1.0, 3.0, "long")
    trades_short = simulate_p15_per_trade(df_15m, 0.3, 1.0, 3.0, "short")
    print(f"  LONG: {len(trades_long)} trades, total ${sum(t['pnl_usd'] for t in trades_long):.0f}")
    print(f"  SHORT: {len(trades_short)} trades, total ${sum(t['pnl_usd'] for t in trades_short):.0f}")

    # Build GC history (1h)
    print("[p15-gc-pt] building GC history...")
    df_1h = df_1m.set_index("ts_utc").resample("1h").agg({
        "ts": "first", "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum",
    }).dropna().reset_index()

    eth = pd.read_csv(DATA_ETH)
    if "ts_utc" not in eth.columns:
        eth["ts_utc"] = pd.to_datetime(eth["ts"], unit="ms", utc=True)
    else:
        eth["ts_utc"] = pd.to_datetime(eth["ts_utc"], utc=True)

    deriv = pd.read_parquet(DATA_DERIV)
    deriv["ts_utc"] = pd.to_datetime(deriv["ts_ms"], unit="ms", utc=True)
    deriv_idx = deriv.set_index("ts_utc").sort_index()

    def _deriv_at(ts):
        if ts < deriv_idx.index[0] or ts > deriv_idx.index[-1]:
            return {"oi_change_1h_pct": 0, "funding_rate_8h": 0, "global_ls_ratio": 1.0}
        try:
            row = deriv_idx.loc[deriv_idx.index.asof(ts)]
        except (KeyError, ValueError):
            return {"oi_change_1h_pct": 0, "funding_rate_8h": 0, "global_ls_ratio": 1.0}

        def f(v, d=0.0):
            try:
                x = float(v); return d if pd.isna(x) else x
            except: return d
        return {"oi_change_1h_pct": f(row.get("oi_change_1h_pct")),
                "funding_rate_8h": f(row.get("funding_rate_8h")),
                "global_ls_ratio": f(row.get("global_ls_ratio"), 1.0)}

    from services.grid_coordinator.loop import evaluate_exhaustion
    gc_history = []
    for i in range(50, len(df_1h)):
        sub = df_1h.iloc[i - 50:i + 1].reset_index(drop=True)
        ts = sub.iloc[-1]["ts_utc"]
        eth_w = eth[eth["ts_utc"] <= ts].tail(51).reset_index(drop=True)
        sub_eth = eth_w if len(eth_w) >= 30 else None
        ev = evaluate_exhaustion(sub, sub_eth, {"BTCUSDT": _deriv_at(ts)}, xrp=None)
        gc_history.append({"ts": ts, "up": ev["upside_score"], "down": ev["downside_score"]})
    gc_df = pd.DataFrame(gc_history).set_index("ts").sort_index()
    print(f"[p15-gc-pt] {len(gc_df)} GC ticks")

    def _bucket_at(entry_ts, side: str) -> str:
        # Find GC state at-or-before entry
        try:
            gc_row = gc_df.loc[gc_df.index.asof(entry_ts)]
            up = int(gc_row["up"])
            down = int(gc_row["down"])
        except (KeyError, ValueError, IndexError):
            return "unknown"
        # For LONG: aligned = down>=3 (oversold = bounce coming)
        # For SHORT: aligned = up>=3
        if side == "long":
            if down >= GC_SCORE_MIN: return "aligned (down≥3)"
            if up >= GC_SCORE_MIN: return "misaligned (up≥3)"
            return "neutral"
        else:
            if up >= GC_SCORE_MIN: return "aligned (up≥3)"
            if down >= GC_SCORE_MIN: return "misaligned (down≥3)"
            return "neutral"

    print("[p15-gc-pt] bucketing trades by GC at entry...")
    long_buckets = {}
    short_buckets = {}
    for tr in trades_long:
        b = _bucket_at(tr["entry_ts"], "long")
        long_buckets.setdefault(b, []).append(tr["pnl_usd"])
    for tr in trades_short:
        b = _bucket_at(tr["entry_ts"], "short")
        short_buckets.setdefault(b, []).append(tr["pnl_usd"])

    rows = []
    for direction, buckets in [("long", long_buckets), ("short", short_buckets)]:
        for bucket_name, pnls in buckets.items():
            if not pnls: continue
            wins = sum(1 for p in pnls if p > 0)
            total = sum(pnls)
            rows.append({
                "direction": direction,
                "bucket": bucket_name,
                "n_trades": len(pnls),
                "win_rate_%": round(wins / len(pnls) * 100, 1),
                "total_pnl_usd": round(total, 0),
                "avg_pnl_usd": round(total / len(pnls), 2),
            })
    df_out = pd.DataFrame(rows).sort_values(["direction", "total_pnl_usd"], ascending=[True, False])

    md = []
    md.append("# P-15 + grid_coordinator per-trade bucketing")
    md.append("")
    md.append(f"**Period:** {LOOKBACK_DAYS}d | **GC threshold:** score>={GC_SCORE_MIN}")
    md.append(f"**Total trades:** LONG={len(trades_long)}, SHORT={len(trades_short)}")
    md.append("")
    md.append("## PnL by GC bucket at entry time")
    md.append("")
    md.append(df_out.to_markdown(index=False))
    md.append("")
    md.append("## Verdict")
    md.append("")
    # Compare aligned vs misaligned avg
    for direction in ("long", "short"):
        sub = df_out[df_out["direction"] == direction]
        aligned_row = sub[sub["bucket"].str.startswith("aligned")]
        misaligned_row = sub[sub["bucket"].str.startswith("misaligned")]
        if len(aligned_row) and len(misaligned_row):
            a_avg = aligned_row.iloc[0]["avg_pnl_usd"]
            m_avg = misaligned_row.iloc[0]["avg_pnl_usd"]
            if a_avg > m_avg + 0.5:  # meaningful
                md.append(f"- **{direction.upper()}**: aligned avg ${a_avg} vs misaligned ${m_avg} "
                          f"→ **filter by GC = +${a_avg-m_avg:.2f}/trade**")
            else:
                md.append(f"- **{direction.upper()}**: aligned ${a_avg} vs misaligned ${m_avg} "
                          f"→ no meaningful difference (filter не помогает)")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"\n[p15-gc-pt] wrote {OUT_MD}")
    print("\nResult:")
    print(df_out.to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
