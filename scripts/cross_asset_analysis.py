"""Cross-asset analysis BTC / ETH / XRP — correlation, lead-lag, divergence rules.

Цель: измеримые торговые сигналы из взаимоотношений 3 инструментов.

3 типа анализа:
  1. Базовая корреляция (Pearson на 1h returns) — overall, последние 30/90/180 дней
  2. Lead-lag (cross-correlation на ±N лагах) — кто движется первым
  3. Divergence patterns как форвардные сигналы:
     - BTC up >X% & ETH/XRP flat → BTC откатит?
     - XRP solo pump (BTC спокоен) → fade?
     - Когда корреляция РАЗРЫВАЕТСЯ — что обычно бывает дальше

Output: state/cross_asset_analysis.json + state/cross_asset_findings.md
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _load(symbol: str) -> pd.DataFrame:
    df = pd.read_csv(ROOT / "backtests" / "frozen" / f"{symbol}_1h_2y.csv")
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df = df.set_index("ts").sort_index()[["close"]]
    df.columns = [symbol]
    return df


def _align_three() -> pd.DataFrame:
    """Inner-join BTC + ETH + XRP on common timestamps."""
    btc = _load("BTCUSDT")
    eth = _load("ETHUSDT")
    xrp = _load("XRPUSDT")
    df = btc.join([eth, xrp], how="inner")
    return df


def _returns(df: pd.DataFrame) -> pd.DataFrame:
    return np.log(df / df.shift(1)).dropna()


# ── 1. CORRELATION ─────────────────────────────────────────────────────

def correlation_windows(returns: pd.DataFrame) -> dict:
    """Pearson correlation on 1h returns, multiple windows."""
    end = returns.index.max()
    out = {}
    for label, days in [("30d", 30), ("90d", 90), ("180d", 180), ("365d", 365), ("all", 9999)]:
        r = returns[returns.index >= end - timedelta(days=days)]
        if len(r) < 100:
            continue
        c = r.corr().round(3)
        out[label] = {
            "n_bars": len(r),
            "BTC_ETH": float(c.loc["BTCUSDT", "ETHUSDT"]),
            "BTC_XRP": float(c.loc["BTCUSDT", "XRPUSDT"]),
            "ETH_XRP": float(c.loc["ETHUSDT", "XRPUSDT"]),
        }
    return out


def rolling_correlation(returns: pd.DataFrame, window_hours: int = 24 * 7) -> dict:
    """Rolling 1-week correlation — to find regime breaks."""
    btc_eth = returns["BTCUSDT"].rolling(window_hours).corr(returns["ETHUSDT"])
    btc_xrp = returns["BTCUSDT"].rolling(window_hours).corr(returns["XRPUSDT"])
    eth_xrp = returns["ETHUSDT"].rolling(window_hours).corr(returns["XRPUSDT"])
    return {
        "BTC_ETH": {"min": float(btc_eth.min()), "max": float(btc_eth.max()),
                    "mean": float(btc_eth.mean()), "median": float(btc_eth.median())},
        "BTC_XRP": {"min": float(btc_xrp.min()), "max": float(btc_xrp.max()),
                    "mean": float(btc_xrp.mean()), "median": float(btc_xrp.median())},
        "ETH_XRP": {"min": float(eth_xrp.min()), "max": float(eth_xrp.max()),
                    "mean": float(eth_xrp.mean()), "median": float(eth_xrp.median())},
        # Recent vs historical
        "current_BTC_ETH": float(btc_eth.dropna().iloc[-1]) if len(btc_eth.dropna()) else None,
        "current_BTC_XRP": float(btc_xrp.dropna().iloc[-1]) if len(btc_xrp.dropna()) else None,
        "current_ETH_XRP": float(eth_xrp.dropna().iloc[-1]) if len(eth_xrp.dropna()) else None,
    }


# ── 2. LEAD-LAG ─────────────────────────────────────────────────────────

def lead_lag(returns: pd.DataFrame, max_lag_hours: int = 6) -> dict:
    """Cross-correlation at ±N lag (in hours).
    Positive lag = X leads Y by lag hours.
    """
    out = {}
    pairs = [("BTCUSDT", "ETHUSDT"), ("BTCUSDT", "XRPUSDT"), ("ETHUSDT", "XRPUSDT")]
    for a, b in pairs:
        results = {}
        for lag in range(-max_lag_hours, max_lag_hours + 1):
            if lag < 0:
                # B leads A by |lag|
                shifted = returns[b].shift(-lag)
                c = returns[a].corr(shifted)
            else:
                shifted = returns[a].shift(lag)
                c = returns[b].corr(shifted)
            results[lag] = round(float(c), 4) if not pd.isna(c) else None

        # Find peak
        valid = {k: v for k, v in results.items() if v is not None}
        peak_lag = max(valid, key=lambda k: valid[k])
        out[f"{a}_{b}"] = {
            "by_lag_hours": results,
            "peak_lag_hours": peak_lag,
            "peak_corr": valid[peak_lag],
            "interpretation": (
                f"{a} leads {b} by {peak_lag}h (peak corr {valid[peak_lag]:.3f})"
                if peak_lag > 0 else
                f"{b} leads {a} by {abs(peak_lag)}h (peak corr {valid[peak_lag]:.3f})"
                if peak_lag < 0 else
                f"{a} and {b} synchronous (peak at lag=0, corr {valid[peak_lag]:.3f})"
            ),
        }
    return out


# ── 3. DIVERGENCE PATTERNS ─────────────────────────────────────────────

def divergence_patterns(df: pd.DataFrame, returns: pd.DataFrame) -> dict:
    """Look for cases:
       - BTC moves >|threshold|, but ETH/XRP do not (lag/disagree)
       - One asset moves solo
       - Then: what happens 4h / 24h later?
    """
    findings = {}

    # Pattern A: BTC moves >1% in 1h, ETH does <0.3%
    threshold_btc = 0.01  # 1%
    threshold_alt = 0.003

    # Returns are already log-1h
    pattern_a_up = (returns["BTCUSDT"] > threshold_btc) & (returns["ETHUSDT"].abs() < threshold_alt)
    pattern_a_down = (returns["BTCUSDT"] < -threshold_btc) & (returns["ETHUSDT"].abs() < threshold_alt)

    def _outcomes(mask: pd.Series, horizon_hours: int) -> dict:
        n = int(mask.sum())
        if n == 0:
            return {"n": 0}
        idx_pos = np.where(mask.values)[0]
        # close future returns
        outcomes_btc = []
        outcomes_eth = []
        outcomes_xrp = []
        for i in idx_pos:
            j = i + horizon_hours
            if j >= len(df):
                continue
            outcomes_btc.append(df["BTCUSDT"].iloc[j] / df["BTCUSDT"].iloc[i] - 1)
            outcomes_eth.append(df["ETHUSDT"].iloc[j] / df["ETHUSDT"].iloc[i] - 1)
            outcomes_xrp.append(df["XRPUSDT"].iloc[j] / df["XRPUSDT"].iloc[i] - 1)
        if not outcomes_btc:
            return {"n": 0}
        return {
            "n": len(outcomes_btc),
            "btc_mean_pct": round(float(np.mean(outcomes_btc)) * 100, 3),
            "btc_median_pct": round(float(np.median(outcomes_btc)) * 100, 3),
            "btc_pct_up": round(float(np.mean(np.array(outcomes_btc) > 0)) * 100, 1),
            "eth_mean_pct": round(float(np.mean(outcomes_eth)) * 100, 3),
            "eth_pct_up": round(float(np.mean(np.array(outcomes_eth) > 0)) * 100, 1),
            "xrp_mean_pct": round(float(np.mean(outcomes_xrp)) * 100, 3),
        }

    findings["pattern_A_btc_up_eth_flat"] = {
        "criterion": "BTC 1h-return > +1.0% AND ETH 1h-return |<| 0.3%",
        "outcome_4h_later": _outcomes(pattern_a_up, 4),
        "outcome_24h_later": _outcomes(pattern_a_up, 24),
    }
    findings["pattern_A_btc_down_eth_flat"] = {
        "criterion": "BTC 1h-return < -1.0% AND ETH 1h-return |<| 0.3%",
        "outcome_4h_later": _outcomes(pattern_a_down, 4),
        "outcome_24h_later": _outcomes(pattern_a_down, 24),
    }

    # Pattern B: XRP moves >2% in 1h while BTC does <0.5%
    threshold_xrp_solo = 0.02
    threshold_btc_quiet = 0.005
    pattern_b_up = (returns["XRPUSDT"] > threshold_xrp_solo) & (returns["BTCUSDT"].abs() < threshold_btc_quiet)
    pattern_b_down = (returns["XRPUSDT"] < -threshold_xrp_solo) & (returns["BTCUSDT"].abs() < threshold_btc_quiet)

    findings["pattern_B_xrp_solo_pump"] = {
        "criterion": "XRP 1h > +2.0% AND BTC 1h |<| 0.5%",
        "outcome_4h_later": _outcomes(pattern_b_up, 4),
        "outcome_24h_later": _outcomes(pattern_b_up, 24),
    }
    findings["pattern_B_xrp_solo_dump"] = {
        "criterion": "XRP 1h < -2.0% AND BTC 1h |<| 0.5%",
        "outcome_4h_later": _outcomes(pattern_b_down, 4),
        "outcome_24h_later": _outcomes(pattern_b_down, 24),
    }

    # Pattern C: ETH solo move while BTC quiet
    threshold_eth_solo = 0.015
    pattern_c_up = (returns["ETHUSDT"] > threshold_eth_solo) & (returns["BTCUSDT"].abs() < threshold_btc_quiet)
    pattern_c_down = (returns["ETHUSDT"] < -threshold_eth_solo) & (returns["BTCUSDT"].abs() < threshold_btc_quiet)

    findings["pattern_C_eth_solo_up"] = {
        "criterion": "ETH 1h > +1.5% AND BTC 1h |<| 0.5%",
        "outcome_4h_later": _outcomes(pattern_c_up, 4),
        "outcome_24h_later": _outcomes(pattern_c_up, 24),
    }
    findings["pattern_C_eth_solo_down"] = {
        "criterion": "ETH 1h < -1.5% AND BTC 1h |<| 0.5%",
        "outcome_4h_later": _outcomes(pattern_c_down, 4),
        "outcome_24h_later": _outcomes(pattern_c_down, 24),
    }

    return findings


# ── 4. BETA HEDGE RATIO ─────────────────────────────────────────────────

def beta_hedge_ratio(returns: pd.DataFrame) -> dict:
    """How much ETH/XRP move when BTC moves 1%."""
    btc = returns["BTCUSDT"]
    out = {}
    for sym in ["ETHUSDT", "XRPUSDT"]:
        # Simple OLS: r_alt = beta * r_btc
        beta = float(np.cov(returns[sym], btc, ddof=0)[0, 1] / np.var(btc, ddof=0))
        # When BTC moves +1% / -1% / -3% — what's expected alt move
        out[sym] = {
            "beta_full_period": round(beta, 3),
            "expected_move_for_btc_+1pct": f"{round(beta * 1, 2):+.2f}%",
            "expected_move_for_btc_-3pct": f"{round(beta * -3, 2):+.2f}%",
        }
    return out


def beta_recent(returns: pd.DataFrame, days: int = 30) -> dict:
    end = returns.index.max()
    r = returns[returns.index >= end - timedelta(days=days)]
    btc = r["BTCUSDT"]
    out = {}
    for sym in ["ETHUSDT", "XRPUSDT"]:
        beta = float(np.cov(r[sym], btc, ddof=0)[0, 1] / np.var(btc, ddof=0))
        out[sym] = round(beta, 3)
    return out


# ── MAIN ───────────────────────────────────────────────────────────────

def main():
    print("Loading 3 symbols...")
    df = _align_three()
    returns = _returns(df)
    print(f"Aligned: {len(df)} bars, {df.index.min()} -> {df.index.max()}")

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "data_window": {
            "start": str(df.index.min()),
            "end": str(df.index.max()),
            "bars": len(df),
        },
        "correlation_windows": correlation_windows(returns),
        "rolling_correlation_1w": rolling_correlation(returns),
        "lead_lag": lead_lag(returns, max_lag_hours=6),
        "divergence_patterns": divergence_patterns(df, returns),
        "beta_hedge_full": beta_hedge_ratio(returns),
        "beta_hedge_30d": beta_recent(returns, 30),
        "beta_hedge_90d": beta_recent(returns, 90),
    }

    out_dir = ROOT / "state"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "cross_asset_analysis.json"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved: {json_path}")
    return result


if __name__ == "__main__":
    r = main()
    # Brief stdout summary
    print("\n=== CORRELATION (last 90d) ===")
    c90 = r["correlation_windows"].get("90d", {})
    print(f"  BTC-ETH: {c90.get('BTC_ETH')}  BTC-XRP: {c90.get('BTC_XRP')}  ETH-XRP: {c90.get('ETH_XRP')}")

    print("\n=== LEAD-LAG ===")
    for pair, info in r["lead_lag"].items():
        print(f"  {pair}: {info['interpretation']}")

    print("\n=== BETA (1% BTC move) ===")
    for sym, info in r["beta_hedge_full"].items():
        print(f"  {sym}: beta={info['beta_full_period']} | for BTC +1%: {info['expected_move_for_btc_+1pct']} | for BTC -3%: {info['expected_move_for_btc_-3pct']}")

    print("\n=== DIVERGENCE PATTERNS ===")
    for pname, p in r["divergence_patterns"].items():
        o4 = p.get("outcome_4h_later", {})
        if o4.get("n", 0) >= 5:
            print(f"  {pname}: n={o4['n']} | BTC@+4h mean={o4['btc_mean_pct']}% pct_up={o4['btc_pct_up']}%")
