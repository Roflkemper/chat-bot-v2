from pathlib import Path

from tools import sweep_runner

_REPO_ROOT = Path(__file__).resolve().parents[2]
P15_SWEEP = str(_REPO_ROOT / "configs" / "sweep" / "p15_sweep.yaml")
OHLCV_FIXTURE = str(_REPO_ROOT / "tests" / "services" / "managed_grid_sim"
                    / "fixtures" / "synthetic_ohlcv_case.json")
OUT_DIR = str(_REPO_ROOT / "tests" / "services" / "managed_grid_sim" / "fixtures" / "out")


def test_cli_dry_run_shows_count_no_execution(capsys):
    rc = sweep_runner.main(
        [
            "--config", P15_SWEEP,
            "--ohlcv", OHLCV_FIXTURE,
            "--output", OUT_DIR,
            "--dry-run",
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "expand to" in out


def test_cli_with_max_runs_limits_execution(tmp_path, capsys):
    rc = sweep_runner.main(
        [
            "--config", P15_SWEEP,
            "--ohlcv", OHLCV_FIXTURE,
            "--output", str(tmp_path),
            "--max-runs", "2",
            "--parallelism", "1",
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "completed 2 runs" in out
    assert (tmp_path / "report.md").exists()
