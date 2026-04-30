"""Unit tests for tools/calibrate_ginarea.py — parsing and K calculations."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.calibrate_ginarea import (
    GINAREA_GROUND_TRUTH,
    CalibRow,
    group_stats,
    has_sign_flip,
    safe_k,
    verdict,
)


# ---------------------------------------------------------------------------
# 1. Ground truth payload completeness
# ---------------------------------------------------------------------------
class TestGroundTruthPayload:
    def test_nine_entries(self):
        assert len(GINAREA_GROUND_TRUTH) == 9

    def test_six_short_three_long(self):
        shorts = [e for e in GINAREA_GROUND_TRUTH if e["side"] == "SHORT"]
        longs  = [e for e in GINAREA_GROUND_TRUTH if e["side"] == "LONG"]
        assert len(shorts) == 6
        assert len(longs)  == 3

    def test_short_required_fields(self):
        required = {"bot_id", "side", "contract", "td", "ga_realized", "ga_volume", "ga_triggers",
                    "grid_step", "order_count", "order_size", "instop", "min_stop", "max_stop"}
        for entry in GINAREA_GROUND_TRUTH:
            if entry["side"] == "SHORT":
                missing = required - set(entry.keys())
                assert not missing, f"Missing fields in {entry['bot_id']}: {missing}"

    def test_short_contract_linear(self):
        for e in GINAREA_GROUND_TRUTH:
            if e["side"] == "SHORT":
                assert e["contract"] == "LINEAR", f"{e['bot_id']} should be LINEAR"

    def test_long_contract_inverse(self):
        for e in GINAREA_GROUND_TRUTH:
            if e["side"] == "LONG":
                assert e["contract"] == "INVERSE", f"{e['bot_id']} should be INVERSE"

    def test_td_values_short(self):
        td_vals = sorted(e["td"] for e in GINAREA_GROUND_TRUTH if e["side"] == "SHORT")
        assert td_vals == [0.19, 0.21, 0.25, 0.30, 0.35, 0.45]

    def test_td_values_long(self):
        td_vals = sorted(e["td"] for e in GINAREA_GROUND_TRUTH if e["side"] == "LONG")
        assert td_vals == [0.25, 0.30, 0.45]

    def test_short_realized_positive(self):
        for e in GINAREA_GROUND_TRUTH:
            if e["side"] == "SHORT":
                assert e["ga_realized"] > 0, f"{e['bot_id']} realized should be positive"

    def test_short_triggers_positive_int(self):
        for e in GINAREA_GROUND_TRUTH:
            if e["side"] == "SHORT":
                assert isinstance(e["ga_triggers"], int) and e["ga_triggers"] > 0

    def test_long_triggers_none(self):
        for e in GINAREA_GROUND_TRUTH:
            if e["side"] == "LONG":
                assert e["ga_triggers"] is None, f"{e['bot_id']} LONG triggers should be None"


# ---------------------------------------------------------------------------
# 2. safe_k calculations
# ---------------------------------------------------------------------------
class TestSafeK:
    def test_basic_ratio(self):
        assert abs(safe_k(100.0, 10.0) - 10.0) < 1e-9

    def test_zero_denominator(self):
        assert safe_k(100.0, 0.0) is None

    def test_nan_numerator(self):
        assert safe_k(float("nan"), 5.0) is None

    def test_nan_denominator(self):
        assert safe_k(5.0, float("nan")) is None

    def test_fractional(self):
        k = safe_k(42616.75, 4000.0)
        assert abs(k - 10.654) < 0.001

    def test_negative_ok(self):
        k = safe_k(-500.0, 100.0)
        assert abs(k - (-5.0)) < 1e-9


# ---------------------------------------------------------------------------
# 3. group_stats and verdict
# ---------------------------------------------------------------------------
class TestGroupStats:
    def test_stable_cv_below_15(self):
        ks = [10.0, 10.5, 10.2, 9.8, 10.1, 10.3]
        st = group_stats(ks)
        assert st["cv"] < 15.0
        assert verdict(st["cv"]) == "STABLE"

    def test_td_dependent_cv_15_to_35(self):
        ks = [8.0, 10.0, 12.0, 11.0, 13.0, 9.0]
        st = group_stats(ks)
        assert 15.0 <= st["cv"] < 35.0
        assert verdict(st["cv"]) == "TD-DEPENDENT"

    def test_fractured_cv_above_35(self):
        ks = [1.0, 5.0, 20.0]
        st = group_stats(ks)
        assert st["cv"] >= 35.0
        assert verdict(st["cv"]) == "FRACTURED"

    def test_single_element_std_zero(self):
        st = group_stats([10.0])
        assert st["std"] == 0.0
        assert st["cv"] == 0.0

    def test_empty_returns_none(self):
        st = group_stats([])
        assert st["mean"] is None
        assert st["n"] == 0

    def test_mean_std_correct(self):
        ks = [10.0, 12.0, 14.0]
        st = group_stats(ks)
        assert abs(st["mean"] - 12.0) < 1e-9
        import statistics
        assert abs(st["std"] - statistics.stdev(ks)) < 1e-9

    def test_verdict_boundary_15(self):
        assert verdict(14.99) == "STABLE"
        assert verdict(15.00) == "TD-DEPENDENT"

    def test_verdict_boundary_35(self):
        assert verdict(34.99) == "TD-DEPENDENT"
        assert verdict(35.00) == "FRACTURED"

    def test_verdict_none(self):
        assert verdict(None) == "UNKNOWN"


# ---------------------------------------------------------------------------
# 4. CalibRow normalization logic
# ---------------------------------------------------------------------------
class TestCalibRowNormalization:
    def _make_row(self, bot_id, side, td, sim_realized, ga_realized, k_realized):
        return CalibRow(
            bot_id=bot_id, side=side, contract="LINEAR", td=td,
            sim_trades=100, ga_triggers=500,
            k_trades=5.0,
            sim_realized=sim_realized,
            ga_realized=ga_realized,
            k_realized=k_realized,
            sim_volume=1000.0, ga_volume=10000.0, k_volume=10.0,
            normalized_sim_realized=sim_realized * k_realized,
        )

    def test_normalized_within_20pct_of_ga(self):
        row = self._make_row("X", "SHORT", 0.25, 4000.0, 38909.93, 9.727)
        err_pct = abs(row.normalized_sim_realized - row.ga_realized) / row.ga_realized * 100
        assert err_pct < 20.0, f"Normalized err {err_pct:.1f}% exceeds 20%"

    def test_k_volume_ratio_plausible(self):
        row = self._make_row("Y", "SHORT", 0.30, 4200.0, 42616.75, 10.147)
        # GinArea volume >> sim volume (resolution gap)
        assert row.k_volume == 10.0
        assert row.k_volume > 1.0


# ---------------------------------------------------------------------------
# 5. verdict() abs(cv) correction — Fix A2
# ---------------------------------------------------------------------------
class TestVerdictAbsCV:
    def test_negative_cv_not_stable_large(self):
        # CV = -676.2 (SHORT sign-flip group from calibration data)
        assert verdict(-676.2) != "STABLE"

    def test_negative_cv_not_stable_medium(self):
        assert verdict(-50.0) != "STABLE"
        assert verdict(-35.0) != "STABLE"

    def test_negative_cv_near_boundary(self):
        # abs(-15.0) == 15.0 → TD-DEPENDENT, not STABLE
        assert verdict(-15.0) != "STABLE"
        assert verdict(-15.0) == "TD-DEPENDENT"

    def test_abs_value_used_positive_and_negative_symmetry(self):
        assert verdict(14.99) == "STABLE"
        assert verdict(-14.99) == "STABLE"
        assert verdict(35.0) == "FRACTURED"
        assert verdict(-35.0) == "FRACTURED"
        assert verdict(-676.2) == "FRACTURED"


# ---------------------------------------------------------------------------
# 6. has_sign_flip helper
# ---------------------------------------------------------------------------
class TestHasSignFlip:
    def test_sign_flip_detected(self):
        # SHORT K values from calibration: some negative, some positive
        ks = [-497.11, 267.15, -101.29, 37.75, 34.47, 33.19]
        st = group_stats(ks)
        assert has_sign_flip(st) is True

    def test_all_positive_no_flip(self):
        ks = [33.19, 34.47, 37.75]
        st = group_stats(ks)
        assert has_sign_flip(st) is False

    def test_all_negative_no_flip(self):
        ks = [-5.0, -3.0, -1.0]
        st = group_stats(ks)
        assert has_sign_flip(st) is False

    def test_zero_min_not_flip(self):
        # min=0 not < 0, so no flip
        ks = [0.0, 5.0, 10.0]
        st = group_stats(ks)
        assert has_sign_flip(st) is False

    def test_empty_stats_no_flip(self):
        st = group_stats([])
        assert has_sign_flip(st) is False
