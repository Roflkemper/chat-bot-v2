from services.managed_grid_sim.intervention_rules import (
    ActivateBoosterOnImpulseExhaustion,
    ModifyParamsOnRegimeChange,
    PartialUnloadOnRetracement,
    PauseEntriesOnUnrealizedThreshold,
    RaiseBoundaryOnConfirmedTrend,
    ResumeEntriesOnPullback,
)
from services.managed_grid_sim.models import BotState, RegimeLabel


def _state(**overrides):
    data = {
        "bot_id": "short_main",
        "bot_alias": "short_main",
        "side": "short",
        "contract_type": "linear",
        "is_active": True,
        "position_size_native": 1.0,
        "position_size_usd": 100.0,
        "avg_entry_price": 100.0,
        "unrealized_pnl_usd": -10.0,
        "hold_time_minutes": 120,
        "bar_count_in_drawdown": 10,
        "max_unrealized_pnl_usd": 50.0,
        "min_unrealized_pnl_usd": -20.0,
        "params_current": {},
        "params_original": {},
    }
    data.update(overrides)
    return BotState(**data)


def test_pause_rule_triggers_when_threshold_crossed(sample_snapshot):
    rule = PauseEntriesOnUnrealizedThreshold(-5.0, 60, ["short_main"])
    decision = rule.evaluate(sample_snapshot, _state(unrealized_pnl_usd=-8.0), [])
    assert decision is not None
    assert decision.intervention_type.value == "pause_new_entries"


def test_resume_rule_after_pullback(sample_snapshot):
    rule = ResumeEntriesOnPullback(20.0, 60, ["short_main"])
    recent = [_state(is_active=False, unrealized_pnl_usd=40.0, max_unrealized_pnl_usd=40.0), _state(is_active=False, unrealized_pnl_usd=20.0, max_unrealized_pnl_usd=40.0)]
    decision = rule.evaluate(sample_snapshot, recent[-1], recent)
    assert decision is not None
    assert decision.intervention_type.value == "resume_new_entries"


def test_partial_unload_only_when_unrealized_positive(sample_snapshot):
    rule = PartialUnloadOnRetracement(0.0, 20.0, 0.5, ["short_main"])
    recent = [_state(unrealized_pnl_usd=100.0, max_unrealized_pnl_usd=100.0), _state(unrealized_pnl_usd=70.0, max_unrealized_pnl_usd=100.0)]
    decision = rule.evaluate(sample_snapshot, recent[-1], recent)
    assert decision is not None
    assert decision.partial_unload_fraction == 0.5


def test_modify_params_on_regime_change(sample_snapshot):
    rule = ModifyParamsOnRegimeChange(RegimeLabel.TREND_UP, {"grid_step_pct": 0.05}, ["short_main"])
    decision = rule.evaluate(sample_snapshot, _state(), [])
    assert decision is not None
    assert decision.params_modification == {"grid_step_pct": 0.05}


def test_activate_booster_with_liq_cluster_proximity(sample_snapshot):
    rule = ActivateBoosterOnImpulseExhaustion(2.0, 1.0, 1.0, 0.5, 1.5, ["short_main"])
    decision = rule.evaluate(sample_snapshot, _state(), [])
    assert decision is not None
    assert decision.booster_config is not None


def test_raise_boundary_after_confirmed_trend(sample_snapshot):
    rule = RaiseBoundaryOnConfirmedTrend(2.0, 60, 0.5, ["short_main"])
    decision = rule.evaluate(sample_snapshot, _state(), [])
    assert decision is not None
    assert "boundaries_upper" in (decision.params_modification or {})
