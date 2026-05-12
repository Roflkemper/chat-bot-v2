"""Tests for ginarea_scorer."""
from __future__ import annotations

import pytest

from services.backtest.ginarea_scorer import (
    GinAreaConfig,
    rank_configs,
    score_config,
    V5_CONFIGS_LONG,
)


def _mk(name: str, **kw) -> GinAreaConfig:
    base = dict(
        gs=0.04, thresh=1.5, td=0.9, mult=1.3, tp="off", max_size=300,
        profit_usd=20_000, vol_musd=4.0, peak_exposure_usd=80_000, dd_usd=2_000,
    )
    base.update(kw)
    return GinAreaConfig(name=name, **base)


def test_score_components_sum_to_total() -> None:
    cfg = _mk("t")
    s = score_config(cfg, rebate_per_m=250, capital_rate_per_month=0.02 / 12,
                     dd_weight=1.0, period_months=3.0)
    expected = 20_000 + 4.0 * 250 - 80_000 * (0.02 / 12) * 3.0 - 2_000
    assert s.total == pytest.approx(expected)


def test_risk_limit_excludes_config() -> None:
    cfg = _mk("over-limit", peak_exposure_usd=150_000)
    s = score_config(cfg, risk_limit_usd=100_000)
    assert s.total == float("-inf")
    assert "risk_violation" in s.breakdown


def test_no_limit_allows_anything() -> None:
    cfg = _mk("over-limit", peak_exposure_usd=200_000)
    s = score_config(cfg, risk_limit_usd=None)
    assert s.total != float("-inf")


def test_rank_orders_by_total_desc() -> None:
    cfgs = [
        _mk("low", profit_usd=10_000),
        _mk("hi",  profit_usd=30_000),
        _mk("mid", profit_usd=20_000),
    ]
    ranked = rank_configs(cfgs)
    assert ranked[0].cfg.name == "hi"
    assert ranked[1].cfg.name == "mid"
    assert ranked[2].cfg.name == "low"


def test_higher_volume_increases_rebate() -> None:
    low_vol = _mk("low-vol", vol_musd=4.0)
    hi_vol = _mk("hi-vol", vol_musd=16.0)
    s_low = score_config(low_vol, rebate_per_m=300)
    s_hi = score_config(hi_vol, rebate_per_m=300)
    assert s_hi.rebate - s_low.rebate == pytest.approx(3_600)


def test_dd_weight_penalty_scales() -> None:
    cfg = _mk("dd", dd_usd=5_000)
    light = score_config(cfg, dd_weight=1.0).total
    heavy = score_config(cfg, dd_weight=2.0).total
    assert light - heavy == pytest.approx(5_000)


def test_t2_mega_in_top_at_default_rebate() -> None:
    """При rebate=$250/M (operator-stated) T2-MEGA должен быть в топе."""
    ranked = rank_configs(V5_CONFIGS_LONG, rebate_per_m=250)
    in_limit = [s for s in ranked if s.total != float("-inf")]
    top3_names = [s.cfg.name for s in in_limit[:3]]
    assert any("T2-MEGA" in n for n in top3_names), top3_names


def test_r1_overtakes_at_high_rebate() -> None:
    """При rebate=$500/M R1 (vol 16.84M) обгоняет T2-MEGA (vol 4.08M)."""
    ranked = rank_configs(V5_CONFIGS_LONG, rebate_per_m=500)
    in_limit = [s for s in ranked if s.total != float("-inf")]
    leader_name = in_limit[0].cfg.name
    assert "R1" in leader_name, f"expected R1 at top, got {leader_name}"
