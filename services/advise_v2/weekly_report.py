from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from .action_tracker import ActionTaken, FollowupHorizon, iter_followups, iter_matches
from .signal_logger import iter_signals


class SetupBreakdown(BaseModel):
    """Per-setup metrics."""

    model_config = ConfigDict(extra="forbid")

    pattern_id: str
    signals_count: int
    matches_count: int
    actions: dict[str, int]
    avg_pnl_if_followed: float | None = None
    avg_pnl_if_ignored: float | None = None
    edge_followed_vs_ignored: float | None = None
    sample_size_for_edge: int = 0


class WeeklyReport(BaseModel):
    """Generated weekly summary."""

    model_config = ConfigDict(extra="forbid")

    period_start: datetime
    period_end: datetime
    total_signals: int
    total_matches: int
    total_followups: int
    coverage_rate: float = Field(..., ge=0, le=1)
    overall_action_breakdown: dict[str, int]
    setups: list[SetupBreakdown]
    blind_spots: list[dict]
    hits: list[dict]
    notes: list[str] = Field(default_factory=list)


def generate_weekly_report(
    period_start: datetime,
    period_end: datetime,
    signals_log: Path | None = None,
    matches_log: Path | None = None,
    followup_log: Path | None = None,
) -> WeeklyReport:
    """
    Read advise_v2 JSONL logs and aggregate a weekly comparison report.

    The interval is closed-open: [period_start, period_end).
    Both boundaries must be timezone-aware.
    """
    if period_start.tzinfo is None or period_start.utcoffset() is None:
        raise ValueError("period_start and period_end must be tz-aware")
    if period_end.tzinfo is None or period_end.utcoffset() is None:
        raise ValueError("period_start and period_end must be tz-aware")
    if period_start >= period_end:
        raise ValueError("period_start must be < period_end")

    signals_in_window = [
        env for env in iter_signals(signals_log)
        if period_start <= env.ts < period_end
    ]

    matches_dict = {match.signal_id: match for match in iter_matches(matches_log)}
    followups_dict: dict[str, list] = defaultdict(list)
    for followup in iter_followups(followup_log):
        followups_dict[followup.signal_id].append(followup)

    total_signals = len(signals_in_window)
    total_matches = sum(1 for env in signals_in_window if env.signal_id in matches_dict)
    coverage_rate = total_matches / total_signals if total_signals else 0.0

    overall_action_breakdown: dict[str, int] = defaultdict(int)
    setups_dict: dict[str, list] = defaultdict(list)

    for env in signals_in_window:
        setups_dict[env.setup_id].append(env)
        match = matches_dict.get(env.signal_id)
        if match is None:
            overall_action_breakdown["unmatched"] += 1
        else:
            overall_action_breakdown[match.action_taken.value] += 1

    setup_breakdowns: list[SetupBreakdown] = []
    for pattern_id, envs in sorted(setups_dict.items()):
        setup_actions: dict[str, int] = defaultdict(int)
        pnl_followed: list[float] = []
        pnl_ignored: list[float] = []

        for env in envs:
            match = matches_dict.get(env.signal_id)
            followup_24h = next(
                (f for f in followups_dict.get(env.signal_id, []) if f.horizon == FollowupHorizon.H24),
                None,
            )
            pnl_24h = None if followup_24h is None else followup_24h.estimated_pnl_usd

            if match is None:
                setup_actions["unmatched"] += 1
                if pnl_24h is not None:
                    pnl_ignored.append(pnl_24h)
                continue

            setup_actions[match.action_taken.value] += 1
            if pnl_24h is None:
                continue

            if match.action_taken in (ActionTaken.YES_FULL, ActionTaken.YES_PARTIAL):
                pnl_followed.append(pnl_24h)
            elif match.action_taken in (ActionTaken.NO_IGNORED, ActionTaken.NO_MARKET_MOVED):
                pnl_ignored.append(pnl_24h)

        avg_followed = sum(pnl_followed) / len(pnl_followed) if pnl_followed else None
        avg_ignored = sum(pnl_ignored) / len(pnl_ignored) if pnl_ignored else None
        edge = (
            avg_followed - avg_ignored
            if avg_followed is not None and avg_ignored is not None
            else None
        )
        setup_breakdowns.append(
            SetupBreakdown(
                pattern_id=pattern_id,
                signals_count=len(envs),
                matches_count=sum(count for key, count in setup_actions.items() if key != "unmatched"),
                actions=dict(setup_actions),
                avg_pnl_if_followed=avg_followed,
                avg_pnl_if_ignored=avg_ignored,
                edge_followed_vs_ignored=edge,
                sample_size_for_edge=min(len(pnl_followed), len(pnl_ignored)),
            )
        )

    blind_spots: list[dict] = []
    hits: list[dict] = []
    for env in signals_in_window:
        match = matches_dict.get(env.signal_id)
        followup_24h = next(
            (f for f in followups_dict.get(env.signal_id, []) if f.horizon == FollowupHorizon.H24),
            None,
        )
        if followup_24h is None or followup_24h.estimated_pnl_usd is None:
            continue

        if match is not None and match.action_taken == ActionTaken.NO_IGNORED:
            if followup_24h.estimated_pnl_usd > 0:
                blind_spots.append(
                    {
                        "signal_id": env.signal_id,
                        "setup_id": env.setup_id,
                        "missed_pnl_usd": followup_24h.estimated_pnl_usd,
                    }
                )

        if match is not None and match.action_taken in (ActionTaken.YES_FULL, ActionTaken.YES_PARTIAL):
            if followup_24h.estimated_pnl_usd > 0:
                hits.append(
                    {
                        "signal_id": env.signal_id,
                        "setup_id": env.setup_id,
                        "realized_pnl_usd": followup_24h.estimated_pnl_usd,
                    }
                )

    notes: list[str] = []
    if total_signals == 0:
        notes.append("no signals в window")
    if coverage_rate < 0.3 and total_signals > 5:
        notes.append("low coverage rate")

    total_followups = sum(len(items) for items in followups_dict.values())

    return WeeklyReport(
        period_start=period_start,
        period_end=period_end,
        total_signals=total_signals,
        total_matches=total_matches,
        total_followups=total_followups,
        coverage_rate=coverage_rate,
        overall_action_breakdown=dict(overall_action_breakdown),
        setups=setup_breakdowns,
        blind_spots=blind_spots,
        hits=hits,
        notes=notes,
    )


def report_to_markdown(report: WeeklyReport) -> str:
    """Convert WeeklyReport to human-readable markdown."""
    lines = [
        "# Weekly Comparison Report",
        "",
        f"**Period:** {report.period_start.isoformat()} → {report.period_end.isoformat()}",
        "",
        "## Overview",
        f"- Total signals: {report.total_signals}",
        f"- Matches: {report.total_matches} ({report.coverage_rate * 100:.1f}% coverage)",
        f"- Followups: {report.total_followups}",
        "",
        "## Action breakdown",
    ]
    for action, count in sorted(report.overall_action_breakdown.items()):
        lines.append(f"- {action}: {count}")
    lines.append("")
    lines.append("## Per-setup breakdown")
    for setup in report.setups:
        lines.append(f"### {setup.pattern_id}")
        lines.append(f"- Signals: {setup.signals_count}, matches: {setup.matches_count}")
        if setup.edge_followed_vs_ignored is not None:
            lines.append(
                f"- Edge (followed - ignored): {setup.edge_followed_vs_ignored:+.2f} USD "
                f"(n={setup.sample_size_for_edge})"
            )
        lines.append("")
    if report.blind_spots:
        lines.append("## Blind spots (operator ignored, market followed)")
        for spot in report.blind_spots[:10]:
            lines.append(
                f"- {spot['signal_id']} ({spot['setup_id']}): missed +${spot['missed_pnl_usd']:.0f}"
            )
        lines.append("")
    if report.hits:
        lines.append("## Hits (operator followed, profitable)")
        for hit in report.hits[:10]:
            lines.append(
                f"- {hit['signal_id']} ({hit['setup_id']}): +${hit['realized_pnl_usd']:.0f}"
            )
    if report.notes:
        lines.append("## Notes")
        for note in report.notes:
            lines.append(f"- {note}")
    return "\n".join(lines)
