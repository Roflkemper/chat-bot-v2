"""CLI: Run setup detector on historical OHLCV data and produce outcome dataset.

Usage:
    python tools/run_setup_backtest.py \\
      --start 2026-01-01 --end 2026-04-30 \\
      --frozen-path frozen/ETHUSDT_1m.parquet \\
      --pair ETHUSDT \\
      --output data/historical_setups_q1_2026.parquet \\
      --max-setups 100
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("run_setup_backtest")

# Ensure project root is on path
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))


def _parse_date(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def _setup_to_row(setup: Any, outcome: Any) -> dict[str, Any]:
    """Flatten setup + outcome into a flat dict for parquet output."""
    return {
        "setup_id": setup.setup_id,
        "setup_type": setup.setup_type.value,
        "detected_at": setup.detected_at.isoformat(),
        "pair": setup.pair,
        "current_price": setup.current_price,
        "regime": setup.regime_label,
        "session": setup.session_label,
        "entry_price": setup.entry_price,
        "stop_price": setup.stop_price,
        "tp1_price": setup.tp1_price,
        "tp2_price": setup.tp2_price,
        "rr": setup.risk_reward,
        "strength": setup.strength,
        "confidence_pct": setup.confidence_pct,
        "basis_count": len(setup.basis),
        "basis_top3": json.dumps([b.label for b in setup.basis[:3]], ensure_ascii=False),
        "final_status": outcome.new_status.value if outcome.status_changed else "detected",
        "hypothetical_pnl_usd": outcome.hypothetical_pnl_usd,
        "hypothetical_r": outcome.hypothetical_r,
        "time_to_outcome_min": outcome.time_to_outcome_min,
    }


def _print_summary(rows: list[dict[str, Any]]) -> None:
    total = len(rows)
    if total == 0:
        print("\n[RESULT] No setups detected.")
        return

    statuses: dict[str, int] = {}
    by_type: dict[str, int] = {}
    total_pnl = 0.0
    wins = 0

    for r in rows:
        st = str(r.get("final_status", "?"))
        statuses[st] = statuses.get(st, 0) + 1
        t = str(r.get("setup_type", "?"))
        by_type[t] = by_type.get(t, 0) + 1
        pnl = r.get("hypothetical_pnl_usd") or 0.0
        total_pnl += float(pnl)
        if st in ("tp1_hit", "tp2_hit"):
            wins += 1

    complete = sum(v for k, v in statuses.items() if k not in ("detected", "entry_hit"))
    win_rate = wins / complete * 100 if complete > 0 else 0.0

    print(f"\n{'='*60}")
    print(f"BACKTEST SUMMARY")
    print(f"{'='*60}")
    print(f"Total setups detected : {total}")
    print(f"Win rate (TP1/TP2)    : {wins}/{complete} = {win_rate:.1f}%")
    print(f"Hypothetical PnL      : {total_pnl:+.2f} USD")
    print(f"\nBy status:")
    for k, v in sorted(statuses.items()):
        print(f"  {k:20s} {v}")
    print(f"\nBy type:")
    for k, v in sorted(by_type.items(), key=lambda x: -x[1]):
        print(f"  {k:35s} {v}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Setup detector historical backtest")
    parser.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="End date YYYY-MM-DD")
    parser.add_argument("--frozen-path", default="frozen/ETHUSDT_1m.parquet", help="Path to frozen OHLCV")
    parser.add_argument("--pair", default="ETHUSDT", help="Trading pair symbol")
    parser.add_argument("--output", default="data/historical_setups.parquet", help="Output parquet path")
    parser.add_argument("--step-minutes", type=int, default=5, help="Detection interval in minutes")
    parser.add_argument("--max-setups", type=int, default=None, help="Stop after N setups (for testing)")
    args = parser.parse_args()

    from services.setup_backtest.historical_context import HistoricalContextBuilder
    from services.setup_backtest.outcome_simulator import HistoricalOutcomeSimulator
    from services.setup_backtest.replay_engine import SetupBacktestReplay

    start_ts = _parse_date(args.start)
    end_ts = _parse_date(args.end)

    frozen_path = Path(args.frozen_path)
    if not frozen_path.exists():
        # Try relative to project root
        frozen_path = _ROOT / args.frozen_path
    if not frozen_path.exists():
        logger.error("Frozen data not found: %s", args.frozen_path)
        return 1

    logger.info("Building context from %s (%s)", frozen_path, args.pair)
    ctx_builder = HistoricalContextBuilder(frozen_path, pair=args.pair)

    logger.info("Running replay %s → %s step=%dmin", start_ts.date(), end_ts.date(), args.step_minutes)
    replay = SetupBacktestReplay(ctx_builder, step_minutes=args.step_minutes)

    detected_count = 0

    def _progress(ts: datetime, step: int) -> None:
        nonlocal detected_count
        if step % 500 == 0:
            logger.info("progress: ts=%s step=%d setups_so_far=%d", ts.strftime("%Y-%m-%d %H:%M"), step, detected_count)

    setups = replay.run(start_ts, end_ts, progress_callback=_progress, max_setups=args.max_setups)
    detected_count = len(setups)
    logger.info("Detection done: %d setups found", detected_count)

    if not setups:
        print("\n[INFO] No setups detected in this period.")
        return 0

    logger.info("Simulating outcomes for %d setups...", detected_count)
    simulator = HistoricalOutcomeSimulator(ctx_builder._df_1m)
    outcomes = simulator.simulate_all(setups)

    rows = [_setup_to_row(s, o) for s, o in zip(setups, outcomes)]

    import pandas as pd
    df = pd.DataFrame(rows)

    out_path = Path(args.output)
    if not out_path.is_absolute():
        out_path = _ROOT / args.output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)
    logger.info("Output written: %s (%d rows)", out_path, len(df))

    _print_summary(rows)

    print(f"\nOutput: {out_path}")
    print(f"\nOperator action — full year BTC run:")
    print(f"  python tools/run_setup_backtest.py \\")
    print(f"    --start 2025-05-01 --end 2026-04-30 \\")
    print(f"    --frozen-path backtests/frozen/BTCUSDT_1m_2y.csv --pair BTCUSDT \\")
    print(f"    --output data/historical_setups_y1_2026-04-30.parquet")
    print(f"  ETA: 30-60 min on full year")

    return 0


if __name__ == "__main__":
    sys.exit(main())
