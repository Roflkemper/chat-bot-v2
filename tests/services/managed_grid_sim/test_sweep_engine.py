from pathlib import Path

from services.managed_grid_sim.managed_runner import ManagedGridSimRunner
from services.managed_grid_sim.sweep_engine import SweepEngine

from .conftest import fake_engine_loader


def test_expand_simple_sweep_to_correct_count(sample_bars):
    engine = SweepEngine(sample_bars[:5], None, Path("C:/bot7/configs/sweep/p15_sweep.yaml"), parallelism=1, runner=ManagedGridSimRunner(engine_loader=fake_engine_loader))
    runs = engine.expand_to_runs()
    assert len(runs) == 32


def test_expand_yaml_with_no_ranges_returns_single_run(tmp_path, sample_bars):
    path = tmp_path / "one.yaml"
    path.write_text(
        "sweep_id: one\nbase_bot_configs:\n  - bot_id: a\n    alias: a\n    side: short\n    contract_type: linear\n    order_size: 1\n    order_count: 10\n    grid_step_pct: 0.03\n    target_profit_pct: 0.21\n    min_stop_pct: 0.01\n    max_stop_pct: 0.04\n    instop_pct: 0.01\n    boundaries_lower: 0\n    boundaries_upper: 999999\nintervention_rules: []\n",
        encoding="utf-8",
    )
    engine = SweepEngine(sample_bars[:5], None, path, parallelism=1, runner=ManagedGridSimRunner(engine_loader=fake_engine_loader))
    runs = engine.expand_to_runs()
    assert len(runs) == 1


def test_execute_all_returns_results_for_each_config(sample_bars):
    engine = SweepEngine(sample_bars[:5], None, Path("C:/bot7/configs/sweep/p15_sweep.yaml"), parallelism=1, runner=ManagedGridSimRunner(engine_loader=fake_engine_loader))
    runs = engine.expand_to_runs()[:2]
    results = engine.execute_all(runs)
    assert len(results) == 2
