"""Signal backtest harness — measure edge of indicator-based signals.

MVP: RSI bearish/bullish divergence on 1h. If numbers look reasonable,
extend to MFI, OBV, CMF, MACD-hist, Stoch + market structure.

Usage:
    python tools/backtest_signals.py
    python tools/backtest_signals.py --csv backtests/frozen/BTCUSDT_1h_2y.csv
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

DEFAULT_CSV = Path("backtests/frozen/BTCUSDT_1h_2y.csv")
PIVOT_LOOKBACK = 5          # bars on each side for pivot detection
DIV_WINDOW = 30             # max bars between two pivots forming a divergence
RSI_PERIOD = 14
WIN_BAR_THRESHOLDS = {"WR": 55.0, "PF": 1.30, "N": 50}


# ─────────────────────── indicators ───────────────────────

def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def mfi(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, period: int = 14) -> pd.Series:
    typical = (high + low + close) / 3.0
    raw_mf = typical * volume
    pos_mf = raw_mf.where(typical > typical.shift(1), 0.0)
    neg_mf = raw_mf.where(typical < typical.shift(1), 0.0)
    pos_sum = pos_mf.rolling(period).sum()
    neg_sum = neg_mf.rolling(period).sum()
    ratio = pos_sum / neg_sum.replace(0, np.nan)
    return 100 - (100 / (1 + ratio))


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = np.sign(close.diff()).fillna(0)
    return (direction * volume).cumsum()


def cmf(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, period: int = 20) -> pd.Series:
    hl = (high - low).replace(0, np.nan)
    mfm = ((close - low) - (high - close)) / hl
    mfv = mfm * volume
    return mfv.rolling(period).sum() / volume.rolling(period).sum()


def macd_hist(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.Series:
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line - signal_line


def stoch(high: pd.Series, low: pd.Series, close: pd.Series, k_period: int = 14, d_period: int = 3) -> pd.Series:
    """Return %K (smoothed not applied — we use raw %K for pivot symmetry)."""
    lowest = low.rolling(k_period).min()
    highest = high.rolling(k_period).max()
    rng = (highest - lowest).replace(0, np.nan)
    k = (close - lowest) / rng * 100.0
    return k.rolling(d_period).mean()  # smoothed %K (=%D)


# ─────────────────────── pivots ───────────────────────

def find_pivots(series: pd.Series, lookback: int = PIVOT_LOOKBACK) -> tuple[pd.Series, pd.Series]:
    """Return (pivot_high_mask, pivot_low_mask). True only at confirmed pivots.

    A bar is a pivot high iff it's the strict max in [i-lookback, i+lookback].
    Symmetric for lows. Pivots are confirmed `lookback` bars later (no lookahead
    in real-time use — we only register pivot at bar i+lookback).
    """
    arr = series.values
    n = len(arr)
    high_mask = np.zeros(n, dtype=bool)
    low_mask = np.zeros(n, dtype=bool)
    for i in range(lookback, n - lookback):
        window = arr[i - lookback : i + lookback + 1]
        if arr[i] == window.max() and (window == arr[i]).sum() == 1:
            high_mask[i] = True
        if arr[i] == window.min() and (window == arr[i]).sum() == 1:
            low_mask[i] = True
    return pd.Series(high_mask, index=series.index), pd.Series(low_mask, index=series.index)


# ─────────────────────── divergence detector ───────────────────────

@dataclass
class Signal:
    bar_idx: int                        # confirmation bar (second pivot + lookback)
    ts: int
    direction: str                      # "bearish" or "bullish"
    price: float
    confluence: int                     # count of indicators showing divergence
    agreeing_indicators: tuple[str, ...]
    prev_pivot_idx: int
    prev_pivot_price: float


def _nearest_pivot_in_window(
    pivot_indices: list[int], target_idx: int, tolerance: int,
) -> int | None:
    """Return pivot_idx within ±tolerance of target_idx, nearest if multiple."""
    best = None
    best_dist = tolerance + 1
    for pi in pivot_indices:
        d = abs(pi - target_idx)
        if d <= tolerance and d < best_dist:
            best = pi
            best_dist = d
    return best


def _check_indicator_pivot_divergence(
    indicator: pd.Series,
    indicator_pivots: tuple[list[int], list[int]],   # (highs, lows)
    prev_price_idx: int,
    cur_price_idx: int,
    direction: str,
    tolerance: int,
) -> bool:
    """STRICT divergence: indicator must have its OWN pivot near each price pivot,
    AND the indicator pivot values must move in the opposite direction to price.

    bearish (price HH): indicator must have a pivot-high near both bars and
                         second indicator-high < first indicator-high.
    bullish (price LL): indicator must have a pivot-low near both bars and
                         second indicator-low > first indicator-low.
    """
    ind_highs, ind_lows = indicator_pivots
    pivots = ind_highs if direction == "bearish" else ind_lows

    prev_pi = _nearest_pivot_in_window(pivots, prev_price_idx, tolerance)
    cur_pi = _nearest_pivot_in_window(pivots, cur_price_idx, tolerance)
    if prev_pi is None or cur_pi is None:
        return False

    prev_val = indicator.iloc[prev_pi]
    cur_val = indicator.iloc[cur_pi]
    if pd.isna(prev_val) or pd.isna(cur_val):
        return False
    if direction == "bearish":
        return cur_val < prev_val
    return cur_val > prev_val


def detect_multi_divergences(
    df: pd.DataFrame,
    indicators: dict[str, pd.Series],
    window: int = DIV_WINDOW,
    lookback: int = PIVOT_LOOKBACK,
    pivot_tolerance: int = 3,
) -> list[Signal]:
    """STRICT regular divergences: each agreeing indicator must have its own
    pivot near both price pivots (within `pivot_tolerance` bars).

    This restores the MVP-grade strictness — a price HH coupled with an
    indicator-pivot LH at the same bars, not just a lower indicator value.
    """
    price_high_mask, _ = find_pivots(df["high"], lookback)
    _, price_low_mask = find_pivots(df["low"], lookback)
    price_highs = df.index[price_high_mask].tolist()
    price_lows = df.index[price_low_mask].tolist()

    # Pre-compute pivots for every indicator once.
    indicator_pivots: dict[str, tuple[list[int], list[int]]] = {}
    for name, ind in indicators.items():
        ph_mask, pl_mask = find_pivots(ind, lookback)
        indicator_pivots[name] = (
            ind.index[ph_mask].tolist(),
            ind.index[pl_mask].tolist(),
        )

    signals: list[Signal] = []

    for direction, price_pivots, price_col in (
        ("bearish", price_highs, "high"),
        ("bullish", price_lows, "low"),
    ):
        for i in range(1, len(price_pivots)):
            cur_idx = price_pivots[i]
            prev_idx = price_pivots[i - 1]
            if cur_idx - prev_idx > window:
                continue
            cur_price = df[price_col].iloc[cur_idx]
            prev_price = df[price_col].iloc[prev_idx]
            if direction == "bearish" and cur_price <= prev_price:
                continue
            if direction == "bullish" and cur_price >= prev_price:
                continue
            agreeing = tuple(
                name for name, ind in indicators.items()
                if _check_indicator_pivot_divergence(
                    ind, indicator_pivots[name],
                    prev_idx, cur_idx, direction, pivot_tolerance,
                )
            )
            if not agreeing:
                continue
            conf_idx = cur_idx + lookback
            if conf_idx >= len(df):
                continue
            signals.append(Signal(
                bar_idx=conf_idx,
                ts=int(df["ts"].iloc[conf_idx]),
                direction=direction,
                price=float(df["close"].iloc[conf_idx]),
                confluence=len(agreeing),
                agreeing_indicators=agreeing,
                prev_pivot_idx=prev_idx,
                prev_pivot_price=float(prev_price),
            ))

    signals.sort(key=lambda s: s.bar_idx)
    return signals


# ─────────────────────── market structure (BoS) ───────────────────────

@dataclass
class StructurePivot:
    bar_idx: int
    price: float
    kind: str  # "H" (high) or "L" (low)
    label: str | None = None  # "HH", "HL", "LH", "LL"


def label_structure(df: pd.DataFrame, lookback: int = PIVOT_LOOKBACK) -> list[StructurePivot]:
    """Walk price pivots in time order; label each as HH/HL/LH/LL relative to
    the previous same-kind pivot."""
    high_mask, _ = find_pivots(df["high"], lookback)
    _, low_mask = find_pivots(df["low"], lookback)

    raw: list[StructurePivot] = []
    for idx in df.index:
        if high_mask.iloc[idx]:
            raw.append(StructurePivot(idx, float(df["high"].iloc[idx]), "H"))
        if low_mask.iloc[idx]:
            raw.append(StructurePivot(idx, float(df["low"].iloc[idx]), "L"))
    raw.sort(key=lambda p: p.bar_idx)

    last_high: StructurePivot | None = None
    last_low: StructurePivot | None = None
    for p in raw:
        if p.kind == "H":
            if last_high is None:
                p.label = "H?"
            else:
                p.label = "HH" if p.price > last_high.price else "LH"
            last_high = p
        else:
            if last_low is None:
                p.label = "L?"
            else:
                p.label = "HL" if p.price > last_low.price else "LL"
            last_low = p
    return raw


def detect_bos_signals(df: pd.DataFrame, lookback: int = PIVOT_LOOKBACK) -> list[Signal]:
    """Break of Structure: when price closes through the most recent
    structural pivot in the opposite direction.

    Bullish BoS: close > most-recent LH (downtrend swing high broken upward).
    Bearish BoS: close < most-recent HL (uptrend swing low broken downward).

    Confirmation = bar where the close prints; entry = same close.
    """
    pivots = label_structure(df, lookback)
    closes = df["close"].values
    signals: list[Signal] = []

    last_LH: StructurePivot | None = None
    last_HL: StructurePivot | None = None

    used_LH_idx = -1
    used_HL_idx = -1

    for i, p in enumerate(pivots):
        # Pivot becomes "live" only after lookback bars (no lookahead).
        live_at = p.bar_idx + lookback
        if live_at >= len(df):
            continue

        # Check broken structure on every bar between this pivot becoming live
        # and the next pivot's live point.
        next_live = (
            pivots[i + 1].bar_idx + lookback
            if i + 1 < len(pivots) else len(df)
        )

        if p.label == "LH":
            last_LH = p
        elif p.label == "HL":
            last_HL = p

        for bar in range(live_at, min(next_live, len(df))):
            close = closes[bar]
            # Bullish BoS: close above an unused LH.
            if last_LH is not None and last_LH.bar_idx > used_LH_idx and close > last_LH.price:
                signals.append(Signal(
                    bar_idx=bar,
                    ts=int(df["ts"].iloc[bar]),
                    direction="bullish",
                    price=float(close),
                    confluence=1,
                    agreeing_indicators=("BoS",),
                    prev_pivot_idx=last_LH.bar_idx,
                    prev_pivot_price=last_LH.price,
                ))
                used_LH_idx = last_LH.bar_idx
            # Bearish BoS: close below an unused HL.
            if last_HL is not None and last_HL.bar_idx > used_HL_idx and close < last_HL.price:
                signals.append(Signal(
                    bar_idx=bar,
                    ts=int(df["ts"].iloc[bar]),
                    direction="bearish",
                    price=float(close),
                    confluence=1,
                    agreeing_indicators=("BoS",),
                    prev_pivot_idx=last_HL.bar_idx,
                    prev_pivot_price=last_HL.price,
                ))
                used_HL_idx = last_HL.bar_idx

    signals.sort(key=lambda s: s.bar_idx)
    return signals


# ─────────────────────── regime filter (trend / range) ───────────────────────

def compute_regime(df: pd.DataFrame, ema_fast: int = 50, ema_slow: int = 200) -> pd.Series:
    """Simple regime tag per bar:
       'trend_up'   if ema_fast > ema_slow AND close > ema_fast
       'trend_down' if ema_fast < ema_slow AND close < ema_fast
       'range'      otherwise
    """
    fast = df["close"].ewm(span=ema_fast, adjust=False).mean()
    slow = df["close"].ewm(span=ema_slow, adjust=False).mean()
    out = pd.Series("range", index=df.index, dtype=object)
    out[(fast > slow) & (df["close"] > fast)] = "trend_up"
    out[(fast < slow) & (df["close"] < fast)] = "trend_down"
    return out


# ─────────────────────── forward-return scoring ───────────────────────

def score_signals(
    df: pd.DataFrame,
    signals: list[Signal],
    horizons: list[int],
    regime_series: pd.Series | None = None,
    sl_pct: float = 1.5,
    tp_pct: float = 3.0,
    sltp_max_bars: int = 24,
) -> pd.DataFrame:
    """For each signal: direction-aware fixed-horizon return + first-touch SL/TP exit."""
    rows = []
    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values
    n = len(closes)

    for s in signals:
        entry = s.price
        row = {
            "bar_idx": s.bar_idx,
            "ts": s.ts,
            "direction": s.direction,
            "entry": entry,
            "confluence": s.confluence,
            "agreeing": "+".join(s.agreeing_indicators),
            "regime": regime_series.iloc[s.bar_idx] if regime_series is not None else "n/a",
        }
        for h in horizons:
            future_idx = s.bar_idx + h
            if future_idx >= n:
                row[f"ret_{h}h"] = np.nan
                continue
            future_price = closes[future_idx]
            if s.direction == "bearish":
                ret = (entry - future_price) / entry * 100.0
            else:
                ret = (future_price - entry) / entry * 100.0
            row[f"ret_{h}h"] = ret

        # SL/TP first-touch exit (bullish: TP=entry+x%, SL=entry-y%; bearish: mirrored).
        if s.direction == "bullish":
            sl_price = entry * (1 - sl_pct / 100.0)
            tp_price = entry * (1 + tp_pct / 100.0)
        else:
            sl_price = entry * (1 + sl_pct / 100.0)
            tp_price = entry * (1 - tp_pct / 100.0)

        exit_ret = None
        exit_reason = None
        exit_bar = None
        end_bar = min(s.bar_idx + sltp_max_bars, n - 1)
        for b in range(s.bar_idx + 1, end_bar + 1):
            hi = highs[b]
            lo = lows[b]
            if s.direction == "bullish":
                if hi >= tp_price:
                    exit_ret, exit_reason, exit_bar = tp_pct, "TP", b
                    break
                if lo <= sl_price:
                    exit_ret, exit_reason, exit_bar = -sl_pct, "SL", b
                    break
            else:
                if lo <= tp_price:
                    exit_ret, exit_reason, exit_bar = tp_pct, "TP", b
                    break
                if hi >= sl_price:
                    exit_ret, exit_reason, exit_bar = -sl_pct, "SL", b
                    break
        if exit_ret is None:
            close_at_exit = closes[end_bar]
            if s.direction == "bullish":
                exit_ret = (close_at_exit - entry) / entry * 100.0
            else:
                exit_ret = (entry - close_at_exit) / entry * 100.0
            exit_reason = "TIME"
            exit_bar = end_bar
        row["sltp_ret"] = exit_ret
        row["sltp_reason"] = exit_reason
        row["sltp_bars"] = exit_bar - s.bar_idx

        rows.append(row)
    return pd.DataFrame(rows)


# ─────────────────────── metrics ───────────────────────

def compute_metrics(returns: pd.Series) -> dict:
    """Win rate, profit factor, mean, sample size for a returns series."""
    valid = returns.dropna()
    if len(valid) == 0:
        return {"N": 0, "WR_pct": np.nan, "PF": np.nan, "mean_pct": np.nan, "median_pct": np.nan}
    wins = valid[valid > 0]
    losses = valid[valid <= 0]
    wr = len(wins) / len(valid) * 100.0
    gross_win = wins.sum()
    gross_loss = -losses.sum()
    pf = gross_win / gross_loss if gross_loss > 0 else np.inf
    return {
        "N": len(valid),
        "WR_pct": round(wr, 2),
        "PF": round(pf, 3),
        "mean_pct": round(valid.mean(), 3),
        "median_pct": round(valid.median(), 3),
    }


def edge_verdict(metrics: dict, sample_thr: int = WIN_BAR_THRESHOLDS["N"]) -> str:
    if metrics["N"] < sample_thr:
        return f"INSUFFICIENT (N={metrics['N']} < {sample_thr})"
    wr_ok = metrics["WR_pct"] >= WIN_BAR_THRESHOLDS["WR"]
    pf_ok = metrics["PF"] >= WIN_BAR_THRESHOLDS["PF"]
    if wr_ok and pf_ok:
        return "EDGE"
    if not wr_ok and not pf_ok:
        return "NO EDGE"
    if wr_ok:
        return f"PARTIAL (WR ok, PF {metrics['PF']:.2f} below {WIN_BAR_THRESHOLDS['PF']})"
    return f"PARTIAL (PF ok, WR {metrics['WR_pct']:.1f}% below {WIN_BAR_THRESHOLDS['WR']}%)"


# ─────────────────────── timeframe resampling ───────────────────────

def _resample_4h(df_1h: pd.DataFrame) -> pd.DataFrame:
    """Resample 1h OHLCV to 4h. Aligns on UTC midnight via ts (ms)."""
    g = df_1h.copy()
    g["bucket"] = g["ts"] // (4 * 60 * 60 * 1000)
    out = g.groupby("bucket").agg(
        ts=("ts", "first"),
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    ).reset_index(drop=True)
    return out


# ─────────────────────── runner ───────────────────────

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--out", type=Path, default=Path("tools/backtest_signals_out.csv"))
    args = parser.parse_args()

    if not args.csv.exists():
        print(f"ERROR: CSV not found: {args.csv}")
        return 1

    print(f"Loading {args.csv}...")
    df = pd.read_csv(args.csv)
    print(f"  {len(df)} bars, ts {df['ts'].iloc[0]} -> {df['ts'].iloc[-1]}")
    df = df.reset_index(drop=True)

    # Resample 1h → 4h for cross-TF analysis.
    df_4h = _resample_4h(df)
    print(f"  4h resample: {len(df_4h)} bars")

    horizons = [1, 4, 12]
    summary_rows: list[dict] = []

    def _add_summary(experiment: str, n_total: int, scored_df: pd.DataFrame) -> None:
        """Compute metrics for each horizon + sltp_ret on `scored_df` and append to summary."""
        for h in horizons:
            m = compute_metrics(scored_df[f"ret_{h}h"])
            summary_rows.append({
                "experiment": experiment,
                "metric": f"hold_{h}h",
                "N": m["N"],
                "WR%": m["WR_pct"],
                "PF": m["PF"],
                "mean%": m["mean_pct"],
                "verdict": edge_verdict(m),
            })
        if "sltp_ret" in scored_df.columns:
            m = compute_metrics(scored_df["sltp_ret"])
            summary_rows.append({
                "experiment": experiment,
                "metric": "SL/TP 1.5/3.0%",
                "N": m["N"],
                "WR%": m["WR_pct"],
                "PF": m["PF"],
                "mean%": m["mean_pct"],
                "verdict": edge_verdict(m),
            })

    def _build_indicators(d: pd.DataFrame) -> dict[str, pd.Series]:
        return {
            "RSI":   rsi(d["close"], RSI_PERIOD),
            "MFI":   mfi(d["high"], d["low"], d["close"], d["volume"], 14),
            "OBV":   obv(d["close"], d["volume"]),
            "CMF":   cmf(d["high"], d["low"], d["close"], d["volume"], 20),
            "MACDh": macd_hist(d["close"], 12, 26, 9),
            "Stoch": stoch(d["high"], d["low"], d["close"], 14, 3),
        }

    # ─── Experiment A: 1h multi-indicator strict divergence ───
    print("\n[1/4] 1h strict multi-indicator divergence...")
    inds_1h = _build_indicators(df)
    regime_1h = compute_regime(df, 50, 200)
    sigs_1h = detect_multi_divergences(df, inds_1h)
    print(f"  signals: {len(sigs_1h)}")
    scored_1h = score_signals(df, sigs_1h, horizons, regime_series=regime_1h)

    for direction in ("bullish", "bearish"):
        for min_conf in (1, 2, 3, 4):
            sub = scored_1h[(scored_1h["direction"] == direction) & (scored_1h["confluence"] >= min_conf)]
            if len(sub) >= 30:
                _add_summary(f"1h DIV {direction[:4]} conf>={min_conf}", len(sub), sub)

    # ─── Experiment B: 1h with regime filter ───
    print("[2/4] 1h divergence + regime filter...")
    for direction, want_regime in (("bullish", "trend_up"), ("bullish", "range"), ("bearish", "trend_down"), ("bearish", "range")):
        sub = scored_1h[
            (scored_1h["direction"] == direction)
            & (scored_1h["confluence"] >= 1)
            & (scored_1h["regime"] == want_regime)
        ]
        if len(sub) >= 30:
            _add_summary(f"1h DIV {direction[:4]} +{want_regime}", len(sub), sub)

    # ─── Experiment C: 4h multi-indicator strict divergence ───
    print("[3/4] 4h strict multi-indicator divergence...")
    inds_4h = _build_indicators(df_4h)
    regime_4h = compute_regime(df_4h, 50, 200)
    sigs_4h = detect_multi_divergences(df_4h, inds_4h)
    print(f"  signals: {len(sigs_4h)}")
    # 4h horizons: same hour-counts but in 4h-bars. h=1 means 4h ahead.
    h4_horizons = [1, 3, 6]   # 4h, 12h, 24h ahead
    scored_4h = score_signals(df_4h, sigs_4h, h4_horizons, regime_series=regime_4h)
    for direction in ("bullish", "bearish"):
        for min_conf in (1, 2, 3):
            sub = scored_4h[(scored_4h["direction"] == direction) & (scored_4h["confluence"] >= min_conf)]
            if len(sub) >= 30:
                # Reuse summary helper but with 4h horizons rebadged.
                for h_4, label in zip(h4_horizons, ("4h", "12h", "24h")):
                    m = compute_metrics(sub[f"ret_{h_4}h"])
                    summary_rows.append({
                        "experiment": f"4h DIV {direction[:4]} conf>={min_conf}",
                        "metric": f"hold_{label}",
                        "N": m["N"],
                        "WR%": m["WR_pct"],
                        "PF": m["PF"],
                        "mean%": m["mean_pct"],
                        "verdict": edge_verdict(m),
                    })

    # ─── Experiment D: 1h Break of Structure (BoS) ───
    print("[4/4] 1h Break of Structure (BoS)...")
    sigs_bos = detect_bos_signals(df)
    print(f"  signals: {len(sigs_bos)}")
    scored_bos = score_signals(df, sigs_bos, horizons, regime_series=regime_1h)
    for direction in ("bullish", "bearish"):
        sub = scored_bos[scored_bos["direction"] == direction]
        if len(sub) >= 30:
            _add_summary(f"1h BoS {direction[:4]}", len(sub), sub)
    # BoS + regime filter
    for direction, want_regime in (("bullish", "trend_up"), ("bearish", "trend_down")):
        sub = scored_bos[(scored_bos["direction"] == direction) & (scored_bos["regime"] == want_regime)]
        if len(sub) >= 30:
            _add_summary(f"1h BoS {direction[:4]} +{want_regime}", len(sub), sub)

    # ─── Baseline ───
    print("baseline: random-entry buy & hold...")
    for h in horizons:
        future = df["close"].shift(-h)
        rets = (future - df["close"]) / df["close"] * 100.0
        m = compute_metrics(rets)
        summary_rows.append({
            "experiment": "BASELINE buy&hold",
            "metric": f"hold_{h}h",
            "N": m["N"],
            "WR%": m["WR_pct"],
            "PF": m["PF"],
            "mean%": m["mean_pct"],
            "verdict": "(reference)",
        })

    # ─── Print sorted summary ───
    summary = pd.DataFrame(summary_rows)
    summary = summary.sort_values(
        by=["PF", "WR%"], ascending=[False, False], kind="mergesort"
    ).reset_index(drop=True)

    print()
    print("=" * 100)
    print("FULL SUMMARY  (sorted by PF descending; PF>=1.30 AND WR>=55% AND N>=50 = EDGE)")
    print("=" * 100)
    print(f"  {'experiment':<35} | {'metric':<14} | {'N':>5} | {'WR%':>6} | {'PF':>6} | {'mean%':>7} | verdict")
    print("  " + "-" * 35 + " | " + "-" * 14 + " | " + "-" * 5 + " | " + "-" * 6 + " | " + "-" * 6 + " | " + "-" * 7 + " | -------")
    for _, r in summary.iterrows():
        pf_str = f"{r['PF']:.3f}" if not (isinstance(r["PF"], float) and np.isinf(r["PF"])) else "  inf"
        wr_str = f"{r['WR%']:.2f}" if not pd.isna(r["WR%"]) else "  n/a"
        mean_str = f"{r['mean%']:.3f}" if not pd.isna(r["mean%"]) else "  n/a"
        print(f"  {r['experiment']:<35} | {r['metric']:<14} | {r['N']:>5} | {wr_str:>6} | {pf_str:>6} | {mean_str:>7} | {r['verdict']}")

    # Save raw signals
    args.out.parent.mkdir(parents=True, exist_ok=True)
    scored_1h.to_csv(args.out, index=False)
    scored_4h.to_csv(args.out.with_suffix(".4h.csv"), index=False)
    scored_bos.to_csv(args.out.with_suffix(".bos.csv"), index=False)
    summary.to_csv(args.out.with_suffix(".summary.csv"), index=False)
    print(f"\n  Signals: {args.out} (+ .4h.csv + .bos.csv)")
    print(f"  Summary: {args.out.with_suffix('.summary.csv')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
