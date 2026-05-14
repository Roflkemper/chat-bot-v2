"""CLI runner: python -m services.ict_levels.runner --input ... --output ..."""
from __future__ import annotations

import argparse
import logging
import sys
import time

from .builder import build_ict_levels


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build ICT levels parquet from 1m OHLCV CSV")
    parser.add_argument("--input",  required=True, help="Path to BTCUSDT_1m.csv")
    parser.add_argument("--output", required=True, help="Output .parquet path")
    parser.add_argument("--start",  default=None,  help="Start date (inclusive) YYYY-MM-DD")
    parser.add_argument("--end",    default=None,  help="End date (inclusive) YYYY-MM-DD")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    t0 = time.monotonic()
    df = build_ict_levels(
        input_path=args.input,
        output_path=args.output,
        start=args.start,
        end=args.end,
    )
    elapsed = time.monotonic() - t0

    print(f"Done. rows={len(df):,}  cols={len(df.columns)}  elapsed={elapsed:.1f}s")
    print(f"Output: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
