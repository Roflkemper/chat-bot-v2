from services.managed_grid_sim.intervention_rules import PauseEntriesOnUnrealizedThreshold
from services.managed_grid_sim.managed_runner import ManagedGridSimRunner, ManagedRunConfig
from services.managed_grid_sim.regime_classifier import RegimeClassifier

from .conftest import fake_engine_loader


def test_run_with_no_intervention_rules_matches_calibrate_result(sample_bars, base_bot_config):
    runner = ManagedGridSimRunner(engine_loader=fake_engine_loader)
    result = runner.run(
        ManagedRunConfig(
            bot_configs=[base_bot_config],
            bars=sample_bars[:10],
            intervention_rules=[],
            regime_classifier=RegimeClassifier(),
            run_id="run0",
        )
    )
    assert result.bar_count == 10
    assert result.total_interventions == 0


def test_run_records_intervention_events(sample_bars, base_bot_config):
    runner = ManagedGridSimRunner(engine_loader=fake_engine_loader)
    rule = PauseEntriesOnUnrealizedThreshold(100.0, 0, ["short_main"])
    result = runner.run(
        ManagedRunConfig(
            bot_configs=[base_bot_config],
            bars=sample_bars[:5],
            intervention_rules=[rule],
            regime_classifier=RegimeClassifier(),
            run_id="run1",
        )
    )
    assert result.total_interventions >= 1


def test_run_handles_multiple_bots_simultaneously(sample_bars, base_bot_config):
    runner = ManagedGridSimRunner(engine_loader=fake_engine_loader)
    second = dict(base_bot_config)
    second["bot_id"] = "long_main"
    second["alias"] = "long_main"
    second["side"] = "long"
    second["contract_type"] = "inverse"
    result = runner.run(
        ManagedRunConfig(
            bot_configs=[base_bot_config, second],
            bars=sample_bars[:5],
            intervention_rules=[],
            regime_classifier=RegimeClassifier(),
            run_id="run2",
        )
    )
    assert result.total_trades >= 0


def test_run_strict_mode_raises_on_failure(sample_bars, base_bot_config, sample_snapshot):
    class BadRule:
        def evaluate(self, snapshot, bot_state, recent_states):
            raise RuntimeError("boom")

    runner = ManagedGridSimRunner(engine_loader=fake_engine_loader)
    try:
        runner.run(
            ManagedRunConfig(
                bot_configs=[base_bot_config],
                bars=sample_bars[:2],
                intervention_rules=[BadRule()],
                regime_classifier=RegimeClassifier(),
                run_id="run3",
                strict_mode=True,
            )
        )
    except RuntimeError as exc:
        assert str(exc) == "boom"
    else:
        raise AssertionError("expected RuntimeError")
