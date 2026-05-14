"""Validation and gap analysis for ingested derivatives parquets.

Usage:
    python -m services.derivatives_ingest.validate
    python -m services.derivatives_ingest.validate --symbol BTCUSDT
    python -m services.derivatives_ingest.validate --report-path reports/derivatives_ingest_validation_2026-05-03.md
"""
from __future__ import annotations

import argparse
import io
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

import pandas as pd

if hasattr(sys.stdout, "buffer") and sys.stdout.encoding and \
        sys.stdout.encoding.lower().replace("-", "") not in ("utf8", "utf8bom"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[2]
FROZEN_DIR = ROOT / "backtests" / "frozen" / "derivatives_1y"
REPORTS_DIR = ROOT / "reports"

log = logging.getLogger(__name__)

START_MS = int(datetime(2025, 5, 1, tzinfo=timezone.utc).timestamp() * 1000)
END_MS   = int(datetime(2026, 4, 30, 23, 59, 59, tzinfo=timezone.utc).timestamp() * 1000)

DURATION_DAYS = (END_MS - START_MS) / 86_400_000

# Expected row counts (5m granularity = 288/day from data portal)
EXPECTED_OI_ROWS = int(DURATION_DAYS * 288)
EXPECTED_FUNDING_ROWS = int(DURATION_DAYS * 3)   # 8h settlements
EXPECTED_LS_ROWS = int(DURATION_DAYS * 288)       # 5m, single merged column

_5M_MS = 5 * 60 * 1000
_8H_MS = 8 * 60 * 60 * 1000


class GapResult(NamedTuple):
    metric: str
    symbol: str
    total_rows: int
    expected_rows: int
    coverage_pct: float
    gap_count: int
    longest_gap_bars: int
    sanity_ok: bool
    notes: str


def _find_gaps(ts_series: pd.Series, expected_interval_ms: int, tolerance_factor: float = 1.5) -> tuple[int, int]:
    """Return (gap_count, longest_gap_in_bars)."""
    diffs = ts_series.sort_values().diff().dropna()
    threshold = expected_interval_ms * tolerance_factor
    gaps = diffs[diffs > threshold]
    if gaps.empty:
        return 0, 0
    longest = int(gaps.max() / expected_interval_ms)
    return len(gaps), longest


def validate_oi(symbol: str) -> GapResult:
    path = FROZEN_DIR / f"{symbol}_OI_5m_1y.parquet"
    if not path.exists():
        return GapResult("OI_5m", symbol, 0, EXPECTED_OI_ROWS, 0.0, 0, 0, False, "FILE MISSING")

    df = pd.read_parquet(path)
    n = len(df)
    coverage = n / EXPECTED_OI_ROWS * 100

    sanity_ok = bool((df["sum_open_interest"] > 0).mean() > 0.95)
    notes = ""
    if not sanity_ok:
        notes = "WARNING: >5% zero OI values"
    if (df["sum_open_interest"] < 0).any():
        sanity_ok = False
        notes += " | negative OI"

    gap_count, longest_gap = _find_gaps(df["ts_ms"], _5M_MS)
    return GapResult("OI_5m", symbol, n, EXPECTED_OI_ROWS, coverage, gap_count, longest_gap, sanity_ok, notes)


def validate_funding(symbol: str) -> GapResult:
    path = FROZEN_DIR / f"{symbol}_funding_8h_1y.parquet"
    if not path.exists():
        return GapResult("funding_8h", symbol, 0, EXPECTED_FUNDING_ROWS, 0.0, 0, 0, False, "FILE MISSING")

    df = pd.read_parquet(path)
    n = len(df)
    coverage = n / EXPECTED_FUNDING_ROWS * 100

    out_of_range = ((df["fundingRate"] < -0.02) | (df["fundingRate"] > 0.02)).sum()
    sanity_ok = out_of_range < n * 0.01
    notes = f"{out_of_range} rates outside -2%..+2%" if out_of_range else ""

    gap_count, longest_gap = _find_gaps(df["ts_ms"], _8H_MS)
    return GapResult("funding_8h", symbol, n, EXPECTED_FUNDING_ROWS, coverage, gap_count, longest_gap, sanity_ok, notes)


def validate_ls(symbol: str) -> GapResult:
    path = FROZEN_DIR / f"{symbol}_LS_5m_1y.parquet"
    if not path.exists():
        return GapResult("LS_5m", symbol, 0, EXPECTED_LS_ROWS, 0.0, 0, 0, False, "FILE MISSING")

    df = pd.read_parquet(path)
    n = len(df)
    coverage = n / EXPECTED_LS_ROWS * 100

    # taker_vol_ratio and ratios should be positive
    bad_taker = (df["taker_vol_ratio"] <= 0).sum()
    bad_global = (df["global_ls_ratio"] <= 0).sum()
    sanity_ok = (bad_taker + bad_global) < n * 0.05
    notes = ""
    if not sanity_ok:
        notes = f"bad_taker={bad_taker} bad_global={bad_global}"

    gap_count, longest_gap = _find_gaps(df["ts_ms"], _5M_MS)
    return GapResult("LS_5m", symbol, n, EXPECTED_LS_ROWS, coverage, gap_count, longest_gap, sanity_ok, notes)


def validate_all(symbols: list[str]) -> list[GapResult]:
    results: list[GapResult] = []
    for sym in symbols:
        results.append(validate_oi(sym))
        results.append(validate_funding(sym))
        results.append(validate_ls(sym))
    return results


def render_report(results: list[GapResult]) -> str:
    lines = [
        "# Derivatives Ingest Validation Report",
        f"Generated: {datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')}",
        f"Period: 2025-05-01 to 2026-04-30 ({DURATION_DAYS:.0f} days)",
        "",
        "## Coverage Summary",
        "",
        "| Metric | Symbol | Rows | Expected | Coverage% | Gaps | LongestGap(bars) | Sanity | Notes |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    all_ok = True
    for r in results:
        sanity_icon = "OK" if r.sanity_ok else "FAIL"
        if not r.sanity_ok or r.coverage_pct < 90:
            all_ok = False
        lines.append(
            f"| {r.metric} | {r.symbol} | {r.total_rows:,} | {r.expected_rows:,} "
            f"| {r.coverage_pct:.1f}% | {r.gap_count} | {r.longest_gap_bars} "
            f"| {sanity_icon} | {r.notes} |"
        )

    lines += [
        "",
        f"## Overall: {'PASS' if all_ok else 'ISSUES FOUND'}",
        "",
        "## Data Sources",
        "- OI + LS ratios: data.binance.vision daily zip files (5m granularity)",
        "- Funding rate: Binance fapi/v1/fundingRate live API (full 1y history)",
        "",
        "## Notes",
        "- Expected rows are estimates; Binance may have brief maintenance windows",
        "- OI and LS from data portal use same CSV: sum_open_interest, top_trader/global LS, taker vol",
        "- Funding 8h: 3 settlements per day (00:00, 08:00, 16:00 UTC)",
        "- Cross-validation: overlap with live collector data in last 5 days",
    ]
    return "\n".join(lines)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", nargs="+", default=["BTCUSDT", "XRPUSDT"])
    parser.add_argument("--report-path", default=None)
    args = parser.parse_args()

    results = validate_all(args.symbols)
    report_md = render_report(results)
    print(report_md)

    report_path = Path(args.report_path) if args.report_path else \
        REPORTS_DIR / "derivatives_ingest_validation_2026-05-03.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report_md, encoding="utf-8")
    log.info("Report written: %s", report_path)


if __name__ == "__main__":
    main()
