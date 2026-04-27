"""Report generator — markdown summary of a What-If play run.

§12 TZ-022.

CLI:
    python -m src.whatif.reports --play P-1 --date 2026-04-27
    python -m src.whatif.reports --play P-1  # uses most recent date
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

_PLAY_NAMES: dict[str, str] = {
    "P-1":  "Raise Boundary on Rally",
    "P-2":  "Launch Stack Short on Rally",
    "P-3":  "Launch Counter-Long on Critical Rally",
    "P-4":  "Stop on Extended Rally / No-Pullback",
    "P-5":  "Close Partial on Critical Rally",
    "P-6":  "Raise-and-Stack Short on Critical Rally",
    "P-7":  "Launch Stack Long after Dump",
    "P-8":  "Restart with New Params on Critical",
    "P-9":  "Close Partial Long on Rally",
    "P-10": "Restart with New Params (Drawdown)",
    "P-11": "Launch Stack Short on Rally (v2)",
    "P-12": "Adaptive Grid on Rally / No-Pullback",
}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _fmt(v: float | None, spec: str = ".2f") -> str:
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    return format(v, spec)


def _parse_params(param_values_json: str) -> str:
    d = json.loads(param_values_json)
    return ", ".join(f"{k}={v}" for k, v in sorted(d.items()))


def _col(df: pd.DataFrame, name: str, default=None) -> pd.Series:
    """Safe column access — returns series of default if column missing."""
    if name in df.columns:
        return df[name]
    return pd.Series([default] * len(df), index=df.index)


# ─────────────────────────────────────────────────────────────────────────────
# Section builders
# ─────────────────────────────────────────────────────────────────────────────

def _section_header(play_id: str, results_df: pd.DataFrame, manifest: dict) -> list[str]:
    play_name   = _PLAY_NAMES.get(play_id, play_id)
    run_date    = manifest.get("timestamp", "")[:10] or "unknown"
    version     = manifest.get("version", "—")
    horizon     = manifest.get("horizon_min", "—")
    total_eps   = int(results_df["n_episodes"].max()) if not results_df.empty else 0
    symbols     = manifest.get("symbols_filter", "BTCUSDT")

    return [
        f"# Play {play_id} — {play_name}",
        "",
        "| | |",
        "|---|---|",
        f"| Дата прогона | {run_date} |",
        f"| Версия движка | {version} |",
        f"| Эпизодов | {total_eps} |",
        f"| Горизонт (мин) | {horizon} |",
        f"| Символ | {symbols} |",
        "",
    ]


def _section_param_grid(results_df: pd.DataFrame) -> list[str]:
    if results_df.empty:
        return []
    param_ranges: dict[str, set] = {}
    for pv in results_df["param_values"]:
        for k, v in json.loads(pv).items():
            param_ranges.setdefault(k, set()).add(v)

    lines = ["## Сетка параметров", ""]
    for k in sorted(param_ranges):
        lines.append(f"- **{k}**: {sorted(param_ranges[k])}")
    lines.append("")
    return lines


def _section_summary_table(results_df: pd.DataFrame) -> list[str]:
    sorted_df = results_df.sort_values("mean_pnl_vs_baseline_usd", ascending=False)

    lines = [
        "## Сводная таблица по combo",
        "",
        "| combo_id | параметры | n_eps | mean_pnl_vs_base USD | win_rate | mean_dd_vs_base % | target_hit% | volume USD |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for _, row in sorted_df.iterrows():
        vol = _col(results_df, "mean_volume_traded_usd").iloc[0]
        vol = _fmt(row.get("mean_volume_traded_usd", row.get("mean_volume_usd")), ".0f")
        lines.append(
            f"| {row['param_combo_id']} "
            f"| {_parse_params(row['param_values'])} "
            f"| {int(row['n_episodes'])} "
            f"| {_fmt(row['mean_pnl_vs_baseline_usd'])} "
            f"| {_fmt(row['win_rate'], '.1%')} "
            f"| {_fmt(row['mean_dd_vs_baseline_pct'])} "
            f"| {_fmt(row.get('mean_target_hit_pct'), '.1%')} "
            f"| {vol} |"
        )
    lines.append("")
    return lines


def _section_best_combo(results_df: pd.DataFrame) -> tuple[list[str], str]:
    """Returns (lines, best_combo_id)."""
    best = results_df.sort_values("mean_pnl_vs_baseline_usd", ascending=False).iloc[0]
    best_id     = best["param_combo_id"]
    best_params = _parse_params(best["param_values"])

    lines = [
        "## Лучшее combo",
        "",
        f"**{best_id}** — {best_params}",
        "",
        f"- mean PnL vs baseline: **{_fmt(best['mean_pnl_vs_baseline_usd'])} USD**",
        f"- win rate (action > baseline): **{_fmt(best['win_rate'], '.1%')}**",
        f"- mean DD vs baseline: **{_fmt(best['mean_dd_vs_baseline_pct'])} %**",
        f"- mean volume: **{_fmt(best.get('mean_volume_traded_usd'), '.0f')} USD**",
        "",
    ]
    return lines, best_id


def _ep_table_rows(sub_df: pd.DataFrame) -> list[str]:
    rows = []
    for _, r in sub_df.iterrows():
        ts   = str(r.get("ts_start", "—"))[:19]
        et   = r.get("episode_type", "—")
        hit  = "✓" if int(r.get("target_hit_count", 0) or 0) > 0 else "—"
        rows.append(
            f"| {ts} | {et} "
            f"| {_fmt(r['pnl_vs_baseline_usd'])} "
            f"| {_fmt(r['dd_vs_baseline_pct'])} "
            f"| {hit} |"
        )
    return rows


_EP_HEADER = "| timestamp | episode_type | pnl_vs_base USD | dd_vs_base % | target_hit |"
_EP_SEP    = "|---|---|---|---|---|"


def _section_episodes(raw_df: pd.DataFrame | None, best_combo_id: str) -> list[str]:
    if raw_df is None or raw_df.empty:
        return [
            "## Top-5 / Worst-5 эпизодов",
            "",
            "_Per-episode данные недоступны. Запустите прогон заново: `_raw.parquet` будет создан автоматически._",
            "",
        ]

    best_raw = raw_df[raw_df["param_combo_id"] == best_combo_id].copy()
    if best_raw.empty:
        return [
            "## Top-5 / Worst-5 эпизодов",
            "",
            f"_Нет данных для combo {best_combo_id}._",
            "",
        ]

    top5   = best_raw.nlargest(5, "pnl_vs_baseline_usd")
    worst5 = best_raw.nsmallest(5, "pnl_vs_baseline_usd")

    lines = [
        "## Top-5 эпизодов (action лучше baseline)",
        "",
        _EP_HEADER, _EP_SEP,
    ]
    lines += _ep_table_rows(top5)
    lines += [
        "",
        "## Worst-5 эпизодов (action хуже baseline)",
        "",
        _EP_HEADER, _EP_SEP,
    ]
    lines += _ep_table_rows(worst5)
    lines.append("")
    return lines


def _section_footer(play_id: str) -> list[str]:
    return [
        "---",
        "",
        "**Ограничения модели v1:**",
        "- Позиции синтетические (не из реальных bot snapshots)",
        "- Не моделируется: частичное закрытие, маржин-колл, фандинг",
        "- Slippage и комиссии фиксированы (0.01% / 0.04%)",
        "- Горизонт 240 мин не захватывает разворот после ралли",
        "",
        f"Данные: `whatif_results/{play_id}_*.parquet`",
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def generate_report(
    play_id: str,
    results_df: pd.DataFrame,
    manifest: dict,
    raw_df: pd.DataFrame | None = None,
) -> str:
    """Build markdown report string.

    Args:
        play_id:     e.g. "P-1".
        results_df:  Aggregated combo DataFrame from grid_search_play / parquet.
        manifest:    Dict from manifest.json (may be empty).
        raw_df:      Per-episode raw rows (optional, enables Top/Worst sections).

    Returns:
        Markdown string.
    """
    if results_df.empty:
        return f"# Play {play_id}\n\n_No results._\n"

    lines: list[str] = []
    lines += _section_header(play_id, results_df, manifest)
    lines += _section_param_grid(results_df)
    lines += _section_summary_table(results_df)
    combo_lines, best_id = _section_best_combo(results_df)
    lines += combo_lines
    lines += _section_episodes(raw_df, best_id)
    lines += _section_footer(play_id)

    return "\n".join(lines) + "\n"


def write_report(
    play_id: str,
    output_dir: str | Path = "whatif_results",
    date_str: str | None = None,
) -> Path:
    """Load parquet(s) from output_dir, generate report, write .md file.

    Args:
        play_id:    e.g. "P-1".
        output_dir: Directory containing parquet files and manifest.json.
        date_str:   Date suffix "YYYY-MM-DD". If None, uses most recent file.

    Returns:
        Path to written .md file.
    """
    output_dir = Path(output_dir)

    # Find aggregated parquet
    if date_str:
        agg_path = output_dir / f"{play_id}_{date_str}.parquet"
    else:
        candidates = sorted(output_dir.glob(f"{play_id}_????-??-??.parquet"))
        if not candidates:
            raise FileNotFoundError(f"No parquet found for {play_id} in {output_dir}")
        agg_path = candidates[-1]
        date_str = agg_path.stem.split("_", 1)[1]  # extract date from filename

    results_df = pd.read_parquet(agg_path)

    # Raw parquet (optional)
    raw_path = output_dir / f"{play_id}_{date_str}_raw.parquet"
    raw_df = pd.read_parquet(raw_path) if raw_path.exists() else None

    # Manifest (optional)
    manifest_path = output_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}

    report_md = generate_report(play_id, results_df, manifest, raw_df)

    out_path = output_dir / f"{play_id}_{date_str}.md"
    out_path.write_text(report_md, encoding="utf-8")
    return out_path


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m src.whatif.reports",
        description="Generate markdown report for a What-If play run (TZ-022 §12)",
    )
    p.add_argument("--play", required=True, help="Play ID, e.g. P-1")
    p.add_argument("--date", default=None, help="Date suffix YYYY-MM-DD (default: most recent)")
    p.add_argument("--output", type=Path, default=Path("whatif_results"),
                   help="Results directory. Default: whatif_results/")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args(argv)
    try:
        path = write_report(args.play, args.output, args.date)
        print(f"Report written: {path}")
        return 0
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
