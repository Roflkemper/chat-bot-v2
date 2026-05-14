"""CLI: walk-forward T2-MEGA на 1m BTCUSDT 2y данных."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.backtest.walk_forward_t2mega import format_walk_forward, run_walk_forward


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--span-days", type=int, default=90, help="Window length in days.")
    parser.add_argument("--step-days", type=int, default=30, help="Window step in days.")
    args = parser.parse_args()

    print(f"Running walk-forward: {args.span_days}d windows, step {args.step_days}d...")
    print("(this may take 1-2 minutes per window on 1m bars)")
    results = run_walk_forward(span_days=args.span_days, step_days=args.step_days)
    print()
    print(format_walk_forward(results))
