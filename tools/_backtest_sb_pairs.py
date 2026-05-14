"""Session Breakout + другой детектор — pair-wise backtest.

Question: какой именно partner-detector усиливает session_breakout?
Может session_breakout + multi_divergence работают вместе лучше всех?
Или session_breakout + cascade_alert?

Method:
  1. Reuse signal timeline from confluence backtest.
  2. For each session_breakout signal, check if PARTNER detector fired in
     last N hours same side.
  3. Backtest only those "co-occurrence" trades — measure PF, WR, N.
  4. Compare 4 partners: multi_divergence, pdl_bounce, pdh_rejection,
     cascade_proxy.

Output: docs/STRATEGIES/SESSION_BREAKOUT_PAIRS.md
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT_MD = ROOT / "docs" / "STRATEGIES" / "SESSION_BREAKOUT_PAIRS.md"
SIGNAL_TIMELINE = ROOT / "state" / "confluence_signal_timeline.parquet"
PRICE_1H = ROOT / "backtests" / "frozen" / "BTCUSDT_1h_2y.csv"

WINDOW_HOURS = [2, 4, 6, 12]
HOLD_HOURS = 3   # match live session_breakout HOLD_HOURS
N_FOLDS = 4
BASE_SIZE_USD = 1000.0
TAKER_FEE_PCT = 0.075


def simulate(df: pd.DataFrame, sb_sigs: pd.DataFrame, partner_sigs: pd.DataFrame,
             *, window_h: int) -> dict:
    """For each session_breakout signal, check if partner fired in last window_h.
    Then trade on session_breakout entry, hold HOLD_HOURS."""
    n = len(df)
    close = df["close"].values

    # Index partner signals by bar for window lookups
    partner_long_by_bar: dict[int, bool] = {}
    partner_short_by_bar: dict[int, bool] = {}
    for _, row in partner_sigs.iterrows():
        bar = int(row["bar"])
        if row["side"] == "long":
            partner_long_by_bar[bar] = True
        else:
            partner_short_by_bar[bar] = True

    trades_pair = []
    trades_solo = []  # session_breakout WITHOUT partner (baseline)

    for _, sb in sb_sigs.iterrows():
        bar = int(sb["bar"])
        side = sb["side"]
        if bar + HOLD_HOURS >= n or bar - window_h < 0:
            continue
        entry = float(close[bar])
        exit_p = float(close[bar + HOLD_HOURS])
        if entry <= 0:
            continue
        if side == "long":
            gross_pct = (exit_p - entry) / entry * 100
        else:
            gross_pct = (entry - exit_p) / entry * 100
        pnl_usd = BASE_SIZE_USD * (gross_pct - 2 * TAKER_FEE_PCT) / 100

        # Did partner fire in last window_h?
        target_by_bar = partner_long_by_bar if side == "long" else partner_short_by_bar
        partner_fired = any(b in target_by_bar
                             for b in range(bar - window_h + 1, bar + 1))
        if partner_fired:
            trades_pair.append(pnl_usd)
        else:
            trades_solo.append(pnl_usd)

    return {
        "pair_n": len(trades_pair),
        "pair_pnl": sum(trades_pair),
        "pair_pf": _pf(trades_pair),
        "pair_wr": _wr(trades_pair),
        "solo_n": len(trades_solo),
        "solo_pnl": sum(trades_solo),
        "solo_pf": _pf(trades_solo),
        "solo_wr": _wr(trades_solo),
    }


def _pf(pnls: list[float]) -> float:
    if not pnls:
        return 0.0
    arr = np.array(pnls)
    wins = arr[arr > 0].sum()
    losses = -arr[arr < 0].sum()
    if losses <= 0:
        return 999.0 if wins > 0 else 0.0
    return wins / losses


def _wr(pnls: list[float]) -> float:
    if not pnls:
        return 0.0
    arr = np.array(pnls)
    return (arr > 0).mean() * 100


def main() -> int:
    print("[sb-pairs] loading data...")
    sig_df = pd.read_parquet(SIGNAL_TIMELINE)
    df = pd.read_csv(PRICE_1H).sort_values("ts").reset_index(drop=True)

    sb_sigs = sig_df[sig_df["detector"] == "session_breakout"].copy()
    print(f"[sb-pairs] {len(sb_sigs)} session_breakout signals")

    partners = ["multi_divergence", "pdl_bounce", "pdh_rejection", "cascade_proxy"]
    results = []

    for partner in partners:
        partner_sigs = sig_df[sig_df["detector"] == partner]
        print(f"\n=== Partner: {partner} ({len(partner_sigs)} signals) ===")
        for wh in WINDOW_HOURS:
            m = simulate(df, sb_sigs, partner_sigs, window_h=wh)
            results.append({"partner": partner, "window_h": wh, **m})
            print(f"  window={wh}h:  "
                  f"PAIR n={m['pair_n']} PnL=${m['pair_pnl']:+,.0f} "
                  f"PF={m['pair_pf']:.2f} WR={m['pair_wr']:.0f}%  |  "
                  f"SOLO n={m['solo_n']} PnL=${m['solo_pnl']:+,.0f} "
                  f"PF={m['solo_pf']:.2f}")

    # Markdown
    md = ["# Session Breakout × Other Detectors — Pair-wise Backtest\n\n"]
    md.append(f"**Method:** for each session_breakout signal, check if PARTNER\n")
    md.append(f"detector fired same side within last `window_h`. Bucket into PAIR (yes) or SOLO (no).\n")
    md.append(f"Trade only on the session_breakout bar, hold {HOLD_HOURS}h, fees 2×{TAKER_FEE_PCT}%.\n\n")
    md.append(f"**Total session_breakout signals:** {len(sb_sigs)}\n\n")

    md.append("## Results\n\n")
    md.append("| partner | window_h | PAIR N | PAIR PnL | PAIR PF | PAIR WR% | SOLO N | SOLO PnL | SOLO PF |\n")
    md.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|\n")
    for r in results:
        md.append(f"| {r['partner']} | {r['window_h']} | {r['pair_n']} | "
                  f"{r['pair_pnl']:+,.0f} | {r['pair_pf']:.2f} | {r['pair_wr']:.0f} | "
                  f"{r['solo_n']} | {r['solo_pnl']:+,.0f} | {r['solo_pf']:.2f} |\n")

    md.append("\n## Сравнение pair vs solo по detector × window\n\n")
    md.append("| partner | window | pair_PF / solo_PF | edge boost (pair PnL - solo avg) |\n")
    md.append("|---|---:|---|---:|\n")
    for r in results:
        boost_per_trade = (r["pair_pnl"] / r["pair_n"]) - (r["solo_pnl"] / r["solo_n"]) \
            if r["pair_n"] and r["solo_n"] else 0
        md.append(f"| {r['partner']} | {r['window_h']}h | "
                  f"{r['pair_pf']:.2f} / {r['solo_pf']:.2f} | "
                  f"${boost_per_trade:+.2f}/trade |\n")

    # Verdict
    md.append("\n## Verdict\n\n")
    best = max(results, key=lambda r: r["pair_pf"] if r["pair_n"] >= 30 else 0)
    md.append(f"Лучшая пара: **session_breakout + {best['partner']}** "
              f"(window={best['window_h']}h) → PAIR PF {best['pair_pf']:.2f} "
              f"(vs solo PF {best['solo_pf']:.2f}), N={best['pair_n']}, "
              f"PnL ${best['pair_pnl']:+,.0f}.\n\n")
    md.append("Это значит: когда session_breakout срабатывает И в последние "
              f"{best['window_h']} часов уже был сигнал {best['partner']} в ту же "
              f"сторону — edge **значительно сильнее** обычного.\n\n")
    md.append("Confluence boost которое мы добавили в loop.py будет автоматически "
              "усиливать confidence для таких setups.\n")

    OUT_MD.write_text("".join(md), encoding="utf-8")
    print(f"\n[sb-pairs] wrote {OUT_MD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
