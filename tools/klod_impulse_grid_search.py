#!/usr/bin/env python3
"""
TZ-KLOD-IMPULSE-GRID-SEARCH
Grid search for KLOD_IMPULSE (bot 6075975963) trigger params on frozen BTC 1m.

Strategy: Impulse Long — enter long on sharp dump with RSI confirmation.
Grid: gs=0.3%, target=0.8%, max 5 orders × $180 = $900 total.
Exit: TP +0.8% | SL -1.5% | time-stop 24h.

Usage:
    python tools/klod_impulse_grid_search.py
    python tools/klod_impulse_grid_search.py --data backtests/frozen/BTCUSDT_1m_2y.csv
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# ── Grid search space ──────────────────────────────────────────────────────────
PRICE_DROP_THRESHOLDS = [-1.6, -1.8, -2.0, -2.2, -2.4, -2.6]  # 6 values
WINDOW_5M_BARS       = [4, 6, 8, 10]                            # 4 values
RSI_1H_THRESHOLDS    = [46, 49, 52, 55]                         # 4 values
# Total: 6 × 4 × 4 = 96 combinations

# ── Strategy params (fixed) ───────────────────────────────────────────────────
N_ORDERS     = 5
GS_PCT       = 0.3    # grid step %
TARGET_PCT   = 0.8    # TP % from initial entry
SL_PCT       = 1.5    # SL % from initial entry
CAPITAL_USD  = 900.0  # total allocated ($)
TIME_STOP_H  = 24     # hours before time-stop
ORDER_USD    = CAPITAL_USD / N_ORDERS  # $180 each

_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_DATA    = _ROOT / "backtests" / "frozen" / "BTCUSDT_1m_2y.csv"
_REPORTS_DIR     = _ROOT / "reports"


# ── Data loading ──────────────────────────────────────────────────────────────

def load_and_resample(path: str | Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load 1m CSV (Unix-ms ts), resample to 5m and 1h."""
    print(f"Loading {path} ...", flush=True)
    df = pd.read_csv(path)
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df = df.set_index("ts").sort_index()
    df = df[~df.index.duplicated(keep="first")]

    _agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    df_5m = df.resample("5min").agg(_agg).dropna(subset=["close"])
    df_1h = df.resample("1h").agg(_agg).dropna(subset=["close"])

    print(
        f"  1m={len(df):,}  5m={len(df_5m):,}  1h={len(df_1h):,} "
        f"  span={df.index[0].date()}..{df.index[-1].date()}",
        flush=True,
    )
    return df, df_5m, df_1h


# ── RSI ───────────────────────────────────────────────────────────────────────

def rsi_series(close: pd.Series, period: int = 14) -> pd.Series:
    """Vectorized Wilder RSI series."""
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(com=period - 1, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(com=period - 1, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100.0 - 100.0 / (1.0 + rs)
    return rsi.fillna(50.0).clip(0.0, 100.0)


def rsi_1h_on_5m(df_1h: pd.DataFrame, df_5m: pd.DataFrame) -> pd.Series:
    """Compute 1h RSI then forward-fill to 5m index."""
    rsi_h = rsi_series(df_1h["close"], 14)
    rsi_h.index = df_1h.index
    return rsi_h.reindex(df_5m.index, method="ffill").fillna(50.0)


# ── Trigger detection ─────────────────────────────────────────────────────────

def detect_triggers(
    df_5m: pd.DataFrame,
    rsi_on_5m: pd.Series,
    price_drop_pct: float,
    window_bars: int,
    rsi_threshold: float,
) -> np.ndarray:
    """Boolean mask (len=5m bars) where trigger fires.

    Trigger = price_drop_over_N_bars ≤ threshold AND RSI_1h ≤ rsi_threshold.
    Cooldown: 30-bar (2.5h) between fires to avoid double-triggering same dump.
    """
    close = df_5m["close"].values
    n = len(close)
    pct = np.full(n, 0.0)
    pct[window_bars:] = (close[window_bars:] - close[:n - window_bars]) / close[:n - window_bars] * 100.0

    rsi_arr = rsi_on_5m.values
    raw_trigger = (pct <= price_drop_pct) & (rsi_arr <= rsi_threshold)

    # 30-bar (2.5h) cooldown — iterate only over trigger events, not all bars
    raw_idx = np.where(raw_trigger)[0]
    if len(raw_idx) == 0:
        return np.zeros(n, dtype=bool)
    selected = [raw_idx[0]]
    for idx in raw_idx[1:]:
        if idx - selected[-1] >= 30:
            selected.append(idx)
    result = np.zeros(n, dtype=bool)
    result[selected] = True
    return result


# ── Outcome simulation ────────────────────────────────────────────────────────

def simulate_triggers(
    trigger_indices_5m: np.ndarray,
    df_5m: pd.DataFrame,
    df_1m: pd.DataFrame,
) -> list[dict]:
    """Simulate all triggers for one combination.

    Entry: open of the first 1m bar after the 5m trigger bar closes.
    Grid: N_ORDERS at GS_PCT steps below entry.
    Exit: TP at +TARGET_PCT | SL at -SL_PCT | time-stop 24h.
    Conservative: SL wins if SL and TP on same bar.
    """
    if len(trigger_indices_5m) == 0:
        return []

    ts_5m = df_5m.index
    ts_1m_ns = np.asarray(df_1m.index.astype(np.int64))
    high_1m   = df_1m["high"].values
    low_1m    = df_1m["low"].values
    close_1m  = df_1m["close"].values
    open_1m   = df_1m["open"].values
    N_1m      = len(df_1m)
    time_stop_bars = TIME_STOP_H * 60  # 1440

    # Grid step offsets (fraction of entry price)
    grid_offsets = np.arange(N_ORDERS) * GS_PCT / 100.0  # [0, 0.003, 0.006, ...]

    results: list[dict] = []
    for idx_5m in trigger_indices_5m:
        # Entry bar: first 1m bar after this 5m bar's close
        bar_close_ts = ts_5m[idx_5m]
        entry_ts_ns = bar_close_ts.value + int(5 * 60 * 1e9)
        entry_idx = int(np.searchsorted(ts_1m_ns, entry_ts_ns, side="left"))
        if entry_idx >= N_1m:
            continue

        entry_price = float(open_1m[entry_idx])
        if entry_price <= 0:
            continue

        end_idx = min(entry_idx + time_stop_bars, N_1m)
        h = high_1m[entry_idx:end_idx]
        l = low_1m[entry_idx:end_idx]
        c = close_1m[entry_idx:end_idx]
        n_bars = len(h)
        if n_bars == 0:
            continue

        # Grid order prices (lower than entry)
        orders = entry_price * (1.0 - grid_offsets)
        tp_price = entry_price * (1.0 + TARGET_PCT / 100.0)
        sl_price = entry_price * (1.0 - SL_PCT / 100.0)

        # When does each order fill? (cumulative min of low)
        cum_min = np.minimum.accumulate(l)
        fill_bar = np.full(N_ORDERS, n_bars, dtype=np.int32)
        fill_bar[0] = 0  # order 0 always fills at entry

        for j in range(1, N_ORDERS):
            mask = cum_min <= orders[j]
            if mask.any():
                fill_bar[j] = int(np.argmax(mask))

        # First TP bar
        tp_mask = h >= tp_price
        tp_bar = int(np.argmax(tp_mask)) if tp_mask.any() else n_bars

        # First SL bar
        sl_mask = l <= sl_price
        sl_bar = int(np.argmax(sl_mask)) if sl_mask.any() else n_bars

        # Determine exit
        if sl_bar < n_bars and tp_bar < n_bars:
            if sl_bar <= tp_bar:  # SL wins (conservative: same bar → SL)
                outcome, exit_b, exit_price = "sl", sl_bar, sl_price
            else:
                outcome, exit_b, exit_price = "tp", tp_bar, tp_price
        elif sl_bar < n_bars:
            outcome, exit_b, exit_price = "sl", sl_bar, sl_price
        elif tp_bar < n_bars:
            outcome, exit_b, exit_price = "tp", tp_bar, tp_price
        else:
            outcome, exit_b, exit_price = "time_stop", n_bars - 1, float(c[-1])

        # Filled orders at exit bar
        filled_mask = fill_bar <= exit_b
        filled_mask[0] = True  # always
        n_filled = int(filled_mask.sum())
        avg_entry = float(orders[filled_mask].mean())
        position_usd = n_filled * ORDER_USD
        qty = position_usd / avg_entry
        pnl = qty * (exit_price - avg_entry)

        results.append({
            "outcome": outcome,
            "pnl_usd": round(pnl, 2),
            "bars_held": exit_b + 1,
            "n_orders_filled": n_filled,
            "entry_price": round(entry_price, 2),
        })

    return results


# ── Aggregation ───────────────────────────────────────────────────────────────

def aggregate(
    outcomes: list[dict],
    price_drop_pct: float,
    window_bars: int,
    rsi_threshold: float,
    months: float,
) -> dict:
    n = len(outcomes)
    if n == 0:
        return {
            "price_drop_pct": price_drop_pct, "window_bars": window_bars,
            "rsi_threshold": rsi_threshold, "n_triggers": 0,
            "fire_rate_mo": 0.0, "win_rate_pct": 0.0,
            "total_pnl_usd": 0.0, "avg_pnl_per_fire": 0.0,
            "max_dd_usd": 0.0, "n_tp": 0, "n_sl": 0, "n_ts": 0, "avg_hold_h": 0.0,
        }

    pnls = np.array([o["pnl_usd"] for o in outcomes])
    n_tp = sum(1 for o in outcomes if o["outcome"] == "tp")
    n_sl = sum(1 for o in outcomes if o["outcome"] == "sl")
    n_ts = sum(1 for o in outcomes if o["outcome"] == "time_stop")
    avg_hold = float(np.mean([o["bars_held"] for o in outcomes])) / 60.0

    cum = np.cumsum(pnls)
    running_max = np.maximum.accumulate(cum)
    max_dd = float(np.min(cum - running_max))

    return {
        "price_drop_pct": price_drop_pct,
        "window_bars": window_bars,
        "rsi_threshold": rsi_threshold,
        "n_triggers": n,
        "fire_rate_mo": round(n / months, 1),
        "win_rate_pct": round(n_tp / n * 100, 1),
        "total_pnl_usd": round(float(pnls.sum()), 1),
        "avg_pnl_per_fire": round(float(pnls.mean()), 2),
        "max_dd_usd": round(max_dd, 1),
        "n_tp": n_tp, "n_sl": n_sl, "n_ts": n_ts,
        "avg_hold_h": round(avg_hold, 1),
    }


# ── Report generation ─────────────────────────────────────────────────────────

def _row(r: dict) -> str:
    trigger = f"{r['price_drop_pct']}%/{r['window_bars']}b/RSI{r['rsi_threshold']}"
    return (
        f"| {trigger:<26} | {r['n_triggers']:>5} | {r['fire_rate_mo']:>7.1f} "
        f"| {r['win_rate_pct']:>7.1f}% | {r['total_pnl_usd']:>10.1f} "
        f"| {r['avg_pnl_per_fire']:>10.2f} | {r['max_dd_usd']:>9.1f} "
        f"| {r['n_tp']:>4}/{r['n_sl']:>4}/{r['n_ts']:>4} |"
    )


def _header() -> str:
    return (
        "| Params (drop/window/RSI)   | Fires | Fire/mo | Win Rate |  Total PnL |  Avg/Fire |  Max DD   | TP/SL/TS |"
        "\n"
        "|:---------------------------|------:|--------:|---------:|-----------:|----------:|----------:|:---------|"
    )


def generate_report(results: list[dict], run_date: str) -> str:
    df = pd.DataFrame(results)

    # Sort by total_pnl_usd
    by_pnl = df.sort_values("total_pnl_usd", ascending=False)
    # Filter fire_rate ≥ 5/mo for WR ranking
    actionable = df[df["fire_rate_mo"] >= 5.0].sort_values("win_rate_pct", ascending=False)
    # Recommended: fire_rate 5-15/mo + WR > 50% + positive PnL
    recommended = df[
        (df["fire_rate_mo"] >= 5.0) & (df["fire_rate_mo"] <= 15.0) &
        (df["win_rate_pct"] > 50.0) & (df["total_pnl_usd"] > 0)
    ].sort_values("total_pnl_usd", ascending=False)

    lines: list[str] = []
    lines.append(f"# KLOD_IMPULSE Grid Search — {run_date}")
    lines.append("")
    lines.append("**Bot:** KLOD_IMPULSE (6075975963) · Impulse Long preset")
    lines.append(f"**Data:** BTCUSDT 1m 2y frozen ({run_date[:10]})")
    lines.append(f"**Grid:** {len(df)} combinations (drop={PRICE_DROP_THRESHOLDS}, window={WINDOW_5M_BARS}, RSI={RSI_1H_THRESHOLDS})")
    lines.append(f"**Strategy:** gs={GS_PCT}% · TP={TARGET_PCT}% · SL={SL_PCT}% · {N_ORDERS} orders × ${ORDER_USD:.0f} = ${CAPITAL_USD:.0f}")
    lines.append(f"**Trigger target:** 5-15 fires/month, WR > 50%, PnL > 0")
    lines.append("")

    lines.append("## Full results (all 96 combinations)")
    lines.append("")
    lines.append(_header())
    for _, r in by_pnl.iterrows():
        lines.append(_row(r))
    lines.append("")

    lines.append("## Top-10 by Total PnL")
    lines.append("")
    lines.append(_header())
    for _, r in by_pnl.head(10).iterrows():
        lines.append(_row(r))
    lines.append("")

    lines.append("## Top-10 by Win Rate (fire rate ≥ 5/month)")
    lines.append("")
    if actionable.empty:
        lines.append("_No combinations with ≥5 fires/month._")
    else:
        lines.append(_header())
        for _, r in actionable.head(10).iterrows():
            lines.append(_row(r))
    lines.append("")

    lines.append("## Sensitivity analysis (around best recommended params)")
    lines.append("")
    if not recommended.empty:
        best = recommended.iloc[0]
        best_d = best["price_drop_pct"]
        best_w = int(best["window_bars"])
        best_r = best["rsi_threshold"]
        neighbors = df[
            (df["price_drop_pct"].isin([best_d - 0.2, best_d, best_d + 0.2])) &
            (df["window_bars"].isin([max(4, best_w - 2), best_w, min(10, best_w + 2)])) &
            (df["rsi_threshold"].isin([best_r - 3, best_r, best_r + 3]))
        ].sort_values("total_pnl_usd", ascending=False)
        lines.append(f"Neighborhood of recommended ({best_d}%/{best_w}b/RSI{best_r:.0f}):")
        lines.append("")
        lines.append(_header())
        for _, r in neighbors.iterrows():
            lines.append(_row(r))
    else:
        lines.append("_No combination meets all criteria (5-15/mo, WR>50%, PnL>0)._")
        lines.append("")
        lines.append("Best available (relaxed: fire_rate ≥ 3/mo, WR > 45%):")
        relaxed = df[
            (df["fire_rate_mo"] >= 3.0) & (df["win_rate_pct"] > 45.0)
        ].sort_values("total_pnl_usd", ascending=False)
        if not relaxed.empty:
            lines.append("")
            lines.append(_header())
            for _, r in relaxed.head(5).iterrows():
                lines.append(_row(r))
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## RECOMMENDATION")
    lines.append("")

    def _rec_block(r: pd.Series, label: str) -> str:
        return "\n".join([
            f"### {label}",
            "",
            f"```",
            f"price_drop_threshold: {r['price_drop_pct']}%",
            f"window_5m_bars:       {int(r['window_bars'])}",
            f"rsi_1h_threshold:     {r['rsi_threshold']:.0f}",
            f"```",
            "",
            f"Expected: ~{r['fire_rate_mo']:.1f} fires/month · WR {r['win_rate_pct']:.1f}% · "
            f"avg pnl ${r['avg_pnl_per_fire']:.2f}/fire · total PnL ${r['total_pnl_usd']:.0f}/yr · "
            f"max DD ${r['max_dd_usd']:.0f}",
        ])

    if not recommended.empty:
        best = recommended.iloc[0]
        lines.append(_rec_block(best, "RECOMMENDED (best total PnL, 5-15/mo, WR>50%)"))
        lines.append("")
        if len(recommended) >= 2:
            # Conservative: highest WR
            conservative = recommended.sort_values("win_rate_pct", ascending=False).iloc[0]
            lines.append(_rec_block(conservative, "ALTERNATIVE — Conservative (highest WR)"))
            lines.append("")
        if len(recommended) >= 3:
            # Aggressive: highest fire rate
            aggressive = recommended.sort_values("fire_rate_mo", ascending=False).iloc[0]
            lines.append(_rec_block(aggressive, "ALTERNATIVE — Aggressive (highest fire rate)"))
            lines.append("")
    else:
        # No perfect fit — give best from relaxed criteria
        relaxed = df[df["fire_rate_mo"] >= 3.0].sort_values("total_pnl_usd", ascending=False)
        if not relaxed.empty:
            best = relaxed.iloc[0]
            lines.append(_rec_block(best, "BEST AVAILABLE (relaxed — fire_rate ≥ 3/mo)"))
            lines.append("")
            lines.append(
                "> ⚠️ No combination meets all three criteria simultaneously. "
                "Consider running on a larger dataset or accepting lower WR threshold."
            )
        else:
            lines.append("> ❌ No viable combination found in this search space.")
    lines.append("")
    lines.append(f"_Generated by tools/klod_impulse_grid_search.py on {run_date}_")

    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="KLOD_IMPULSE trigger params grid search")
    parser.add_argument("--data", default=str(_DEFAULT_DATA), help="Path to BTCUSDT_1m_2y.csv")
    parser.add_argument("--out", default=None, help="Report output path (default: reports/...)")
    args = parser.parse_args(argv)

    t0 = time.monotonic()
    run_date = datetime.utcnow().strftime("%Y-%m-%dT%H:%MZ")

    df_1m, df_5m, df_1h = load_and_resample(args.data)
    months = (df_1m.index[-1] - df_1m.index[0]).total_seconds() / (30.44 * 86400)

    # Precompute RSI once (expensive, shared across all combinations)
    print("Computing 1h RSI...", flush=True)
    rsi_on_5m = rsi_1h_on_5m(df_1h, df_5m)

    total_combos = len(PRICE_DROP_THRESHOLDS) * len(WINDOW_5M_BARS) * len(RSI_1H_THRESHOLDS)
    print(f"Running {total_combos} combinations...", flush=True)

    results: list[dict] = []
    done = 0

    for price_drop in PRICE_DROP_THRESHOLDS:
        for window in WINDOW_5M_BARS:
            for rsi_thr in RSI_1H_THRESHOLDS:
                trigger_mask = detect_triggers(df_5m, rsi_on_5m, price_drop, window, rsi_thr)
                trigger_idx = np.where(trigger_mask)[0]
                outcomes = simulate_triggers(trigger_idx, df_5m, df_1m)
                agg = aggregate(outcomes, price_drop, window, rsi_thr, months)
                results.append(agg)

                done += 1
                if done % 16 == 0 or done == total_combos:
                    elapsed = time.monotonic() - t0
                    eta = elapsed / done * (total_combos - done)
                    print(
                        f"  {done}/{total_combos}  elapsed={elapsed:.1f}s  eta={eta:.0f}s",
                        flush=True,
                    )

    elapsed = time.monotonic() - t0
    print(f"Done. {total_combos} combos in {elapsed:.1f}s ({elapsed/total_combos*1000:.0f}ms/combo)", flush=True)

    # Summary stats
    df_res = pd.DataFrame(results)
    viable = df_res[
        (df_res["fire_rate_mo"] >= 5) & (df_res["fire_rate_mo"] <= 15) &
        (df_res["win_rate_pct"] > 50) & (df_res["total_pnl_usd"] > 0)
    ]
    print(f"Viable combos (5-15/mo, WR>50%, PnL>0): {len(viable)}/{total_combos}", flush=True)

    # Write report
    report = generate_report(results, run_date)
    out_name = f"klod_impulse_grid_search_{run_date[:10]}.md"
    out_path = Path(args.out) if args.out else _REPORTS_DIR / out_name
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(f"Report: {out_path}", flush=True)

    # Print top-5 to stdout
    top5 = df_res.sort_values("total_pnl_usd", ascending=False).head(5)
    print("\nTop-5 by total PnL:")
    for _, r in top5.iterrows():
        print(
            f"  {r['price_drop_pct']}%/{r['window_bars']}b/RSI{r['rsi_threshold']:.0f}"
            f"  fires={r['n_triggers']}({r['fire_rate_mo']:.1f}/mo)"
            f"  WR={r['win_rate_pct']:.1f}%  PnL=${r['total_pnl_usd']:.0f}"
            f"  avg=${r['avg_pnl_per_fire']:.2f}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
