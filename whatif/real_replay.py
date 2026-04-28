from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from whatif.real_snapshot_replay import ROOT, run_real_play


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay What-If plays on real bot snapshots.")
    parser.add_argument("--plays", required=True, help="Comma-separated play ids, e.g. P-1,P-2")
    parser.add_argument("--bots", required=True, help="Comma-separated bot aliases/names/ids")
    parser.add_argument("--horizon-min", type=int, default=240)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def _load_synth_best(play_id: str) -> dict[str, float | str]:
    day = "2026-04-27"
    path = ROOT / "whatif_results" / f"{play_id}_{day}.parquet"
    if not path.exists():
        return {}
    df = pd.read_parquet(path).sort_values("mean_pnl_vs_baseline_usd", ascending=False)
    if df.empty:
        return {}
    row = df.iloc[0]
    return {
        "synth_param_values": row["param_values"],
        "synth_mean_pnl_vs_baseline_usd": float(row["mean_pnl_vs_baseline_usd"]),
    }


def _md_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_no rows_"
    cols = list(df.columns)
    lines = [
        "| " + " | ".join(cols) + " |",
        "| " + " | ".join(["---"] * len(cols)) + " |",
    ]
    for _, row in df.iterrows():
        vals = []
        for col in cols:
            val = row[col]
            if isinstance(val, float):
                vals.append(f"{val:.4f}")
            else:
                vals.append(str(val))
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    plays = [item.strip() for item in args.plays.split(",") if item.strip()]
    bots = [item.strip() for item in args.bots.split(",") if item.strip()]

    summary_frames = []
    for play in plays:
        summary, _ = run_real_play(play, bots, horizon_min=args.horizon_min)
        if summary.empty:
            continue
        synth = _load_synth_best(play)
        if synth:
            summary["synth_mean_pnl_vs_baseline_usd"] = synth["synth_mean_pnl_vs_baseline_usd"]
            summary["synth_vs_real_delta_usd"] = (
                summary["mean_pnl_vs_baseline_usd"] - summary["synth_mean_pnl_vs_baseline_usd"]
            )
        summary_frames.append(summary.head(1))

    result = pd.concat(summary_frames, ignore_index=True) if summary_frames else pd.DataFrame()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    body = [
        f"# REAL_SUMMARY_{datetime.now(timezone.utc).date()}",
        "",
        f"Generated: {stamp}",
        "",
        f"Plays: {', '.join(plays)}",
        f"Bots: {', '.join(bots)}",
        "",
    ]
    if result.empty:
        body.extend(
            [
                "## Result",
                "No overlapping real tracker windows found for the requested plays and bots.",
                "Current workspace facts:",
                "- tracker coverage starts after the available episode timestamps for P-1/P-2/P-6/P-7",
                "- summary table is therefore empty in this run",
                "",
            ]
        )
    body.extend(
        [
        "## Best real combo per play",
        _md_table(result),
        ]
    )
    args.output.write_text("\n".join(body), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "rows": int(len(result))}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
