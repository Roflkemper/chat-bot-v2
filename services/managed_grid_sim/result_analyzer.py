from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from .models import InterventionType, ManagedRunResult, TrendType


@dataclass(frozen=True, slots=True)
class SweepAnalysisResult:
    sweep_id: str
    total_runs: int
    pareto_frontier: list[ManagedRunResult]
    grouped_by_trend_type: dict[TrendType, list[ManagedRunResult]]
    best_per_metric: dict[str, ManagedRunResult]
    sensitivity_analysis: dict[str, float]
    hard_ban_check: list[str]


class SweepAnalyzer:
    def __init__(self, sweep_id: str = "sweep") -> None:
        self.sweep_id = sweep_id

    def analyze(self, all_runs: list[ManagedRunResult]) -> SweepAnalysisResult:
        grouped: dict[TrendType, list[ManagedRunResult]] = {}
        for run in all_runs:
            grouped.setdefault(run.trend_type, []).append(run)
        best = {
            "final_realized_pnl_usd": max(all_runs, key=lambda item: item.final_realized_pnl_usd),
            "sharpe_ratio": max(all_runs, key=lambda item: item.sharpe_ratio),
            "total_volume_usd": max(all_runs, key=lambda item: item.total_volume_usd),
            "max_drawdown_pct": min(all_runs, key=lambda item: item.max_drawdown_pct),
        } if all_runs else {}
        pareto = self._pareto(all_runs)
        hard_bans = self._detect_hard_bans(all_runs)
        sensitivity = {"total_interventions": sum(run.total_interventions for run in all_runs) / len(all_runs)} if all_runs else {}
        return SweepAnalysisResult(
            sweep_id=self.sweep_id,
            total_runs=len(all_runs),
            pareto_frontier=pareto,
            grouped_by_trend_type=grouped,
            best_per_metric=best,
            sensitivity_analysis=sensitivity,
            hard_ban_check=hard_bans,
        )

    def _pareto(self, runs: list[ManagedRunResult]) -> list[ManagedRunResult]:
        ordered = sorted(runs, key=lambda item: (-item.final_realized_pnl_usd, item.max_drawdown_pct))
        frontier: list[ManagedRunResult] = []
        best_dd = float("inf")
        for run in ordered:
            if run.max_drawdown_pct <= best_dd:
                frontier.append(run)
                best_dd = run.max_drawdown_pct
        return frontier

    def _detect_hard_bans(self, runs: list[ManagedRunResult]) -> list[str]:
        findings: list[str] = []
        for run in runs:
            if run.interventions_by_type.get(InterventionType.PARTIAL_UNLOAD, 0) > 0 and run.final_realized_pnl_usd < 0:
                findings.append(f"{run.run_id}: p5_partial_unload_with_realized_loss")
        return findings

    def write_report(self, analysis: SweepAnalysisResult, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            f"# Sweep Report: {analysis.sweep_id}",
            "",
            f"- Total runs: {analysis.total_runs}",
            f"- Pareto frontier size: {len(analysis.pareto_frontier)}",
            "",
            "## Best per metric",
        ]
        for metric, run in analysis.best_per_metric.items():
            lines.append(f"- {metric}: {run.run_id}")
        lines.append("")
        lines.append("## Hard ban check")
        if analysis.hard_ban_check:
            for item in analysis.hard_ban_check:
                lines.append(f"- {item}")
        else:
            lines.append("- none")
        output_path.write_text("\n".join(lines), encoding="utf-8")
        return output_path
