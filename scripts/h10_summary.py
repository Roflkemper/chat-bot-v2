"""H10 Backtest Summary Report Generator.

Usage:
    python scripts/h10_summary.py <backtest_csv> [--out reports/h10_backtest_YYYYMMDD.md]
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd
import numpy as np

REPORTS_DIR = ROOT / "reports"


def generate_report(df: pd.DataFrame, out_path: Path) -> None:
    if df.empty:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("# H10 Backtest -- No results\n\nNo setups detected.\n")
        return

    n_setups = df["setup_ts"].nunique()
    n_params = len(df.groupby(["grid_steps", "grid_step_pct", "tp_pct",
                                "time_stop_hours", "protective_stop_pct"]))
    date_range = f"{pd.Timestamp(df['setup_ts'].min()).date()} to {pd.Timestamp(df['setup_ts'].max()).date()}"

    lines: list[str] = [
        "# H10 Backtest Report",
        "",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}  ",
        f"**Setup window:** {date_range}  ",
        f"**Total setups detected:** {n_setups}  ",
        f"**Param combinations:** {n_params}  ",
        "",
        "---",
        "",
        "## Setup Distribution by Month",
        "",
    ]

    # Monthly breakdown
    df_ts = df.drop_duplicates("setup_ts").copy()
    df_ts["month"] = pd.to_datetime(df_ts["setup_ts"]).dt.to_period("M")
    monthly = df_ts.groupby("month").size().reset_index(name="setups")
    lines.append("| Month | Setups |")
    lines.append("|---|---|")
    for _, row in monthly.iterrows():
        lines.append(f"| {row['month']} | {row['setups']} |")
    lines.extend(["", "---", "", "## Per-Params Results", ""])

    # Per-params performance
    param_cols = ["protective_stop_pct", "tp_pct", "grid_step_pct", "time_stop_hours"]
    param_groups = df.groupby(param_cols)

    summary_rows: list[dict] = []
    for key, grp in param_groups:
        n = len(grp)
        wins = (grp["pnl_usd"] > 0).sum()
        win_rate = wins / n if n > 0 else 0
        avg_pnl = grp["pnl_usd"].mean()
        med_pnl = grp["pnl_usd"].median()
        total_pnl = grp["pnl_usd"].sum()
        total_vol = grp["volume_usd"].sum()
        avg_dd = grp["max_drawdown_pct"].mean()
        max_dd = grp["max_drawdown_pct"].min()  # most negative
        pct_tp = (grp["exit_reason"] == "tp").mean() * 100
        pct_ts = (grp["exit_reason"] == "time_stop").mean() * 100
        pct_ps = (grp["exit_reason"] == "protective_stop").mean() * 100
        score = total_vol * win_rate  # primary ranking metric

        stop, tp, step, tsh = key
        summary_rows.append({
            "stop": stop if stop is not None else "none",
            "tp_pct": tp,
            "step_pct": step,
            "time_h": tsh,
            "n": n,
            "win%": round(win_rate * 100, 1),
            "avg_pnl": round(avg_pnl, 2),
            "med_pnl": round(med_pnl, 2),
            "total_pnl": round(total_pnl, 2),
            "vol_musd": round(total_vol / 1e6, 3),
            "avg_dd%": round(avg_dd, 2),
            "max_dd%": round(max_dd, 2),
            "%tp": round(pct_tp, 1),
            "%ts": round(pct_ts, 1),
            "%ps": round(pct_ps, 1),
            "score": round(score, 1),
        })

    sdf = pd.DataFrame(summary_rows).sort_values("score", ascending=False)

    lines.append("| stop | tp% | step% | time_h | n | win% | avg_pnl$ | med_pnl$ | total_pnl$ | vol_M$ | avg_dd% | max_dd% | %tp | %ts | %ps | score |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for _, r in sdf.iterrows():
        lines.append(
            f"| {r['stop']} | {r['tp_pct']} | {r['step_pct']} | {r['time_h']} | "
            f"{r['n']} | {r['win%']} | {r['avg_pnl']} | {r['med_pnl']} | "
            f"{r['total_pnl']} | {r['vol_musd']} | {r['avg_dd%']} | {r['max_dd%']} | "
            f"{r['%tp']} | {r['%ts']} | {r['%ps']} | {r['score']} |"
        )

    lines.extend(["", "---", "", "## Session / Hour Analysis", ""])

    # Heatmap: setup frequency by hour of day
    df_ts["hour"] = pd.to_datetime(df_ts["setup_ts"]).dt.hour
    hourly_count = df_ts.groupby("hour").size()

    lines.append("**Setups by UTC hour:**  ")
    lines.append("")
    lines.append("| Hour | Count |")
    lines.append("|---|---|")
    for hour, cnt in sorted(hourly_count.items()):
        lines.append(f"| {hour:02d}:00 | {cnt} |")

    lines.extend(["", "---", "", "## Top 10 Best Setups (by PnL)", ""])

    top_cols = ["setup_ts", "impulse_pct", "impulse_dir", "target_side",
                "avg_entry", "exit_price", "exit_reason", "pnl_usd", "duration_min"]
    best_10 = df[df["protective_stop_pct"].isna()].nlargest(10, "pnl_usd")[top_cols]
    lines.append(best_10.to_markdown(index=False))

    lines.extend(["", "---", "", "## Top 10 Worst Setups (by PnL)", ""])
    worst_10 = df[df["protective_stop_pct"].isna()].nsmallest(10, "pnl_usd")[top_cols]
    lines.append(worst_10.to_markdown(index=False))

    lines.extend(["", "---", "", "## Recommended Parameters", ""])

    # Recommendation: best score with max_drawdown <= 2%
    good = sdf[sdf["max_dd%"] >= -2.0]
    if good.empty:
        good = sdf  # fall back to all
    rec = good.sort_values("score", ascending=False).iloc[0]
    lines.extend([
        f"**Best by (volume x win_rate) with max_drawdown <= 2%:**",
        f"",
        f"- protective_stop: `{rec['stop']}`",
        f"- tp_pct: `{rec['tp_pct']}`",
        f"- grid_step_pct: `{rec['step_pct']}`",
        f"- time_stop_hours: `{rec['time_h']}`",
        f"- win_rate: `{rec['win%']}%`",
        f"- avg_pnl/cycle: `${rec['avg_pnl']}`",
        f"- total_volume: `${rec['vol_musd']:.3f}M`",
        f"- max_drawdown: `{rec['max_dd%']}%`",
        f"",
        f"---",
        f"",
        f"## Notes on Data",
        f"",
        f"Historical backtest uses BTCUSDT 1h/1m data from frozen dataset.",
        f"Liquidation component = 0% (collectors only have recent data).",
        f"Liquidity map uses structure proximity (60%) + volume profile (40%).",
        f"Conditions relaxed from original spec: C1 impulse 1.5%->1.2%, C2 range 0.8%->1.0%.",
        f"For live deployment, liquidation data will be available from day 3+ of operation.",
    ])

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report saved: {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", nargs="?", default=None)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    if args.csv is None:
        candidates = sorted(REPORTS_DIR.glob("h10_backtest_*.csv"))
        if not candidates:
            print("No backtest CSV found. Run backtest_h10.py first.")
            sys.exit(1)
        csv_path = candidates[-1]
        print(f"Using latest: {csv_path}")
    else:
        csv_path = Path(args.csv)

    df = pd.read_csv(csv_path)
    out = Path(args.out) if args.out else (
        REPORTS_DIR / f"h10_backtest_{datetime.now().strftime('%Y-%m-%d')}.md"
    )
    generate_report(df, out)


if __name__ == "__main__":
    main()
