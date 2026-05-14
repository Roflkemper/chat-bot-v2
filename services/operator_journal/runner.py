from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .snapshot_diff import run_extraction


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract operator decisions from tracker history")
    parser.add_argument("--rebuild", action="store_true", help="Rebuild output parquet from scratch")
    parser.add_argument("--incremental", action="store_true", help="Append only new decisions after the last saved ts")
    parser.add_argument("--output", default="data/operator_journal/decisions.parquet", help="Output parquet path")
    args = parser.parse_args(argv)
    if not args.rebuild and not args.incremental:
        parser.error("one of --rebuild or --incremental is required")

    df = run_extraction(rebuild=args.rebuild, incremental=args.incremental, output=Path(args.output))
    print(f"decisions={len(df)} output={args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
