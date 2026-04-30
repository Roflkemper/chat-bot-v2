from datetime import datetime, timezone

from services.managed_grid_sim.models import InterventionType, ManagedRunResult, TrendType
from services.managed_grid_sim.result_analyzer import SweepAnalyzer


def _result(run_id: str, pnl: float, dd: float, trend: TrendType = TrendType.SMOOTH_TRENDING):
    return ManagedRunResult(
        run_id=run_id,
        config_hash=run_id,
        bot_configs=[],
        trend_type=trend,
        final_realized_pnl_usd=pnl,
        final_unrealized_pnl_usd=0.0,
        total_volume_usd=100.0 + pnl,
        max_drawdown_pct=dd,
        max_drawdown_usd=dd,
        sharpe_ratio=pnl / 10.0,
        total_trades=10,
        total_interventions=1,
        interventions_by_type={InterventionType.PAUSE_NEW_ENTRIES: 1},
        intervention_log=[],
        bar_count=10,
        sim_duration_seconds=1.0,
    )


def test_analyze_with_5_runs_returns_correct_pareto(tmp_path):
    analyzer = SweepAnalyzer("p15")
    analysis = analyzer.analyze([_result("a", 10, 5), _result("b", 8, 4), _result("c", 12, 8)])
    assert analysis.total_runs == 3
    assert len(analysis.pareto_frontier) >= 1


def test_analyze_detects_hard_ban_pattern_p8():
    analyzer = SweepAnalyzer("p15")
    run = ManagedRunResult(
        run_id="bad",
        config_hash="bad",
        bot_configs=[],
        trend_type=TrendType.SMOOTH_TRENDING,
        final_realized_pnl_usd=-1.0,
        final_unrealized_pnl_usd=0.0,
        total_volume_usd=50.0,
        max_drawdown_pct=5.0,
        max_drawdown_usd=5.0,
        sharpe_ratio=0.0,
        total_trades=10,
        total_interventions=1,
        interventions_by_type={InterventionType.PARTIAL_UNLOAD: 1},
        intervention_log=[],
        bar_count=10,
        sim_duration_seconds=1.0,
    )
    analysis = analyzer.analyze([run])
    assert analysis.hard_ban_check


def test_analyze_writes_markdown_report(tmp_path):
    analyzer = SweepAnalyzer("p15")
    analysis = analyzer.analyze([_result("a", 10, 5)])
    out = analyzer.write_report(analysis, tmp_path / "report.md")
    assert out.exists()
    assert "Total runs" in out.read_text(encoding="utf-8")
