from pathlib import Path

from tools import sweep_runner


def test_cli_dry_run_shows_count_no_execution(capsys):
    rc = sweep_runner.main(
        [
            "--config",
            "C:/bot7/configs/sweep/p15_sweep.yaml",
            "--ohlcv",
            "C:/bot7/tests/services/managed_grid_sim/fixtures/synthetic_ohlcv_case.json",
            "--output",
            "C:/bot7/tests/services/managed_grid_sim/fixtures/out",
            "--dry-run",
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "expand to" in out


def test_cli_with_max_runs_limits_execution(tmp_path, capsys):
    rc = sweep_runner.main(
        [
            "--config",
            "C:/bot7/configs/sweep/p15_sweep.yaml",
            "--ohlcv",
            "C:/bot7/tests/services/managed_grid_sim/fixtures/synthetic_ohlcv_case.json",
            "--output",
            str(tmp_path),
            "--max-runs",
            "2",
            "--parallelism",
            "1",
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "completed 2 runs" in out
    assert (tmp_path / "report.md").exists()
