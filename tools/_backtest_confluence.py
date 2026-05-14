"""Confluence backtest — comma cooccurrence of multiple edge signals.

Hypothesis: когда 2-3+ независимых сигналов совпадают по времени в одной
direction (long/short), edge становится значительно сильнее.

Existing edges (with 4/4 walk-forward folds positive):
  1. Session breakout — ew=15 hold=3h, PF 1.73 (all transitions)
  2. long_multi_divergence — live WR ~100%
  3. long_pdl_bounce — отбой от PDL
  4. Cascade Alert — post-liquidation 5+ BTC

Method:
  1. Pre-generate signal timeline for each detector across 2y BTC 1h data.
     For each bar: which signal (if any) fired, side (long/short), strength.
  2. For each bar, count active signals in last `confluence_window_h` hours
     for each side independently.
  3. Trade rule: if active long signals >= K AND no active short signals → LONG.
                 if active short signals >= K AND no active long signals → SHORT.
                 (Mixed = skip — conflict)
  4. Hold N hours, exit market. Cooldown M hours.
  5. Sweep K (2, 3, 4), window_h (2, 4, 6, 12), hold_h (2, 4, 6, 12).

Simplified signal generation (avoid running full live detectors):
  - session_breakout: ICT levels + first-15min-of-session high/low break
  - multi_divergence: RSI 1h + OBV 1h slope divergence vs price (last 12 bars)
  - pdl_bounce: price within 0.5% of PDL + bullish close
  - pdh_rejection: price within 0.5% of PDH + bearish close
  - cascade_alert proxy: 1h candle with vol_z > 3 AND range > 1.5%

Output:
  docs/STRATEGIES/CONFLUENCE_BACKTEST.md
  state/confluence_results.csv
  state/confluence_signal_timeline.parquet (for inspection)
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT_MD = ROOT / "docs" / "STRATEGIES" / "CONFLUENCE_BACKTEST.md"
CSV_OUT = ROOT / "state" / "confluence_results.csv"
SIGNAL_TIMELINE = ROOT / "state" / "confluence_signal_timeline.parquet"

PRICE_1H = ROOT / "backtests" / "frozen" / "BTCUSDT_1h_2y.csv"
ICT_PARQUET = ROOT / "data" / "ict_levels" / "BTCUSDT_ict_levels_1m.parquet"

# Sweep params
CONFLUENCE_WINDOWS = [2, 4, 6, 12]  # hours to look back for co-occurrence
MIN_SIGNALS = [2, 3, 4]              # K — minimum confluence
HOLD_HOURS = [2, 4, 6, 12]
COOLDOWN_HOURS = 4
N_FOLDS = 4

BASE_SIZE_USD = 1000.0
TAKER_FEE_PCT = 0.075


@dataclass
class Signal:
    bar_idx: int
    detector: str
    side: str   # "long" / "short"


def load_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    print("[confluence] loading 1h BTC...")
    df = pd.read_csv(PRICE_1H).sort_values("ts").reset_index(drop=True)
    print(f"[confluence] {len(df)} 1h bars  "
          f"{pd.to_datetime(df['ts'].iloc[0], unit='ms')} -> "
          f"{pd.to_datetime(df['ts'].iloc[-1], unit='ms')}")

    print("[confluence] loading ICT levels (1m, will resample to 1h)...")
    ict = pd.read_parquet(ICT_PARQUET, columns=[
        "asia_high", "asia_low", "london_high", "london_low",
        "ny_am_high", "ny_am_low", "ny_lunch_high", "ny_lunch_low",
        "ny_pm_high", "ny_pm_low", "session_active",
        "time_in_session_min", "pdh", "pdl", "open", "high", "low", "close",
    ])
    # Resample to 1h boundaries — keep last value of each col per hour
    ict_1h = ict.resample("1h").last().reset_index()
    # Re-align to df['ts']: convert ts_ms → datetime
    df["dt"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    # Merge_asof on dt — ICT row preceding each df bar
    ict_1h["ts"] = ict_1h["ts"]
    df_merged = pd.merge_asof(
        df.sort_values("dt"),
        ict_1h.sort_values("ts").rename(columns={"ts": "dt"}),
        on="dt", direction="backward", tolerance=pd.Timedelta("2h"),
        suffixes=("", "_ict"),
    )
    print(f"[confluence] merged {len(df_merged)} rows, "
          f"non-null pdh: {df_merged['pdh'].notna().sum()}")
    return df, df_merged


# ── Signal generators (simplified versions of live detectors) ────────────


def _gen_session_breakout(df: pd.DataFrame) -> list[Signal]:
    """Fire when session_active changes (new session start) and within first
    bar after change, price has broken prior session high/low."""
    signals = []
    sa = df["session_active"].values
    prior_session = {
        "asia": "ny_pm",
        "london": "asia",
        "ny_am": "london",
        "ny_lunch": "ny_am",
        "ny_pm": "ny_lunch",
    }
    for i in range(1, len(df)):
        if sa[i] == sa[i - 1]:
            continue
        if sa[i] == "dead" or pd.isna(sa[i]):
            continue
        new = sa[i]
        prior = prior_session.get(str(new))
        if not prior:
            continue
        prior_high = df.iloc[i].get(f"{prior}_high")
        prior_low = df.iloc[i].get(f"{prior}_low")
        if pd.isna(prior_high) or pd.isna(prior_low):
            continue
        bar_high = df["high"].iloc[i]
        bar_low = df["low"].iloc[i]
        if bar_high >= prior_high:
            signals.append(Signal(i, "session_breakout", "long"))
        elif bar_low <= prior_low:
            signals.append(Signal(i, "session_breakout", "short"))
    return signals


def _gen_multi_divergence(df: pd.DataFrame, lookback: int = 12) -> list[Signal]:
    """RSI(14) on 1h + price divergence over last `lookback` bars.

    LONG signal: price lower-low AND RSI higher-low (bullish div)
    SHORT signal: price higher-high AND RSI lower-high (bearish div)
    """
    closes = df["close"].values
    if len(closes) < 30:
        return []
    delta = np.diff(closes, prepend=closes[0])
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    period = 14
    avg_gain = pd.Series(gain).rolling(period).mean().values
    avg_loss = pd.Series(loss).rolling(period).mean().values
    rs = avg_gain / np.where(avg_loss > 0, avg_loss, 1e-9)
    rsi = 100 - 100 / (1 + rs)

    signals = []
    for i in range(lookback + period, len(df)):
        win_close = closes[i - lookback:i + 1]
        win_rsi = rsi[i - lookback:i + 1]
        # divide window in 2 halves; compare extremes
        half = lookback // 2
        p1_low = float(np.min(win_close[:half]))
        p2_low = float(np.min(win_close[half:]))
        r1_low = float(np.min(win_rsi[:half]))
        r2_low = float(np.min(win_rsi[half:]))
        p1_high = float(np.max(win_close[:half]))
        p2_high = float(np.max(win_close[half:]))
        r1_high = float(np.max(win_rsi[:half]))
        r2_high = float(np.max(win_rsi[half:]))
        # bullish div
        if p2_low < p1_low and r2_low > r1_low and rsi[i] < 50:
            signals.append(Signal(i, "multi_divergence", "long"))
        # bearish div
        elif p2_high > p1_high and r2_high < r1_high and rsi[i] > 50:
            signals.append(Signal(i, "multi_divergence", "short"))
    return signals


def _gen_pdl_bounce(df: pd.DataFrame) -> list[Signal]:
    """Price within 0.5% of PDL AND green close (above open) → LONG."""
    signals = []
    for i in range(len(df)):
        pdl = df["pdl"].iloc[i]
        if pd.isna(pdl) or pdl <= 0:
            continue
        low = df["low"].iloc[i]
        close = df["close"].iloc[i]
        open_ = df["open"].iloc[i]
        if abs(low - pdl) / pdl < 0.005 and close > open_:
            signals.append(Signal(i, "pdl_bounce", "long"))
    return signals


def _gen_pdh_rejection(df: pd.DataFrame) -> list[Signal]:
    """Price within 0.5% of PDH AND red close → SHORT."""
    signals = []
    for i in range(len(df)):
        pdh = df["pdh"].iloc[i]
        if pd.isna(pdh) or pdh <= 0:
            continue
        high = df["high"].iloc[i]
        close = df["close"].iloc[i]
        open_ = df["open"].iloc[i]
        if abs(high - pdh) / pdh < 0.005 and close < open_:
            signals.append(Signal(i, "pdh_rejection", "short"))
    return signals


def _gen_cascade_proxy(df: pd.DataFrame, lookback: int = 20) -> list[Signal]:
    """Proxy for cascade-alert: large bar (range > 1.5%) AND vol_z > 2.

    Treat as reversal signal — after cascade, expect bounce in opposite direction.
    Red big bar + high vol → LONG (long longs got liquidated, bounce up).
    Green big bar + high vol → SHORT (shorts capitulated, expect retrace).
    """
    signals = []
    if len(df) < lookback + 10:
        return signals
    vol_mean = df["volume"].rolling(lookback).mean()
    vol_std = df["volume"].rolling(lookback).std()
    vol_z = (df["volume"] - vol_mean) / vol_std.replace(0, np.nan)
    for i in range(lookback, len(df)):
        z = vol_z.iloc[i]
        if pd.isna(z) or z < 2.0:
            continue
        high = df["high"].iloc[i]
        low = df["low"].iloc[i]
        open_ = df["open"].iloc[i]
        close = df["close"].iloc[i]
        rng_pct = (high - low) / open_ * 100 if open_ > 0 else 0
        if rng_pct < 1.5:
            continue
        if close < open_:
            signals.append(Signal(i, "cascade_proxy", "long"))   # bounce expected
        else:
            signals.append(Signal(i, "cascade_proxy", "short"))


    return signals


def generate_all_signals(df: pd.DataFrame) -> pd.DataFrame:
    print("[confluence] generating signals...")
    signals = []
    signals.extend(_gen_session_breakout(df))
    signals.extend(_gen_multi_divergence(df))
    signals.extend(_gen_pdl_bounce(df))
    signals.extend(_gen_pdh_rejection(df))
    signals.extend(_gen_cascade_proxy(df))
    sig_df = pd.DataFrame([{"bar": s.bar_idx, "detector": s.detector, "side": s.side}
                            for s in signals])
    counts = sig_df["detector"].value_counts()
    print(f"[confluence] {len(sig_df)} signals total:")
    for det, cnt in counts.items():
        print(f"  {det}: {cnt}")
    return sig_df


# ── Backtest confluence ───────────────────────────────────────────────────


def simulate_confluence(df: pd.DataFrame, sig_df: pd.DataFrame, *,
                        window_h: int, min_signals: int,
                        hold_h: int) -> dict:
    n = len(df)
    cool_bars = COOLDOWN_HOURS
    last_trade = -10**9

    # Pre-build per-bar lookup of (detector, side) tuples for O(1) window scan.
    # Use numpy arrays for speed instead of pandas .loc range queries (which
    # require sorted unique index and break on duplicates).
    long_by_bar: dict[int, set[str]] = {}
    short_by_bar: dict[int, set[str]] = {}
    for _, row in sig_df.iterrows():
        bar = int(row["bar"])
        det = str(row["detector"])
        if row["side"] == "long":
            long_by_bar.setdefault(bar, set()).add(det)
        else:
            short_by_bar.setdefault(bar, set()).add(det)

    close = df["close"].values
    trades = []

    for i in range(window_h, n - hold_h):
        if i - last_trade < cool_bars:
            continue
        lo = i - window_h + 1
        hi = i + 1
        long_dets: set[str] = set()
        short_dets: set[str] = set()
        for b in range(lo, hi):
            if b in long_by_bar:
                long_dets |= long_by_bar[b]
            if b in short_by_bar:
                short_dets |= short_by_bar[b]
        n_long = len(long_dets)
        n_short = len(short_dets)

        side = None
        if n_long >= min_signals and n_short == 0:
            side = "long"
        elif n_short >= min_signals and n_long == 0:
            side = "short"

        if side is None:
            continue
        last_trade = i

        entry = float(close[i])
        exit_p = float(close[i + hold_h])
        if entry <= 0:
            continue
        if side == "long":
            gross_pct = (exit_p - entry) / entry * 100
        else:
            gross_pct = (entry - exit_p) / entry * 100
        fee_pct = 2 * TAKER_FEE_PCT
        pnl_usd = BASE_SIZE_USD * (gross_pct - fee_pct) / 100
        trades.append({"bar": i, "side": side,
                       "n_signals": n_long if side == "long" else n_short,
                       "pnl_usd": pnl_usd})

    if not trades:
        return {"n": 0, "pnl": 0.0, "pf": 0.0, "wr": 0.0, "avg": 0.0, "dd": 0.0}

    pnls = np.array([t["pnl_usd"] for t in trades])
    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]
    pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else (
        999.0 if wins.sum() > 0 else 0.0)
    wr = float((pnls > 0).mean() * 100)
    eq = np.cumsum(pnls)
    peak = np.maximum.accumulate(eq)
    dd = float(np.max(peak - eq))
    return {"n": len(trades), "pnl": float(pnls.sum()),
            "pf": pf, "wr": wr, "avg": float(pnls.mean()), "dd": dd}


def walk_forward(df: pd.DataFrame, sig_df: pd.DataFrame, *,
                 window_h: int, min_signals: int, hold_h: int,
                 n_folds: int = N_FOLDS) -> list[dict]:
    n = len(df)
    fold_size = n // n_folds
    out = []
    for k in range(n_folds):
        start = k * fold_size
        end = (k + 1) * fold_size if k < n_folds - 1 else n
        sub_df = df.iloc[start:end].reset_index(drop=True)
        # Filter signals to fold
        sub_sig = sig_df[(sig_df["bar"] >= start) & (sig_df["bar"] < end)].copy()
        sub_sig["bar"] = sub_sig["bar"] - start
        m = simulate_confluence(sub_df, sub_sig, window_h=window_h,
                                min_signals=min_signals, hold_h=hold_h)
        out.append({"fold": k + 1, "n": m["n"], "pnl": m["pnl"], "pf": m["pf"]})
    return out


def main() -> int:
    df, df_merged = load_data()
    sig_df = generate_all_signals(df_merged)
    # Save signal timeline
    sig_df.to_parquet(SIGNAL_TIMELINE, index=False)
    print(f"[confluence] wrote signal timeline {SIGNAL_TIMELINE}")

    results = []
    n_combos = len(CONFLUENCE_WINDOWS) * len(MIN_SIGNALS) * len(HOLD_HOURS)
    print(f"\n[confluence] {n_combos} combos\n")
    idx = 0
    for wh in CONFLUENCE_WINDOWS:
        for k in MIN_SIGNALS:
            for hh in HOLD_HOURS:
                idx += 1
                m = simulate_confluence(df_merged, sig_df, window_h=wh,
                                        min_signals=k, hold_h=hh)
                wf = walk_forward(df_merged, sig_df, window_h=wh,
                                  min_signals=k, hold_h=hh)
                pos = sum(1 for f in wf if f["pnl"] > 0)
                results.append({
                    "window_h": wh, "min_signals": k, "hold_h": hh,
                    "n_trades": m["n"], "pnl_usd": m["pnl"],
                    "pf": m["pf"], "wr_pct": m["wr"],
                    "avg_pnl": m["avg"], "max_dd": m["dd"],
                    "fold_pos": pos, "fold_total": len(wf),
                })
                print(f"  [{idx}/{n_combos}] w={wh} K>={k} hold={hh} "
                      f"N={m['n']:>4} PnL=${m['pnl']:+,.0f} PF={m['pf']:.2f} "
                      f"WR={m['wr']:.0f}% pos={pos}/{len(wf)}")

    results.sort(key=lambda r: r["pnl_usd"], reverse=True)
    print("\n[confluence] TOP 10:")
    for r in results[:10]:
        print(f"  w={r['window_h']:>3} K>={r['min_signals']} hold={r['hold_h']:>3}  "
              f"N={r['n_trades']:>4} PnL=${r['pnl_usd']:>+9,.0f} "
              f"PF={r['pf']:>5.2f} WR={r['wr_pct']:>5.0f}% "
              f"pos={r['fold_pos']}/{r['fold_total']}")

    # Report
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    md = ["# Confluence Detector Backtest \n\n"]
    md.append("**Стратегия:** комбинация 5 детекторов в одном direction в окне.\n")
    md.append("Детекторы: session_breakout, multi_divergence, pdl_bounce, "
              "pdh_rejection, cascade_proxy\n\n")
    md.append(f"**Период:** {len(df)} 1h bars (~2y BTCUSDT)\n")
    md.append(f"**Signals total:** {len(sig_df)}\n")
    md.append("**Signal counts:**\n")
    for det, cnt in sig_df["detector"].value_counts().items():
        md.append(f"- {det}: {cnt}\n")
    md.append(f"\n**Sweep:** window={CONFLUENCE_WINDOWS}h × min_signals={MIN_SIGNALS} "
              f"× hold={HOLD_HOURS}h = {len(results)} combos\n\n")

    md.append("## Топ-25 по PnL\n\n")
    md.append("| window_h | min_K | hold_h | N | PnL ($) | PF | WR% | avg | DD | pos folds |\n")
    md.append("|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|\n")
    for r in results[:25]:
        md.append(f"| {r['window_h']} | {r['min_signals']} | {r['hold_h']} | "
                  f"{r['n_trades']} | {r['pnl_usd']:+,.0f} | {r['pf']:.2f} | "
                  f"{r['wr_pct']:.0f} | {r['avg_pnl']:+,.1f} | "
                  f"{r['max_dd']:,.0f} | {r['fold_pos']}/{r['fold_total']} |\n")

    md.append("\n## Verdict\n\n")
    qualified = [r for r in results
                 if r["pf"] >= 1.5 and r["n_trades"] >= 30 and r["fold_pos"] >= 3]
    if qualified:
        best = max(qualified, key=lambda r: r["pnl_usd"])
        md.append(f"✅ Confluence edge **подтверждён**. Best combo: "
                  f"window={best['window_h']}h, K≥{best['min_signals']}, "
                  f"hold={best['hold_h']}h → PF {best['pf']}, "
                  f"N={best['n_trades']}, PnL ${best['pnl_usd']:+,.0f}, "
                  f"{best['fold_pos']}/4 folds.\n")
    else:
        md.append("❌ Confluence не превзошёл одиночные edge при текущих proxy.\n")

    OUT_MD.write_text("".join(md), encoding="utf-8")
    print(f"\n[confluence] wrote {OUT_MD}")
    pd.DataFrame(results).to_csv(CSV_OUT, index=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
