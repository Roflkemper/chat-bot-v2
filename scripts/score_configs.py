"""CLI: multi-objective ranking GinArea-конфигов из V5-sweep."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.backtest.ginarea_scorer import (
    DEFAULT_DD_WEIGHT,
    DEFAULT_REBATE_PER_VOL_MUSD,
    V5_CONFIGS_LONG,
    format_ranking,
    rank_configs,
    score_config,
)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--rebate-per-m", type=float, default=DEFAULT_REBATE_PER_VOL_MUSD)
    parser.add_argument("--dd-weight", type=float, default=DEFAULT_DD_WEIGHT)
    parser.add_argument("--risk-limit", type=float, default=100_000.0,
                        help="Max peak exposure in USD; configs above are excluded.")
    parser.add_argument("--no-limit", action="store_true",
                        help="Disable risk limit (show all configs).")
    parser.add_argument("--detail", action="store_true",
                        help="Show full breakdown per config.")
    args = parser.parse_args()

    limit = None if args.no_limit else args.risk_limit
    ranked = rank_configs(
        V5_CONFIGS_LONG,
        rebate_per_m=args.rebate_per_m,
        dd_weight=args.dd_weight,
        risk_limit_usd=limit,
    )
    print(format_ranking(ranked, top=args.top))

    if args.detail:
        print("\n── Breakdown лидера ──")
        leader = ranked[0]
        for k, v in leader.breakdown.items():
            print(f"  {k}: {v:+.0f}")
        print(f"  ────────────")
        print(f"  TOTAL: {leader.total:+.0f}")
