"""Multi-asset divergence confluence — backtest 2026-05-08.

Hypothesis: divergence signal is more reliable when BTC AND ETH show it
simultaneously (within a small time window). Tests:
  1. BTC standalone vs BTC-only-confirmed (baseline)
  2. ETH standalone (does our detector even work on ETH?)
  3. XRP standalone (smaller market, weaker signal expected)
  4. BTC AND ETH within ±X bars (confluence)

Single-asset metrics establish whether each asset has its own edge.
Confluence shows whether requiring both reduces false positives.
"""
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


def build_inds(df: pd.DataFrame) -> dict[str, pd.Series]:
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


def run_one(symbol: str, df: pd.DataFrame, label: str) -> dict:
    inds = build_inds(df)
    sigs = detect_multi_divergences(df, inds)
    bull = [s for s in sigs if s.direction == "bullish" and s.confluence >= 2]

    # Add BoS confluence
    bos_bars = {s.bar_idx for s in detect_bos_signals(df) if s.direction == "bullish"}
    confluent = [s for s in bull if any((s.bar_idx + o) in bos_bars for o in range(0, 11))]

    horizons = [1, 4, 12]
    out = {"symbol": symbol, "label": label}

    print(f"\n--- {label} ---")
    sub = score_signals(df, bull, horizons)
    print(f"  bull DIV conf>=2:  N={len(bull)}")
    for h in horizons:
        m = compute_metrics(sub[f"ret_{h}h"])
        pf_str = f"{m['PF']:.2f}" if not np.isinf(m["PF"]) else " inf"
        print(f"    h{h:>2}: WR={m['WR_pct']:>5.1f}% PF={pf_str:>5} mean={m['mean_pct']:+.3f}%")

    sub_bos = score_signals(df, confluent, horizons)
    print(f"  bull DIV+BoS within +10:  N={len(confluent)}")
    for h in horizons:
        m = compute_metrics(sub_bos[f"ret_{h}h"])
        pf_str = f"{m['PF']:.2f}" if not np.isinf(m["PF"]) else " inf"
        print(f"    h{h:>2}: WR={m['WR_pct']:>5.1f}% PF={pf_str:>5} mean={m['mean_pct']:+.3f}%")

    out["bull_signals"] = bull
    out["confluent_signals"] = confluent
    return out


def main() -> int:
    print("=" * 90)
    print("PER-SYMBOL DIVERGENCE EDGE (1h, 2y)")
    print("=" * 90)

    btc = pd.read_csv("backtests/frozen/BTCUSDT_1h_2y.csv").reset_index(drop=True)
    eth = pd.read_csv("backtests/frozen/ETHUSDT_1h_2y.csv").reset_index(drop=True)
    xrp = pd.read_csv("backtests/frozen/XRPUSDT_1h_2y.csv").reset_index(drop=True)

    btc_res = run_one("BTC", btc, "BTC")
    eth_res = run_one("ETH", eth, "ETH")
    xrp_res = run_one("XRP", xrp, "XRP")

    # Cross-asset confluence: BTC signal + ETH signal within +/- 4 bars (1h timeframe).
    # Also test BTC + XRP for completeness.
    print()
    print("=" * 90)
    print("CROSS-ASSET CONFLUENCE: BTC bull div AND companion bull div within +/- 4h")
    print("=" * 90)

    btc["dt"] = pd.to_datetime(btc["ts"], unit="ms", utc=True)
    eth["dt"] = pd.to_datetime(eth["ts"], unit="ms", utc=True)
    xrp["dt"] = pd.to_datetime(xrp["ts"], unit="ms", utc=True)

    def companion_signal_ts(companion_signals, companion_df, asof_dt, window_h=4):
        """Return True if companion has a bull-div signal within +/- window_h hours of asof_dt."""
        for s in companion_signals:
            sig_dt = pd.to_datetime(companion_df["ts"].iloc[s.bar_idx], unit="ms", utc=True)
            delta_h = abs((sig_dt - asof_dt).total_seconds() / 3600.0)
            if delta_h <= window_h:
                return True
        return False

    btc_bull = btc_res["bull_signals"]
    eth_bull = eth_res["bull_signals"]
    xrp_bull = xrp_res["bull_signals"]

    horizons = [1, 4, 12]

    for companion_label, companion_signals, companion_df in (
        ("BTC + ETH", eth_bull, eth),
        ("BTC + XRP", xrp_bull, xrp),
        ("BTC + ETH + XRP", None, None),  # special case: triple
    ):
        if companion_label == "BTC + ETH + XRP":
            confluent = []
            for s in btc_bull:
                bts = pd.to_datetime(btc["ts"].iloc[s.bar_idx], unit="ms", utc=True)
                if companion_signal_ts(eth_bull, eth, bts, 4) and companion_signal_ts(xrp_bull, xrp, bts, 4):
                    confluent.append(s)
        else:
            confluent = []
            for s in btc_bull:
                bts = pd.to_datetime(btc["ts"].iloc[s.bar_idx], unit="ms", utc=True)
                if companion_signal_ts(companion_signals, companion_df, bts, 4):
                    confluent.append(s)
        print(f"\n--- {companion_label} confluence (BTC bull DIV with companion within +/-4h) ---")
        if not confluent:
            print(f"  N=0  (no overlap)")
            continue
        sub = score_signals(btc, confluent, horizons)
        print(f"  N={len(confluent)} (vs BTC standalone N={len(btc_bull)}, ratio {len(confluent)/len(btc_bull)*100:.0f}%)")
        for h in horizons:
            m = compute_metrics(sub[f"ret_{h}h"])
            pf_str = f"{m['PF']:.2f}" if not np.isinf(m["PF"]) else " inf"
            print(f"    h{h:>2}: WR={m['WR_pct']:>5.1f}% PF={pf_str:>5} mean={m['mean_pct']:+.3f}%")

    return 0


if __name__ == "__main__":
    sys.exit(main())
