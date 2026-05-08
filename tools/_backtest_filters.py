"""15m backtest + funding filter + liquidations filter — one-off analysis script."""
from __future__ import annotations
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from backtest_signals import (  # noqa: E402
    rsi, mfi, obv, cmf, macd_hist, stoch,
    detect_multi_divergences, detect_bos_signals,
    score_signals, compute_metrics,
    PIVOT_LOOKBACK, RSI_PERIOD,
)


def build_indicators_with_delta(df: pd.DataFrame) -> dict[str, pd.Series]:
    hl = (df["high"] - df["low"]).replace(0, np.nan)
    mfv = ((df["close"] - df["low"]) - (df["high"] - df["close"])) / hl * df["volume"]
    return {
        "RSI":      rsi(df["close"], RSI_PERIOD),
        "MFI":      mfi(df["high"], df["low"], df["close"], df["volume"], 14),
        "OBV":      obv(df["close"], df["volume"]),
        "CMF":      cmf(df["high"], df["low"], df["close"], df["volume"], 20),
        "MACDh":    macd_hist(df["close"], 12, 26, 9),
        "Stoch":    stoch(df["high"], df["low"], df["close"], 14, 3),
        "DeltaCum": mfv.cumsum(),
    }


def print_metrics_row(label: str, n: int, scored: pd.DataFrame, horizons: list[int]) -> None:
    line = f"  {label:<22}  N={n:>3}  "
    for h in horizons:
        m = compute_metrics(scored[f"ret_{h}h"])
        pf = f"{m['PF']:.2f}" if not np.isinf(m["PF"]) else " inf"
        line += f"h{h}: WR={m['WR_pct']:>5.1f}% PF={pf:>5}  "
    print(line)


def run_15m() -> None:
    print("=" * 90)
    print("15m TIMEFRAME BACKTEST (BTCUSDT 2y)")
    print("=" * 90)
    df = pd.read_csv("backtests/frozen/BTCUSDT_15m_2y.csv")
    print(f"  bars: {len(df)}")
    inds = build_indicators_with_delta(df)
    sigs = detect_multi_divergences(df, inds)
    bull = [s for s in sigs if s.direction == "bullish" and s.confluence >= 2]
    horizons = [1, 4, 16, 48]   # 15m, 1h, 4h, 12h
    labels = ["15m", "1h", "4h", "12h"]
    print(f"\n  bull DIV conf>=2: N={len(bull)}")
    sc = score_signals(df, bull, horizons)
    for h, lab in zip(horizons, labels):
        m = compute_metrics(sc[f"ret_{h}h"])
        pf = f"{m['PF']:.2f}" if not np.isinf(m["PF"]) else " inf"
        print(f"    {lab:>4}: N={m['N']:>4} WR={m['WR_pct']:>5.1f}% PF={pf:>5} mean={m['mean_pct']:+.3f}%")

    bos_bars = {s.bar_idx for s in detect_bos_signals(df) if s.direction == "bullish"}
    for win in (10, 20, 30):
        confluent = [s for s in bull if any((s.bar_idx + o) in bos_bars for o in range(0, win + 1))]
        if not confluent:
            continue
        print(f"\n  bull DIV+BoS within +{win}bars (={win*15}min):  N={len(confluent)}")
        sc = score_signals(df, confluent, horizons)
        for h, lab in zip(horizons, labels):
            m = compute_metrics(sc[f"ret_{h}h"])
            pf = f"{m['PF']:.2f}" if not np.isinf(m["PF"]) else " inf"
            print(f"    {lab:>4}: N={m['N']:>4} WR={m['WR_pct']:>5.1f}% PF={pf:>5} mean={m['mean_pct']:+.3f}%")


def run_funding_filter() -> None:
    print("\n" + "=" * 90)
    print("FUNDING FILTER (1h, partial coverage 2025-03-01 -> 2026-03-31)")
    print("=" * 90)
    df = pd.read_csv("backtests/frozen/BTCUSDT_1h_2y.csv")
    inds = build_indicators_with_delta(df)
    sigs = detect_multi_divergences(df, inds)
    bull = [s for s in sigs if s.direction == "bullish" and s.confluence >= 2]
    bos_bars = {s.bar_idx for s in detect_bos_signals(df) if s.direction == "bullish"}
    confluent = [s for s in bull if any((s.bar_idx + o) in bos_bars for o in range(0, 11))]

    fund_path = Path("_recovery/restored/scripts/frozen/BTCUSDT/_combined_fundingRate.parquet")
    fund = pd.read_parquet(fund_path).sort_values("calc_time").reset_index(drop=True)
    fund_ms = fund["calc_time"].astype("int64") // 10**6

    def funding_at(ts_ms: int) -> float | None:
        idx = np.searchsorted(fund_ms.values, ts_ms, side="right") - 1
        if idx < 0:
            return None
        return float(fund["last_funding_rate"].iloc[idx])

    horizons = [1, 4, 12]

    def split_by_funding(signals):
        neg, pos, none, deep_neg = [], [], [], []
        for s in signals:
            f = funding_at(s.ts)
            if f is None:
                none.append(s)
            elif f < -0.0001:   # below -0.01% (deep negative)
                deep_neg.append(s)
                neg.append(s)
            elif f < 0:
                neg.append(s)
            else:
                pos.append(s)
        return neg, pos, none, deep_neg

    for setup_label, signals in [("DIV bull conf>=2", bull), ("DIV+BoS bull", confluent)]:
        print(f"\n  --- {setup_label} split by funding sign ---")
        neg, pos, none, deep_neg = split_by_funding(signals)
        for label, group in [
            ("ALL", signals),
            ("NEG funding", neg),
            ("DEEP NEG <-0.01%", deep_neg),
            ("POS funding", pos),
            ("no funding data", none),
        ]:
            if len(group) < 5:
                print(f"    {label:<22}  N={len(group):>3}  (skipped, <5 sample)")
                continue
            sc = score_signals(df, group, horizons)
            print_metrics_row(label, len(group), sc, horizons)


def run_liquidations_filter() -> None:
    print("\n" + "=" * 90)
    print("LIQUIDATIONS FILTER (4mo coverage Feb-Jun 2024, very small sample)")
    print("=" * 90)
    df = pd.read_csv("backtests/frozen/BTCUSDT_1h_2y.csv")
    inds = build_indicators_with_delta(df)
    sigs = detect_multi_divergences(df, inds)
    bull = [s for s in sigs if s.direction == "bullish" and s.confluence >= 2]

    liq = pd.read_parquet("data/historical/bybit_liquidations_2024.parquet")
    liq["ts_ms"] = liq["ts_ms"].astype("int64")
    liq_short_side = liq[liq["side"] == "Sell"]   # forced sells (long liqs) — capitulation, bullish reversal
    liq_short_arr = liq_short_side["ts_ms"].values
    liq_qty = liq_short_side["qty"].values

    liq_start_ms = int(liq["ts_ms"].min())
    liq_end_ms = int(liq["ts_ms"].max())
    in_window = [s for s in bull if liq_start_ms <= s.ts <= liq_end_ms]
    print(f"\n  bull DIV signals in liq coverage: {len(in_window)}")

    if not in_window:
        print("  No signals in coverage — skipping.")
        return

    def short_liq_qty_in_prior(ts_ms: int, prior_ms: int) -> float:
        start = ts_ms - prior_ms
        mask = (liq_short_arr >= start) & (liq_short_arr <= ts_ms)
        return float(liq_qty[mask].sum())

    def short_liq_count_in_prior(ts_ms: int, prior_ms: int) -> int:
        start = ts_ms - prior_ms
        mask = (liq_short_arr >= start) & (liq_short_arr <= ts_ms)
        return int(mask.sum())

    horizons = [1, 4, 12]

    print("\n  --- short-liq cascade in past 1h before signal ---")
    for cnt_threshold in (1, 3, 5, 10):
        with_cascade = [s for s in in_window if short_liq_count_in_prior(s.ts, 60 * 60 * 1000) >= cnt_threshold]
        if len(with_cascade) < 3:
            print(f"    >={cnt_threshold} liq events:  N={len(with_cascade)}  (too few)")
            continue
        sc = score_signals(df, with_cascade, horizons)
        print_metrics_row(f">={cnt_threshold} liq events in 1h", len(with_cascade), sc, horizons)

    print("\n  --- cumulative short-liq qty in past 1h before signal ---")
    for qty_threshold in (1.0, 5.0, 10.0):
        with_qty = [s for s in in_window if short_liq_qty_in_prior(s.ts, 60 * 60 * 1000) >= qty_threshold]
        if len(with_qty) < 3:
            print(f"    >={qty_threshold} BTC liq qty:  N={len(with_qty)}  (too few)")
            continue
        sc = score_signals(df, with_qty, horizons)
        print_metrics_row(f">={qty_threshold} BTC liq in 1h", len(with_qty), sc, horizons)


if __name__ == "__main__":
    run_15m()
    run_funding_filter()
    run_liquidations_filter()
