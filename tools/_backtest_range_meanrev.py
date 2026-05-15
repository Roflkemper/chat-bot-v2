"""Range-gated mean-reversion backtest для ручной торговли.

Идея: бот определяет 'сейчас ренж' и предлагает mean-revert сетапы.
Сильные тренды — пропускаем.

3 стратегии в одном прогоне:
  S1. POC reversion на 5m (распакован из 1m): пик объёма за окно W,
      при отклонении ≥X% от POC → trade к POC.
  S2. ADX-gated RSI reversion: если ADX<20 (ренж), RSI<30→LONG, RSI>70→SHORT.
  S3. Bollinger Band reversion: цена касается верх/нижней Bollinger (2σ),
      ADX-gate, hold N часов.

Period: BTC 1m, 2024-02 → 2026-05 (1.17M bars)
Output: docs/STRATEGIES/RANGE_MEANREV_BACKTEST.md + state/range_meanrev_results.csv

Запуск: python tools/_backtest_range_meanrev.py
"""
from __future__ import annotations

import csv
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "backtests" / "frozen" / "BTCUSDT_1m_2y.csv"
OUT_CSV = ROOT / "state" / "range_meanrev_results.csv"
OUT_DOC = ROOT / "docs" / "STRATEGIES" / "RANGE_MEANREV_BACKTEST.md"

# Fees: maker IN -0.0125% + taker OUT 0.075% + 0.02% slippage = ~0.165% round-trip
# Для conservative: оба taker = 0.15% round-trip + 0.02% slip = 0.17%
FEE_RT_PCT = 0.17  # round-trip fee + slippage (%)
SIZE_USD = 1000.0
INITIAL_BARS_WARMUP = 1440  # 1 day 1m bars

# Walk-forward fold size (~6 мес каждый)
N_FOLDS = 4


def load_1m_data() -> pd.DataFrame:
    print(f"Loading {DATA}...", file=sys.stderr)
    df = pd.read_csv(DATA)
    df.columns = [c.strip() for c in df.columns]
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df = df.set_index("ts").sort_index()
    df = df[~df.index.duplicated(keep="first")]
    print(f"  loaded {len(df):,} 1m bars from {df.index[0]} to {df.index[-1]}", file=sys.stderr)
    return df


def resample_5m(df_1m: pd.DataFrame) -> pd.DataFrame:
    return df_1m.resample("5min").agg({
        "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum",
    }).dropna()


def resample_1h(df_1m: pd.DataFrame) -> pd.DataFrame:
    return df_1m.resample("1h").agg({
        "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum",
    }).dropna()


# ───────────────────── Indicators ─────────────────────

def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average Directional Index (trend strength)."""
    high, low, close = df["high"], df["low"], df["close"]
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


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.where(delta > 0, 0).ewm(span=period, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(span=period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50)


def bollinger(close: pd.Series, period: int = 20, k: float = 2.0):
    mid = close.rolling(period).mean()
    sd = close.rolling(period).std(ddof=0)
    return mid, mid + k * sd, mid - k * sd


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


def simulate_hold_then_exit(df: pd.DataFrame, entry_idx: int, side: str,
                            hold_bars: int, sl_pct: float = 1.0,
                            tp_pct: Optional[float] = None) -> Trade:
    """Simulate from entry_idx for hold_bars, with optional SL/TP."""
    entry_row = df.iloc[entry_idx]
    entry = float(entry_row["close"])
    sl = entry * (1 - sl_pct/100) if side == "long" else entry * (1 + sl_pct/100)
    tp = entry * (1 + tp_pct/100) if (tp_pct and side == "long") \
        else entry * (1 - tp_pct/100) if (tp_pct and side == "short") else None
    trade = Trade(entry_ts=entry_row.name, side=side, entry=entry)

    end_idx = min(entry_idx + hold_bars, len(df) - 1)
    for i in range(entry_idx + 1, end_idx + 1):
        bar = df.iloc[i]
        hi, lo = float(bar["high"]), float(bar["low"])
        if side == "long":
            if lo <= sl:
                trade.exit_ts = bar.name; trade.exit = sl; trade.reason = "SL"; return trade
            if tp and hi >= tp:
                trade.exit_ts = bar.name; trade.exit = tp; trade.reason = "TP"; return trade
        else:
            if hi >= sl:
                trade.exit_ts = bar.name; trade.exit = sl; trade.reason = "SL"; return trade
            if tp and lo <= tp:
                trade.exit_ts = bar.name; trade.exit = tp; trade.reason = "TP"; return trade
    # timeout
    last = df.iloc[end_idx]
    trade.exit_ts = last.name; trade.exit = float(last["close"]); trade.reason = "timeout"
    return trade


def trades_metrics(trades: list[Trade], folds_starts: list[pd.Timestamp]) -> dict:
    if not trades:
        return {"n": 0, "pnl_usd": 0, "pf": 0, "wr": 0, "avg": 0, "max_dd": 0, "pos_folds": 0}
    pnls = [t.pnl_usd for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    wr = len(wins) / len(pnls) * 100
    pf = sum(wins) / abs(sum(losses)) if losses else float("inf")
    cum = np.cumsum(pnls)
    max_dd = (np.maximum.accumulate(cum) - cum).max() if len(cum) else 0
    # Per-fold pnl
    fold_pnls = []
    for i, fold_start in enumerate(folds_starts):
        fold_end = folds_starts[i+1] if i+1 < len(folds_starts) else trades[-1].entry_ts + pd.Timedelta(days=1)
        fp = sum(t.pnl_usd for t in trades if fold_start <= t.entry_ts < fold_end)
        fold_pnls.append(fp)
    pos_folds = sum(1 for fp in fold_pnls if fp > 0)
    return {
        "n": len(pnls), "pnl_usd": round(sum(pnls), 1),
        "pf": round(pf, 2) if pf != float("inf") else 99.0,
        "wr": round(wr, 1), "avg": round(np.mean(pnls), 2),
        "max_dd": round(max_dd, 1),
        "pos_folds": f"{pos_folds}/{len(fold_pnls)}",
    }


# ───────────────────── Strategies ─────────────────────

def strategy_poc_revert(df_5m: pd.DataFrame, *, window_hrs: int, distance_pct: float,
                        hold_hrs: int, side_filter: str = "both",
                        sl_pct: float = 1.0) -> list[Trade]:
    """POC reversion: при отклонении ≥X% от POC за окно W → trade к POC."""
    bars_window = window_hrs * 12  # 5m bars
    hold_bars = hold_hrs * 12
    trades = []

    closes = df_5m["close"].values
    highs = df_5m["high"].values
    lows = df_5m["low"].values
    volumes = df_5m["volume"].values

    for i in range(bars_window, len(df_5m) - hold_bars):
        # POC = close where volume was max in window
        w_vol = volumes[i-bars_window:i]
        w_close = closes[i-bars_window:i]
        poc_idx = w_vol.argmax()
        poc = w_close[poc_idx]

        current = closes[i]
        deviation_pct = (current - poc) / poc * 100

        if deviation_pct >= distance_pct and side_filter in ("both", "short_only"):
            t = simulate_hold_then_exit(df_5m, i, "short", hold_bars, sl_pct=sl_pct)
            trades.append(t)
        elif deviation_pct <= -distance_pct and side_filter in ("both", "long_only"):
            t = simulate_hold_then_exit(df_5m, i, "long", hold_bars, sl_pct=sl_pct)
            trades.append(t)
    return trades


def strategy_adx_rsi(df_5m: pd.DataFrame, *, adx_max: float, rsi_low: float,
                     rsi_high: float, hold_hrs: int, sl_pct: float = 1.0) -> list[Trade]:
    """ADX-gated RSI reversion: ренж если ADX<max, RSI<low→LONG, RSI>high→SHORT."""
    adx_series = adx(df_5m, period=14).values
    rsi_series = rsi(df_5m["close"], period=14).values
    hold_bars = hold_hrs * 12
    trades = []
    last_trade_idx = -1000
    cooldown_bars = hold_bars  # одна сделка за период удержания

    for i in range(50, len(df_5m) - hold_bars):
        if i - last_trade_idx < cooldown_bars:
            continue
        if adx_series[i] >= adx_max:
            continue  # trending — skip
        if rsi_series[i] <= rsi_low:
            t = simulate_hold_then_exit(df_5m, i, "long", hold_bars, sl_pct=sl_pct)
            trades.append(t)
            last_trade_idx = i
        elif rsi_series[i] >= rsi_high:
            t = simulate_hold_then_exit(df_5m, i, "short", hold_bars, sl_pct=sl_pct)
            trades.append(t)
            last_trade_idx = i
    return trades


def strategy_bollinger(df_5m: pd.DataFrame, *, bb_period: int, bb_k: float,
                       adx_max: float, hold_hrs: int, sl_pct: float = 1.0) -> list[Trade]:
    """Bollinger Band reversion: касание верхней/нижней + ADX-gate."""
    mid, upper, lower = bollinger(df_5m["close"], period=bb_period, k=bb_k)
    adx_series = adx(df_5m, period=14).values
    close = df_5m["close"].values
    hold_bars = hold_hrs * 12
    trades = []
    last_trade_idx = -1000
    cooldown_bars = hold_bars

    upper_v = upper.values
    lower_v = lower.values

    for i in range(max(bb_period, 50), len(df_5m) - hold_bars):
        if i - last_trade_idx < cooldown_bars:
            continue
        if adx_series[i] >= adx_max:
            continue
        if np.isnan(upper_v[i]) or np.isnan(lower_v[i]):
            continue
        if close[i] <= lower_v[i]:
            t = simulate_hold_then_exit(df_5m, i, "long", hold_bars, sl_pct=sl_pct)
            trades.append(t)
            last_trade_idx = i
        elif close[i] >= upper_v[i]:
            t = simulate_hold_then_exit(df_5m, i, "short", hold_bars, sl_pct=sl_pct)
            trades.append(t)
            last_trade_idx = i
    return trades


# ───────────────────── Sweep & report ─────────────────────

def run_sweep(df_5m: pd.DataFrame):
    folds_starts = pd.date_range(df_5m.index[0], df_5m.index[-1], periods=N_FOLDS+1)[:-1].tolist()
    results = []

    print("\n=== S1: POC reversion (5m) ===", file=sys.stderr)
    for w in [4, 8, 12, 24]:
        for d in [0.8, 1.2, 1.5, 2.0]:
            for h in [1, 2, 4, 6]:
                for side in ["both", "long_only", "short_only"]:
                    trades = strategy_poc_revert(df_5m, window_hrs=w, distance_pct=d,
                                                 hold_hrs=h, side_filter=side)
                    m = trades_metrics(trades, folds_starts)
                    results.append({
                        "strategy": "POC_revert", "w": w, "d_pct": d, "hold_h": h,
                        "side": side, **m,
                    })

    print("=== S2: ADX-gated RSI revert (5m) ===", file=sys.stderr)
    for adx_max in [18, 20, 25]:
        for rsi_low, rsi_high in [(25, 75), (30, 70), (35, 65)]:
            for hold_h in [2, 4, 6, 12]:
                for sl in [0.5, 1.0, 1.5]:
                    trades = strategy_adx_rsi(df_5m, adx_max=adx_max, rsi_low=rsi_low,
                                              rsi_high=rsi_high, hold_hrs=hold_h, sl_pct=sl)
                    m = trades_metrics(trades, folds_starts)
                    results.append({
                        "strategy": "ADX_RSI", "adx_max": adx_max,
                        "rsi_lo": rsi_low, "rsi_hi": rsi_high,
                        "hold_h": hold_h, "sl_pct": sl, **m,
                    })

    print("=== S3: Bollinger revert + ADX gate (5m) ===", file=sys.stderr)
    for bb_p in [20, 40, 60]:
        for bb_k in [1.5, 2.0, 2.5]:
            for adx_max in [20, 25]:
                for hold_h in [2, 4, 6]:
                    for sl in [0.5, 1.0, 1.5]:
                        trades = strategy_bollinger(df_5m, bb_period=bb_p, bb_k=bb_k,
                                                    adx_max=adx_max, hold_hrs=hold_h,
                                                    sl_pct=sl)
                        m = trades_metrics(trades, folds_starts)
                        results.append({
                            "strategy": "Bollinger", "bb_p": bb_p, "bb_k": bb_k,
                            "adx_max": adx_max, "hold_h": hold_h, "sl_pct": sl, **m,
                        })

    return results


def write_results(results: list[dict]):
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(results)
    df.to_csv(OUT_CSV, index=False)
    print(f"\nResults CSV: {OUT_CSV}", file=sys.stderr)
    print(f"\n=== TOP-15 BY PnL (all strategies) ===", file=sys.stderr)
    top = df.sort_values("pnl_usd", ascending=False).head(15)
    print(top.to_string(index=False), file=sys.stderr)

    print(f"\n=== TOP-10 BY PF (n>=50, pos_folds>=3/4) ===", file=sys.stderr)
    df["_pf_num"] = pd.to_numeric(df["pf"], errors="coerce")
    df["_pos"] = df["pos_folds"].astype(str).str.split("/").str[0].astype(int)
    filt = df[(df["n"] >= 50) & (df["_pos"] >= 3)]
    if not filt.empty:
        top_pf = filt.sort_values("_pf_num", ascending=False).head(10)
        print(top_pf.to_string(index=False), file=sys.stderr)
    else:
        print("(no candidates with n>=50 & pos_folds>=3/4)", file=sys.stderr)


def main():
    df_1m = load_1m_data()
    df_5m = resample_5m(df_1m)
    print(f"5m bars: {len(df_5m):,}", file=sys.stderr)
    results = run_sweep(df_5m)
    write_results(results)
    print("\nDONE. See state/range_meanrev_results.csv", file=sys.stderr)


if __name__ == "__main__":
    main()
