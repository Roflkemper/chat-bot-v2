"""CLI: дашборд эффективности фильтров paper_trader по дням."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.paper_trader.filter_dashboard import render_dashboard


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=14)
    args = parser.parse_args()
    print(render_dashboard(days=args.days))
