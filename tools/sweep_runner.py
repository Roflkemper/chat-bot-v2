from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.managed_grid_sim import InterventionLogWriter, SweepAnalyzer, SweepEngine


def load_bars(path: Path) -> list[Any]:
    if path.suffix == ".json":
        raw = json.loads(path.read_text(encoding="utf-8"))
        return [_row_to_bar(row) for row in raw]
    if path.suffix == ".parquet":
        df = pd.read_parquet(path)
    else:
        df = pd.read_csv(path)
    return [_row_to_bar(row) for row in df.to_dict(orient="records")]


def _row_to_bar(row: dict[str, Any]) -> Any:
    from collections import namedtuple

    OHLCBar = namedtuple("OHLCBar", ["ts", "open", "high", "low", "close", "volume"])
    return OHLCBar(
        ts=str(row["ts"]),
        open=float(row["open"]),
        high=float(row["high"]),
        low=float(row["low"]),
        close=float(row["close"]),
        volume=float(row.get("volume", 0.0)),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--ohlcv", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--parallelism", type=int, default=4)
    parser.add_argument("--max-runs", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    bars = load_bars(Path(args.ohlcv))
    engine = SweepEngine(
        bars=bars,
        base_bot_config=None,
        sweep_yaml_path=Path(args.config),
        parallelism=args.parallelism,
    )
    runs = engine.expand_to_runs()
    if args.max_runs is not None:
        runs = runs[: args.max_runs]
    print(f"expand to {len(runs)} runs")
    if args.dry_run:
        return 0

    results = [result for result in engine.execute_all(runs) if not isinstance(result, Exception)]
    output_dir = Path(args.output)
    log_writer = InterventionLogWriter()
    for result in results:
        log_writer.write_run(result, output_dir)
    analyzer = SweepAnalyzer(Path(args.config).stem)
    analysis = analyzer.analyze(results)
    analyzer.write_report(analysis, output_dir / "report.md")
    print(f"completed {len(results)} runs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
