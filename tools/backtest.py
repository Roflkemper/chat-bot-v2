"""Unified backtest runner — single entry for all P-15-family backtests.

Usage:
  python tools/backtest.py p15-honest
  python tools/backtest.py p15-full
  python tools/backtest.py p15-multi-asset
  python tools/backtest.py p15-horizons
  python tools/backtest.py p16
  python tools/backtest.py walkfwd-all
  python tools/backtest.py p15-1h --asset XRPUSDT --direction long
  python tools/backtest.py --list
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent

REGISTRY = {
    "p15-horizons":     ("_backtest_horizons.py",            "Multi-horizon P-15 base + BoS w=10"),
    "p15-honest":       ("_backtest_p15_honest.py",          "P-15 honest sim (cumulative DD, fees)"),
    "p15-full":         ("_backtest_p15_full.py",            "P-15 full: LONG/SHORT, 1h+15m, walk-forward"),
    "p15-multi-asset":  ("_backtest_p15_multi_asset.py",     "P-15 across BTC/ETH/XRP"),
    "p15-rolling":      ("_backtest_p15_rolling_rebalance.py", "P-15 rolling original (optimistic, deprecated)"),
    "p15-dual":         ("_backtest_dual_independent.py",    "Dual-leg averaging variants"),
    "p15-dual-leg":     ("_backtest_dual_leg.py",            "Dual-leg TP-flat sweep"),
    "p16":              ("_backtest_p16_post_impulse.py",    "P-16 post-impulse-booster sweep"),
    "walkfwd-all":      ("_walkfwd_all_detectors.py",        "Walk-forward across all detectors"),
}


def _run_module(filename: str) -> int:
    path = TOOLS / filename
    if not path.exists():
        print(f"ERROR: {path} not found", file=sys.stderr)
        return 1
    spec = importlib.util.spec_from_file_location("backtest_module", path)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(TOOLS))
    spec.loader.exec_module(mod)
    if hasattr(mod, "main"):
        return int(mod.main() or 0)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        prog="backtest",
        description="Unified backtest runner for bot7 strategies",
    )
    p.add_argument("strategy", nargs="?",
                   help="Strategy ID (run with --list to see all)")
    p.add_argument("--list", action="store_true",
                   help="List available backtests")
    args = p.parse_args()

    if args.list or args.strategy is None:
        print("=" * 80)
        print("Available backtests:")
        print("=" * 80)
        for k, (fname, desc) in REGISTRY.items():
            print(f"  {k:<20} — {desc}")
        print()
        print("Usage: python tools/backtest.py <strategy>")
        print("Example: python tools/backtest.py p15-multi-asset")
        return 0

    if args.strategy not in REGISTRY:
        print(f"ERROR: unknown strategy '{args.strategy}'. Run with --list", file=sys.stderr)
        return 1

    fname, _ = REGISTRY[args.strategy]
    print(f"=== Running: {args.strategy} ({fname}) ===\n")
    return _run_module(fname)


if __name__ == "__main__":
    sys.exit(main())
