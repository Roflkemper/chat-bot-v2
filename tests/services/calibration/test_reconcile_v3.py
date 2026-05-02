"""Tests for services/calibration/reconcile_v3.py — TZ-ENGINE-FIX-RESOLUTION."""
from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from services.calibration.reconcile_v3 import (
    GAPoint,
    ResolutionResult,
    _aggregate_by_side,
    check_direct_k_feasible,
    csv_span_iso,
    k_factor,
    load_ga_points,
    overlap_window,
    run_resolution_sensitivity,
)
from services.calibration.sim import SimResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_csv(path: Path, rows: list[tuple[int, float, float, float, float, float]]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ts", "open", "high", "low", "close", "volume"])
        for r in rows:
            w.writerow(r)


def _flat_bars_1m(start_ms: int, n: int, price: float = 75000.0) -> list[tuple]:
    return [
        (start_ms + i * 60_000, price, price, price, price, 0.0)
        for i in range(n)
    ]


def _flat_bars_1s(start_ms: int, n: int, price: float = 75000.0) -> list[tuple]:
    return [
        (start_ms + i * 1_000, price, price, price, price, 0.0)
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# 1. Data span detection
# ---------------------------------------------------------------------------

class TestCsvSpanIso:
    def test_reads_first_and_last_timestamp(self, tmp_path):
        f = tmp_path / "ohlcv.csv"
        _write_csv(f, [
            (1_000_000_000_000, 100.0, 100.5, 99.5, 100.2, 1.0),
            (1_000_000_060_000, 100.2, 100.8, 100.0, 100.4, 1.0),
            (1_000_000_120_000, 100.4, 101.0, 100.2, 100.6, 1.0),
        ])
        first, last = csv_span_iso(f)
        assert first.startswith("2001-09-09")
        assert last.startswith("2001-09-09")
        assert first < last

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            csv_span_iso(tmp_path / "nonexistent.csv")


# ---------------------------------------------------------------------------
# 2. overlap_window logic
# ---------------------------------------------------------------------------

class TestOverlapWindow:
    def test_overlap_intersect(self):
        a = ("2026-04-01T00:00:00+00:00", "2026-04-30T00:00:00+00:00")
        b = ("2026-04-15T00:00:00+00:00", "2026-05-15T00:00:00+00:00")
        assert overlap_window(a, b) == (
            "2026-04-15T00:00:00+00:00",
            "2026-04-30T00:00:00+00:00",
        )

    def test_disjoint_returns_none(self):
        a = ("2025-01-01T00:00:00+00:00", "2025-01-31T00:00:00+00:00")
        b = ("2026-01-01T00:00:00+00:00", "2026-01-31T00:00:00+00:00")
        assert overlap_window(a, b) is None


# ---------------------------------------------------------------------------
# 3. K-factor formula
# ---------------------------------------------------------------------------

class TestKFactor:
    def test_basic(self):
        # ga 100 / sim 10 → K = 10
        assert k_factor(ga_realized=100.0, sim_realized=10.0) == 10.0

    def test_zero_sim_returns_nan(self):
        assert math.isnan(k_factor(100.0, 0.0))

    def test_negative_values(self):
        # SHORT loss
        assert k_factor(-200.0, -20.0) == 10.0


# ---------------------------------------------------------------------------
# 4. GA ground-truth loader
# ---------------------------------------------------------------------------

class TestLoadGAPoints:
    def test_parses_short_and_long(self, tmp_path):
        gt = {
            "version": "test",
            "common_short_params": {
                "order_size_btc": 0.003, "grid_step_pct": 0.03,
                "max_trigger_number": 800,
            },
            "common_long_params": {
                "order_size_usd": 200, "grid_step_pct": 0.03,
                "max_trigger_number": 800,
            },
            "points": [
                {"id": "111", "side": "short", "target_pct": 0.21,
                 "ginarea_results": {"realized_pnl_usd": 1000.0}},
                {"id": "222", "side": "long", "target_pct": 0.30,
                 "ginarea_results": {"realized_pnl_btc": 0.5}},
            ],
        }
        gt_path = tmp_path / "gt.json"
        gt_path.write_text(json.dumps(gt), encoding="utf-8")

        points = load_ga_points(gt_path)
        assert len(points) == 2
        s = next(p for p in points if p.side == "SHORT")
        assert s.bot_id == "111"
        assert s.target_pct == 0.21
        assert s.order_size == 0.003
        assert s.ga_realized == 1000.0
        l = next(p for p in points if p.side == "LONG")
        assert l.order_size == 200.0
        assert l.ga_realized == 0.5  # BTC-denominated for COIN-M


# ---------------------------------------------------------------------------
# 5. Aggregation (mean / std / CV)
# ---------------------------------------------------------------------------

class TestAggregateBySide:
    def _make_result(self, side: str, sim_1m_realized: float, sim_1s_realized: float
                     ) -> ResolutionResult:
        p = GAPoint(
            bot_id="x", side=side, target_pct=0.21, order_size=0.003,
            grid_step_pct=0.03, max_orders=800, ga_realized=0.0,
        )
        return ResolutionResult(
            point=p,
            window_start="2026-04-02T00:00:00+00:00",
            window_end="2026-05-02T00:00:00+00:00",
            sim_1m=SimResult(
                side=side, target_pct=0.21, realized_pnl=sim_1m_realized,
                trading_volume_usd=0.0, num_fills=0, unrealized_pnl=0.0,
                last_price=0.0,
            ),
            sim_1s=SimResult(
                side=side, target_pct=0.21, realized_pnl=sim_1s_realized,
                trading_volume_usd=0.0, num_fills=0, unrealized_pnl=0.0,
                last_price=0.0,
            ),
        )

    def test_aggregates_short_ratios(self):
        results = [
            self._make_result("SHORT", 100.0, 110.0),  # ratio 1.10
            self._make_result("SHORT", 200.0, 220.0),  # ratio 1.10
            self._make_result("SHORT", 50.0,  55.0),   # ratio 1.10
            self._make_result("LONG",  10.0,  9.5),    # ratio 0.95
        ]
        aggregates = _aggregate_by_side(results)
        assert aggregates["SHORT"].n == 3
        assert abs(aggregates["SHORT"].mean - 1.10) < 1e-9
        assert aggregates["SHORT"].std < 1e-9      # all ratios identical
        assert aggregates["SHORT"].cv_pct < 1e-6
        assert aggregates["LONG"].n == 1
        assert abs(aggregates["LONG"].mean - 0.95) < 1e-9

    def test_zero_baseline_excluded_with_note(self):
        results = [
            self._make_result("SHORT", 0.0, 5.0),    # ratio NaN — excluded
            self._make_result("SHORT", 100.0, 105.0),  # ratio 1.05
        ]
        aggregates = _aggregate_by_side(results)
        assert aggregates["SHORT"].n == 1
        assert any("excluded" in n for n in aggregates["SHORT"].notes)


# ---------------------------------------------------------------------------
# 6. End-to-end probe with synthetic CSVs
# ---------------------------------------------------------------------------

class TestRunResolutionSensitivity:
    """Synthetic flat-price 1m and 1s CSVs → sim returns 0 PnL → ratio NaN.

    Verifies wiring (load + sim invocation per config + aggregation) without
    requiring full 30-day datasets in the test suite.
    """

    def test_synthetic_flat_price_runs_end_to_end(self, tmp_path):
        f_1m = tmp_path / "BTCUSDT_1m_2y.csv"
        f_1s = tmp_path / "BTCUSDT_1s_2y.csv"
        # Two overlapping hours of flat data
        start_ms = 1_777_708_800_000  # 2026-05-01 23:00:00 UTC
        _write_csv(f_1m, _flat_bars_1m(start_ms, 120))      # 2 hours
        _write_csv(f_1s, _flat_bars_1s(start_ms + 30 * 60_000, 7200))  # 2h offset+30min

        ga_points = [
            GAPoint(
                bot_id="t1", side="SHORT", target_pct=0.21,
                order_size=0.003, grid_step_pct=0.03, max_orders=800,
                ga_realized=1000.0,
            ),
            GAPoint(
                bot_id="t2", side="LONG", target_pct=0.30,
                order_size=200.0, grid_step_pct=0.03, max_orders=800,
                ga_realized=500.0,
            ),
        ]
        results, aggregates, meta = run_resolution_sensitivity(
            ga_points, ohlcv_1m=f_1m, ohlcv_1s=f_1s,
        )
        assert len(results) == 2
        assert meta["n_configs"] == 2
        # Flat price → sim_1m and sim_1s both have realized=0 → ratio NaN
        for r in results:
            assert r.sim_1m.realized_pnl == 0.0
            assert r.sim_1s.realized_pnl == 0.0
            assert math.isnan(r.ratio)
        # Aggregates exist for both sides with note about zero baselines
        assert aggregates["SHORT"].n == 0
        assert aggregates["LONG"].n == 0


# ---------------------------------------------------------------------------
# 7. Direct-K feasibility gate
# ---------------------------------------------------------------------------

class TestCheckDirectKFeasible:
    def test_gap_30_days_vs_year_blocks(self):
        ga_period = ("2025-05-01T00:00:00+00:00", "2026-04-30T00:00:00+00:00")
        # 1s span: just 30 days at the end of the GA period
        s_span = ("2026-04-02T00:00:00+00:00", "2026-05-02T00:00:00+00:00")
        ok, reason = check_direct_k_feasible(ga_period, s_span)
        assert not ok
        # Coverage should be roughly 28/365 ≈ 7.7%
        assert "%" in reason

    def test_full_coverage_passes(self):
        ga_period = ("2025-05-01T00:00:00+00:00", "2026-04-30T00:00:00+00:00")
        # 1s span fully covers GA period
        s_span = ("2025-04-01T00:00:00+00:00", "2026-05-15T00:00:00+00:00")
        ok, reason = check_direct_k_feasible(ga_period, s_span)
        assert ok
