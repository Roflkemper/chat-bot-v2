"""Session breakout edge — backtest.

Hypothesis: переход между сессиями (Asia → London → NY) часто сопровождается
пробоем high/low предыдущей сессии в первые 60-90 минут новой. Trade в
направлении пробоя.

Strategy:
  At session_change ts:
    set ref_high = prior_session.high
    set ref_low  = prior_session.low
    set entry_window = first X minutes of new session
  Within window:
    if price.high > ref_high * (1 + breakout_buffer):
      → LONG entry at break price, hold N hours, exit market
    if price.low < ref_low * (1 - breakout_buffer):
      → SHORT entry at break price, hold N hours, exit market
  One trade per session boundary.

Sweep:
  - entry_window_min: [30, 60, 90, 120]
  - breakout_buffer_pct: [0.0, 0.05, 0.10, 0.20]   (0 = touch, 0.20 = 0.2% above)
  - hold_hours: [2, 4, 6, 12]
  - transition: [asia_to_london, london_to_ny_am, ny_pm_to_asia, all]

Walk-forward 4 folds.

Output:
  docs/STRATEGIES/SESSION_BREAKOUT_BACKTEST.md
  state/session_breakout_results.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT_MD = ROOT / "docs" / "STRATEGIES" / "SESSION_BREAKOUT_BACKTEST.md"
CSV_OUT = ROOT / "state" / "session_breakout_results.csv"
ICT_PARQUET = ROOT / "data" / "ict_levels" / "BTCUSDT_ict_levels_1m.parquet"

# Sweep — extended 2026-05-11 round 2: deep dive after PF 1.52 found
ENTRY_WINDOWS = [15, 30, 45, 60, 90]    # minutes
BREAKOUT_BUFFERS = [0.0, 0.02, 0.05, 0.10]  # %
HOLD_HOURS = [1, 2, 3, 4, 6, 8, 12]
TRANSITIONS = [
    "asia_to_london",
    "london_to_ny_am",
    "ny_am_to_ny_lunch",
    "ny_pm_to_asia",
    "all",
]

# Map transition to (prior_session_name, new_session_name).
# prior session's high/low used; trigger fires when new session begins.
TRANS_MAP = {
    "asia_to_london":     ("asia", "london"),
    "london_to_ny_am":    ("london", "ny_am"),
    "ny_am_to_ny_lunch":  ("ny_am", "ny_lunch"),
    "ny_pm_to_asia":      ("ny_pm", "asia"),
}

BASE_SIZE_USD = 1000.0
TAKER_FEE_PCT = 0.075
N_FOLDS = 4


def load_data() -> pd.DataFrame:
    df = pd.read_parquet(ICT_PARQUET)
    df = df.sort_index()
    return df


def simulate(df: pd.DataFrame, *, entry_window_min: int, buffer_pct: float,
             hold_hours: int, transition: str) -> dict:
    if transition == "all":
        trans_list = list(TRANS_MAP.values())
    else:
        trans_list = [TRANS_MAP[transition]]

    high_arr = df["high"].values
    low_arr = df["low"].values
    close_arr = df["close"].values
    session_arr = df["session_active"].values
    time_in_session_arr = df["time_in_session_min"].values

    n = len(df)
    hold_bars = hold_hours * 60  # 1m bars

    trades = []

    for prior_session, new_session in trans_list:
        # Field names with high/low
        prior_high_col = f"{prior_session}_high"
        prior_low_col = f"{prior_session}_low"
        prior_high = df[prior_high_col].values
        prior_low = df[prior_low_col].values

        # Iterate by finding new_session start bars (first bar where session == new_session)
        # Use vectorized: find i where session_arr[i] == new_session and session_arr[i-1] != new_session
        in_new = (session_arr == new_session)
        prev_diff = np.zeros(n, dtype=bool)
        prev_diff[1:] = in_new[1:] & ~in_new[:-1]
        change_idxs = np.where(prev_diff)[0]

        for change_i in change_idxs:
            ref_high = prior_high[change_i]
            ref_low = prior_low[change_i]
            if np.isnan(ref_high) or np.isnan(ref_low) or ref_high <= 0 or ref_low <= 0:
                continue
            # Look forward through next entry_window_min bars for break
            end_i = min(change_i + entry_window_min, n - 1)
            broke_up = False
            broke_down = False
            entry_idx = None
            side = None
            target_high = ref_high * (1 + buffer_pct / 100)
            target_low = ref_low * (1 - buffer_pct / 100)
            for i in range(change_i, end_i + 1):
                if high_arr[i] >= target_high:
                    broke_up = True
                    entry_idx = i
                    side = "long"
                    entry_price = float(target_high)
                    break
                if low_arr[i] <= target_low:
                    broke_down = True
                    entry_idx = i
                    side = "short"
                    entry_price = float(target_low)
                    break

            if entry_idx is None:
                continue

            exit_idx = min(entry_idx + hold_bars, n - 1)
            exit_price = float(close_arr[exit_idx])
            if entry_price <= 0:
                continue

            if side == "long":
                gross_pct = (exit_price - entry_price) / entry_price * 100
            else:
                gross_pct = (entry_price - exit_price) / entry_price * 100
            fee_pct = 2 * TAKER_FEE_PCT
            pnl_usd = BASE_SIZE_USD * (gross_pct - fee_pct) / 100
            trades.append({
                "entry_idx": int(entry_idx), "exit_idx": int(exit_idx),
                "side": side, "transition": f"{prior_session}->{new_session}",
                "entry": entry_price, "exit": exit_price,
                "gross_pct": gross_pct, "pnl_usd": pnl_usd,
            })

    if not trades:
        return {"n": 0, "pnl": 0.0, "pf": 0.0, "wr": 0.0,
                "avg_pnl": 0.0, "max_dd": 0.0, "trades": []}

    pnls = np.array([t["pnl_usd"] for t in trades])
    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]
    pf = float(wins.sum() / -losses.sum()) if losses.sum() < 0 else (
        999.0 if wins.sum() > 0 else 0.0)
    wr = float((pnls > 0).mean() * 100)
    eq = np.cumsum(pnls)
    peak = np.maximum.accumulate(eq)
    dd = float(np.max(peak - eq)) if len(eq) else 0.0
    return {
        "n": len(trades), "pnl": float(pnls.sum()),
        "pf": pf, "wr": wr, "avg_pnl": float(pnls.mean()),
        "max_dd": dd, "trades": trades,
    }


def walk_forward(df: pd.DataFrame, *, entry_window_min: int, buffer_pct: float,
                 hold_hours: int, transition: str,
                 n_folds: int = N_FOLDS) -> list[dict]:
    n = len(df)
    fold_size = n // n_folds
    out = []
    for k in range(n_folds):
        start = k * fold_size
        end = (k + 1) * fold_size if k < n_folds - 1 else n
        sub = df.iloc[start:end].copy()
        m = simulate(sub, entry_window_min=entry_window_min,
                     buffer_pct=buffer_pct, hold_hours=hold_hours,
                     transition=transition)
        out.append({"fold": k + 1, "n": m["n"], "pnl": m["pnl"],
                    "pf": m["pf"], "wr": m["wr"], "max_dd": m["max_dd"]})
    return out


def main() -> int:
    print(f"[session-break] loading {ICT_PARQUET.name}...")
    df = load_data()
    print(f"[session-break] {len(df):,} 1m bars, "
          f"{df.index[0]} -> {df.index[-1]}")

    results = []
    n_combos = (len(ENTRY_WINDOWS) * len(BREAKOUT_BUFFERS)
                * len(HOLD_HOURS) * len(TRANSITIONS))
    print(f"[session-break] {n_combos} combos\n")
    idx = 0
    for trans in TRANSITIONS:
        for ew in ENTRY_WINDOWS:
            for bp in BREAKOUT_BUFFERS:
                for hh in HOLD_HOURS:
                    idx += 1
                    m = simulate(df, entry_window_min=ew, buffer_pct=bp,
                                 hold_hours=hh, transition=trans)
                    wf = walk_forward(df, entry_window_min=ew, buffer_pct=bp,
                                      hold_hours=hh, transition=trans)
                    pos_folds = sum(1 for f in wf if f["pnl"] > 0)
                    results.append({
                        "transition": trans, "entry_window_min": ew,
                        "buffer_pct": bp, "hold_hours": hh,
                        "n_trades": m["n"], "pnl_usd": m["pnl"],
                        "pf": m["pf"], "wr_pct": m["wr"],
                        "avg_pnl_usd": m["avg_pnl"], "max_dd_usd": m["max_dd"],
                        "fold_pos": pos_folds, "fold_total": len(wf),
                        "fold_pnls": [f["pnl"] for f in wf],
                    })
                    if idx % 20 == 0 or idx == n_combos:
                        print(f"  [{idx}/{n_combos}] {trans:<20} ew={ew:>3} "
                              f"buf={bp:.2f} hold={hh}h N={m['n']:>4} "
                              f"PnL=${m['pnl']:+,.0f} PF={m['pf']:.2f} "
                              f"pos={pos_folds}/{len(wf)}")

    results.sort(key=lambda r: r["pnl_usd"], reverse=True)
    print("\n[session-break] TOP 15 by PnL:")
    print(f"  {'transition':<22} {'ew':>4} {'buf':>5} {'hold':>4} {'N':>4} "
          f"{'PnL':>10} {'PF':>5} {'WR%':>5} {'pos':>4}")
    for r in results[:15]:
        print(f"  {r['transition']:<22} {r['entry_window_min']:>4} "
              f"{r['buffer_pct']:>5.2f} {r['hold_hours']:>4} {r['n_trades']:>4} "
              f"${r['pnl_usd']:>+9,.0f} {r['pf']:>5.2f} {r['wr_pct']:>5.0f} "
              f"{r['fold_pos']}/{r['fold_total']}")

    # Markdown
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    md = ["# Session Breakout Backtest — BTCUSDT 2y\n\n"]
    md.append(f"**Период:** {df.index[0]} -> {df.index[-1]} ({len(df):,} 1m bars)\n\n")
    md.append("**Стратегия:**\n")
    md.append("- При смене сессии: сохраняем high/low предыдущей сессии\n")
    md.append("- В первые `entry_window` минут новой сессии: если цена пробивает "
              "high+buffer% (или low-buffer%) → LONG/SHORT\n")
    md.append("- Hold N часов, exit market. 1 trade per session boundary.\n")
    md.append(f"- fees: 2 × {TAKER_FEE_PCT}% taker, size: ${BASE_SIZE_USD}\n\n")

    md.append("**Sweep:**\n")
    md.append(f"- transition: {TRANSITIONS}\n")
    md.append(f"- entry_window_min: {ENTRY_WINDOWS}\n")
    md.append(f"- breakout_buffer_pct: {BREAKOUT_BUFFERS}\n")
    md.append(f"- hold_hours: {HOLD_HOURS}\n")
    md.append(f"- Total combos: {len(results)}\n\n")

    md.append("## Топ-25 по PnL\n\n")
    md.append("| transition | ew | buf% | hold | N | PnL ($) | PF | WR% | avg | DD | pos |\n")
    md.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|\n")
    for r in results[:25]:
        md.append(f"| {r['transition']} | {r['entry_window_min']} | "
                  f"{r['buffer_pct']:.2f} | {r['hold_hours']} | {r['n_trades']} | "
                  f"{r['pnl_usd']:+,.0f} | {r['pf']:.2f} | {r['wr_pct']:.0f} | "
                  f"{r['avg_pnl_usd']:+,.1f} | {r['max_dd_usd']:,.0f} | "
                  f"{r['fold_pos']}/{r['fold_total']} |\n")

    md.append("\n## Худшие 5\n\n")
    md.append("| transition | ew | buf% | hold | N | PnL ($) | PF |\n|---|---:|---:|---:|---:|---:|---:|\n")
    for r in results[-5:]:
        md.append(f"| {r['transition']} | {r['entry_window_min']} | "
                  f"{r['buffer_pct']:.2f} | {r['hold_hours']} | {r['n_trades']} | "
                  f"{r['pnl_usd']:+,.0f} | {r['pf']:.2f} |\n")

    md.append("\n## Best per transition (filtered: PF>1, pos>=3)\n\n")
    for trans in TRANSITIONS:
        rows = [r for r in results if r["transition"] == trans
                and r["pf"] > 1 and r["fold_pos"] >= 3]
        if not rows:
            md.append(f"### {trans}\nНет надёжных комбинаций (PF>1, 3+ pos folds).\n\n")
            continue
        best = max(rows, key=lambda r: r["pnl_usd"])
        md.append(f"### {trans}\n")
        md.append(f"- ew={best['entry_window_min']}, buf={best['buffer_pct']:.2f}%, "
                  f"hold={best['hold_hours']}h\n")
        md.append(f"- N={best['n_trades']}, PnL=**${best['pnl_usd']:+,.0f}**, "
                  f"PF={best['pf']:.2f}, WR={best['wr_pct']:.0f}%\n")
        md.append(f"- Pos folds: {best['fold_pos']}/{best['fold_total']}\n")
        md.append(f"- Per-fold PnL: {[round(p, 0) for p in best['fold_pnls']]}\n\n")

    md.append("\n## Verdict\n\n")
    best_overall = results[0]
    if best_overall["pf"] >= 1.5 and best_overall["fold_pos"] >= 3 and best_overall["n_trades"] >= 30:
        md.append(f"✅ **Session breakout edge подтверждён.** "
                  f"{best_overall['transition']}, ew={best_overall['entry_window_min']}, "
                  f"buf={best_overall['buffer_pct']:.2f}%, hold={best_overall['hold_hours']}h "
                  f"→ PF {best_overall['pf']:.2f}, "
                  f"{best_overall['fold_pos']}/{best_overall['fold_total']} positive folds, "
                  f"N={best_overall['n_trades']}.\n\n")
    elif best_overall["pf"] >= 1.0:
        md.append(f"⚠️ Marginal: best PF {best_overall['pf']:.2f}, N={best_overall['n_trades']}.\n\n")
    else:
        md.append(f"❌ Edge не подтверждён: best PF {best_overall['pf']:.2f}.\n\n")

    OUT_MD.write_text("".join(md), encoding="utf-8")
    print(f"\n[session-break] wrote {OUT_MD}")

    pd.DataFrame([{k: v for k, v in r.items() if k != "fold_pnls"} for r in results]).to_csv(
        CSV_OUT, index=False)
    print(f"[session-break] wrote {CSV_OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
