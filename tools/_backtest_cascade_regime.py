"""Cascade directional v2 — с regime-gate фильтрами.

Базовый результат (предыдущий sweep):
  LONG on LONG-cascade, thr=7-10 BTC, hold=24h, TP=2%, SL=2%
  → PF 2.75, WR 76%, n=68, 3/4 folds. Один fold в минусе.

Гипотезы для 4/4 folds:
  1. SHORT trades on SHORT-каскадах — может рабочий зеркальный edge.
  2. Regime gate: ADX < threshold (избегаем сильных трендов).
  3. Regime gate: EMA200 trend filter (LONG только когда EMA50>EMA200 или
     наоборот для шорта).
  4. Time-of-day filter — каскады в азии/нью-йорке могут вести по-разному.

Output: state/cascade_regime_results.csv
Запуск: python tools/_backtest_cascade_regime.py
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PRICE_CSV = ROOT / "backtests" / "frozen" / "BTCUSDT_1m_2y.csv"
LIQ_PARQUET = ROOT / "data" / "historical" / "bybit_liquidations_2024.parquet"
OUT_CSV = ROOT / "state" / "cascade_regime_results.csv"

FEE_RT_PCT = 0.17
SIZE_USD = 1000.0
N_FOLDS = 4


def load_price() -> pd.DataFrame:
    print(f"Loading {PRICE_CSV}...", file=sys.stderr)
    df = pd.read_csv(PRICE_CSV)
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df = df.set_index("ts").sort_index()
    df = df[~df.index.duplicated(keep="first")]
    return df


def load_liquidations() -> pd.DataFrame:
    print(f"Loading {LIQ_PARQUET}...", file=sys.stderr)
    df = pd.read_parquet(LIQ_PARQUET)
    df["liq_side"] = df["side"].apply(lambda x: "long" if x == "Sell" else "short")
    df = df.set_index("ts").sort_index()
    return df


# ───────────────────── Resamples & indicators ─────────────────────

def resample_1h(df_1m: pd.DataFrame) -> pd.DataFrame:
    return df_1m.resample("1h").agg({
        "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum",
    }).dropna()


def adx_h1(df_1h: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df_1h["high"], df_1h["low"], df_1h["close"]
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(span=period, adjust=False).mean()
    up = high.diff()
    down = -low.diff()
    plus_dm = ((up > down) & (up > 0)) * up
    minus_dm = ((down > up) & (down > 0)) * down
    plus_di = 100 * plus_dm.ewm(span=period, adjust=False).mean() / atr
    minus_di = 100 * minus_dm.ewm(span=period, adjust=False).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(span=period, adjust=False).mean().fillna(0)


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


# ───────────────────── Cascade detection ─────────────────────

def detect_cascades(liq_df: pd.DataFrame, *, threshold_btc: float,
                    window_min: int) -> list[tuple[pd.Timestamp, str, float]]:
    cascades = []
    last_per_side: dict[str, pd.Timestamp] = {}
    liq_df = liq_df.copy()
    liq_df["bucket"] = liq_df.index.floor("1min")

    for side in ("long", "short"):
        side_df = liq_df[liq_df["liq_side"] == side]
        if side_df.empty:
            continue
        per_min = side_df.groupby("bucket")["qty"].sum().sort_index()
        rolling = per_min.rolling(f"{window_min}min").sum()
        for ts, total in rolling.items():
            if total >= threshold_btc:
                prev = last_per_side.get(side)
                if prev is None or (ts - prev) >= pd.Timedelta(minutes=30):
                    cascades.append((ts, side, float(total)))
                    last_per_side[side] = ts
    return sorted(cascades, key=lambda x: x[0])


# ───────────────────── Trade simulator ─────────────────────

@dataclass
class Trade:
    entry_ts: pd.Timestamp
    side: str
    entry: float
    exit_ts: Optional[pd.Timestamp] = None
    exit: Optional[float] = None
    reason: str = ""

    @property
    def pnl_pct(self) -> float:
        if self.exit is None:
            return 0.0
        sign = 1 if self.side == "long" else -1
        return sign * (self.exit - self.entry) / self.entry * 100 - FEE_RT_PCT

    @property
    def pnl_usd(self) -> float:
        return self.pnl_pct / 100 * SIZE_USD


def simulate_trade(price_df: pd.DataFrame, entry_ts: pd.Timestamp, side: str,
                   hold_hrs: int, sl_pct: float, tp_pct: float) -> Optional[Trade]:
    try:
        entry_idx = price_df.index.get_indexer([entry_ts], method="bfill")[0]
        if entry_idx < 0 or entry_idx >= len(price_df):
            return None
    except Exception:
        return None
    entry_row = price_df.iloc[entry_idx]
    entry = float(entry_row["close"])
    sl = entry * (1 - sl_pct/100) if side == "long" else entry * (1 + sl_pct/100)
    tp = entry * (1 + tp_pct/100) if side == "long" else entry * (1 - tp_pct/100)
    trade = Trade(entry_ts=entry_row.name, side=side, entry=entry)
    end_idx = min(entry_idx + hold_hrs * 60, len(price_df) - 1)
    for i in range(entry_idx + 1, end_idx + 1):
        bar = price_df.iloc[i]
        hi, lo = float(bar["high"]), float(bar["low"])
        if side == "long":
            if lo <= sl: trade.exit_ts=bar.name; trade.exit=sl; trade.reason="SL"; return trade
            if hi >= tp: trade.exit_ts=bar.name; trade.exit=tp; trade.reason="TP"; return trade
        else:
            if hi >= sl: trade.exit_ts=bar.name; trade.exit=sl; trade.reason="SL"; return trade
            if lo <= tp: trade.exit_ts=bar.name; trade.exit=tp; trade.reason="TP"; return trade
    last = price_df.iloc[end_idx]
    trade.exit_ts=last.name; trade.exit=float(last["close"]); trade.reason="timeout"
    return trade


def trades_metrics(trades: list[Trade], folds_starts: list[pd.Timestamp]) -> dict:
    if not trades:
        return {"n": 0, "pnl_usd": 0, "pf": 0, "wr": 0, "avg": 0, "max_dd": 0,
                "pos_folds": "0/0", "fold_pnls": ""}
    pnls = [t.pnl_usd for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    wr = len(wins) / len(pnls) * 100
    pf = sum(wins) / abs(sum(losses)) if losses else 99.0
    cum = np.cumsum(pnls)
    max_dd = (np.maximum.accumulate(cum) - cum).max() if len(cum) else 0
    fold_pnls = []
    for i, fold_start in enumerate(folds_starts):
        fold_end = folds_starts[i+1] if i+1 < len(folds_starts) else trades[-1].entry_ts + pd.Timedelta(days=1)
        fp = sum(t.pnl_usd for t in trades if fold_start <= t.entry_ts < fold_end)
        fold_pnls.append(fp)
    pos_folds = sum(1 for fp in fold_pnls if fp > 0)
    return {
        "n": len(pnls), "pnl_usd": round(sum(pnls), 1),
        "pf": round(pf, 2), "wr": round(wr, 1),
        "avg": round(np.mean(pnls), 2),
        "max_dd": round(max_dd, 1),
        "pos_folds": f"{pos_folds}/{len(fold_pnls)}",
        "fold_pnls": ";".join(f"{fp:.0f}" for fp in fold_pnls),
    }


# ───────────────────── Sweep with regime gates ─────────────────────

def run_sweep(price_df_1m: pd.DataFrame, liq_df: pd.DataFrame):
    # Pre-compute regime indicators on 1h
    df_1h = resample_1h(price_df_1m)
    adx_series = adx_h1(df_1h, period=14)
    ema50 = ema(df_1h["close"], 50)
    ema200 = ema(df_1h["close"], 200)
    trend_up = ema50 > ema200  # True = uptrend bias
    # Index for quick lookup at any 1m ts
    adx_1m = adx_series.reindex(price_df_1m.index, method="ffill").fillna(0)
    trend_up_1m = trend_up.reindex(price_df_1m.index, method="ffill").fillna(False)

    folds_starts = pd.date_range(liq_df.index[0], liq_df.index[-1], periods=N_FOLDS+1)[:-1].tolist()
    results = []

    # Best base configs from previous sweep:
    base_configs = [
        # (casc_side, thr, win, trade_side, hold, sl, tp)
        ("long",  7,  3, "long",  24, 2.0, 2.0),
        ("long",  7,  3, "long",  12, 2.0, 2.0),
        ("long", 10,  3, "long",  24, 2.0, 2.0),
        ("long", 10,  5, "long",  24, 2.0, 2.0),
        ("long",  5,  3, "long",  24, 2.0, 2.0),
        # SHORT zerocomos to test
        ("short", 5, 3, "short", 12, 2.0, 2.0),
        ("short", 5, 3, "short", 24, 2.0, 2.0),
        ("short", 7, 3, "short", 12, 2.0, 2.0),
        ("short", 7, 3, "short", 24, 2.0, 2.0),
        ("short", 7, 5, "short", 24, 2.0, 2.0),
        ("short", 10, 3, "short", 24, 2.0, 2.0),
        # Counter-trade: LONG on SHORT cascade (shorts squeeze → up)
        ("short", 5, 3, "long", 12, 2.0, 2.0),
        ("short", 7, 3, "long", 12, 2.0, 2.0),
        # Counter: SHORT on LONG cascade (continuation down)
        ("long", 5, 3, "short", 4, 1.0, 1.0),
        ("long", 7, 3, "short", 4, 1.0, 1.0),
    ]

    # Regime filters to try
    regime_filters = [
        ("none",          lambda adx, up: True),
        ("adx_lt_20",     lambda adx, up: adx < 20),
        ("adx_lt_25",     lambda adx, up: adx < 25),
        ("adx_lt_30",     lambda adx, up: adx < 30),
        ("adx_gt_20",     lambda adx, up: adx > 20),
        ("trend_up",      lambda adx, up: up),
        ("trend_down",    lambda adx, up: not up),
        ("trend_up_adx20", lambda adx, up: up and adx < 20),
        ("trend_up_adx25", lambda adx, up: up and adx < 25),
        ("trend_down_adx25", lambda adx, up: (not up) and adx < 25),
    ]

    # Pre-detect cascades per (threshold, window)
    cascades_cache: dict[tuple, list] = {}
    needed_thr_win = set((c[1], c[2]) for c in base_configs)
    for thr, win in needed_thr_win:
        cascades_cache[(thr, win)] = detect_cascades(liq_df, threshold_btc=thr, window_min=win)
        print(f"  detected {len(cascades_cache[(thr, win)])} cascades for thr={thr}BTC win={win}min",
              file=sys.stderr)

    total = len(base_configs) * len(regime_filters)
    print(f"\nRunning {total} (config × regime) combos...", file=sys.stderr)
    done = 0

    for cfg in base_configs:
        casc_side, thr, win, trade_side, hold, sl, tp = cfg
        all_cascades = cascades_cache[(thr, win)]
        side_cascades = [c for c in all_cascades if c[1] == casc_side]

        for filter_name, filter_fn in regime_filters:
            # Filter cascades by regime at entry ts
            filtered_ts = []
            for ts, _, _ in side_cascades:
                # Get adx/trend at this ts
                try:
                    pos = price_df_1m.index.get_indexer([ts], method="ffill")[0]
                    if pos < 0:
                        continue
                    a = float(adx_1m.iloc[pos])
                    u = bool(trend_up_1m.iloc[pos])
                    if filter_fn(a, u):
                        filtered_ts.append(ts)
                except Exception:
                    continue

            trades = []
            for ts in filtered_ts:
                t = simulate_trade(price_df_1m, ts, trade_side, hold, sl, tp)
                if t and t.exit is not None:
                    trades.append(t)
            m = trades_metrics(trades, folds_starts)
            results.append({
                "casc_side": casc_side, "thr_btc": thr, "win_min": win,
                "trade_side": trade_side, "hold_h": hold,
                "sl_pct": sl, "tp_pct": tp,
                "regime_filter": filter_name,
                **m,
            })
            done += 1
            if done % 30 == 0:
                print(f"  ...{done}/{total}", file=sys.stderr)

    return results


def write_results(results: list[dict]):
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(results)
    df.to_csv(OUT_CSV, index=False)
    print(f"\nResults CSV: {OUT_CSV}", file=sys.stderr)

    df["_pos"] = df["pos_folds"].astype(str).str.split("/").str[0].astype(int)
    df["_pf_num"] = pd.to_numeric(df["pf"], errors="coerce")

    print(f"\n=== TOP-15 BY PF (n>=30, pos_folds>=3/4) ===", file=sys.stderr)
    filt = df[(df["n"] >= 30) & (df["_pos"] >= 3)]
    if not filt.empty:
        top = filt.sort_values("_pf_num", ascending=False).head(15)
        print(top.to_string(index=False), file=sys.stderr)
    else:
        print("(no candidates with n>=30 & pos_folds>=3/4)", file=sys.stderr)

    print(f"\n=== TOP-10 4/4 FOLDS (n>=20) ===", file=sys.stderr)
    perfect = df[(df["n"] >= 20) & (df["_pos"] >= 4)]
    if not perfect.empty:
        top4 = perfect.sort_values("_pf_num", ascending=False).head(10)
        print(top4.to_string(index=False), file=sys.stderr)
    else:
        print("(no 4/4 folds candidates with n>=20)", file=sys.stderr)

    print(f"\n=== SHORT-side results (n>=20) ===", file=sys.stderr)
    shorts = df[(df["trade_side"] == "short") & (df["n"] >= 20)]
    if not shorts.empty:
        print(shorts.sort_values("_pf_num", ascending=False).head(10).to_string(index=False), file=sys.stderr)
    else:
        print("(no SHORT-side trades with n>=20)", file=sys.stderr)


def main():
    price_df = load_price()
    liq_df = load_liquidations()
    price_df = price_df.loc[liq_df.index[0]:liq_df.index[-1]]
    print(f"Period: {liq_df.index[0]} -> {liq_df.index[-1]}", file=sys.stderr)
    print(f"Price 1m bars: {len(price_df):,}", file=sys.stderr)
    print(f"Liq events: {len(liq_df):,}", file=sys.stderr)

    results = run_sweep(price_df, liq_df)
    write_results(results)
    print("\nDONE.", file=sys.stderr)


if __name__ == "__main__":
    main()
