from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import SetupStatus, SetupType

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_SETUPS_JSONL = _ROOT / "state" / "setups.jsonl"
_DEFAULT_OUTCOMES_JSONL = _ROOT / "state" / "setup_outcomes.jsonl"
_DEFAULT_HISTORICAL_PARQUET = _ROOT / "data" / "historical_setups.parquet"

_TERMINAL = {
    SetupStatus.TP1_HIT.value,
    SetupStatus.TP2_HIT.value,
    SetupStatus.STOP_HIT.value,
    SetupStatus.EXPIRED.value,
    SetupStatus.INVALIDATED.value,
}
_WIN = {SetupStatus.TP1_HIT.value, SetupStatus.TP2_HIT.value}


@dataclass
class TypeStats:
    setup_type: str
    detected: int = 0
    filled: int = 0
    wins: int = 0
    losses: int = 0
    total_pnl_usd: float = 0.0
    mean_r: float = 0.0
    win_rate: float = 0.0


@dataclass
class SessionStats:
    session: str
    detected: int = 0
    wins: int = 0
    total_pnl_usd: float = 0.0


@dataclass
class RegimeStats:
    regime: str
    detected: int = 0
    wins: int = 0
    total_pnl_usd: float = 0.0


@dataclass
class SetupStats:
    generated_at: datetime
    lookback_days: int
    total_detected: int
    total_filled: int
    total_complete: int
    by_type: dict[str, TypeStats] = field(default_factory=dict)
    by_session: dict[str, SessionStats] = field(default_factory=dict)
    by_regime: dict[str, RegimeStats] = field(default_factory=dict)
    total_hypothetical_pnl_usd: float = 0.0
    total_hypothetical_pnl_strength_7plus: float = 0.0
    total_hypothetical_pnl_strength_8plus: float = 0.0
    source_live_count: int = 0
    source_backtest_count: int = 0


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def _is_recent(ts_str: str, cutoff_ts: float) -> bool:
    try:
        ts = datetime.fromisoformat(ts_str)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts.timestamp() >= cutoff_ts
    except Exception:
        return False


def compute_setup_stats(
    lookback_days: int = 7,
    include_backtest: bool = True,
    setups_path: Path | None = None,
    outcomes_path: Path | None = None,
    historical_path: Path | None = None,
) -> SetupStats:
    now = datetime.now(timezone.utc)
    cutoff_ts = now.timestamp() - lookback_days * 86400

    setups_raw = _load_jsonl(setups_path or _DEFAULT_SETUPS_JSONL)
    outcomes_raw = _load_jsonl(outcomes_path or _DEFAULT_OUTCOMES_JSONL)

    # Build outcome lookup by setup_id
    outcomes_by_id: dict[str, dict[str, Any]] = {}
    for o in outcomes_raw:
        sid = o.get("setup_id", "")
        if sid and o.get("new_status") in _TERMINAL:
            outcomes_by_id[sid] = o

    # Filter by recency
    recent_setups = [s for s in setups_raw if _is_recent(s.get("detected_at", ""), cutoff_ts)]

    # Include historical backtest data if available
    hist_rows: list[dict[str, Any]] = []
    if include_backtest:
        hist_path = historical_path or _DEFAULT_HISTORICAL_PARQUET
        if hist_path.exists():
            try:
                import pandas as pd
                hdf = pd.read_parquet(hist_path)
                hist_rows = hdf.to_dict("records")
            except Exception:
                logger.exception("stats_aggregator.load_historical_failed")

    all_setups = recent_setups
    hist_count = len(hist_rows)
    live_count = len(recent_setups)

    # Build stats
    by_type: dict[str, TypeStats] = {}
    by_session: dict[str, SessionStats] = {}
    by_regime: dict[str, RegimeStats] = {}
    total_pnl = 0.0
    pnl_7plus = 0.0
    pnl_8plus = 0.0
    total_filled = 0
    total_complete = 0

    def _process_row(row: dict[str, Any], outcome: dict[str, Any] | None) -> None:
        nonlocal total_pnl, pnl_7plus, pnl_8plus, total_filled, total_complete

        st = str(row.get("setup_type", "unknown"))
        sess = str(row.get("session_label", "NONE"))
        regime = str(row.get("regime_label", "unknown"))
        strength = int(row.get("strength", 0))
        pnl = float(outcome.get("hypothetical_pnl_usd", 0.0) or 0.0) if outcome else 0.0
        is_filled = outcome is not None and outcome.get("new_status") in (
            SetupStatus.ENTRY_HIT.value, *list(_WIN), SetupStatus.STOP_HIT.value
        )
        is_complete = outcome is not None and outcome.get("new_status") in _TERMINAL
        is_win = outcome is not None and outcome.get("new_status") in _WIN

        if is_filled:
            total_filled += 1
        if is_complete:
            total_complete += 1
            total_pnl += pnl
            if strength >= 7:
                pnl_7plus += pnl
            if strength >= 8:
                pnl_8plus += pnl

        # by_type
        if st not in by_type:
            by_type[st] = TypeStats(setup_type=st)
        ts = by_type[st]
        ts.detected += 1
        if is_filled:
            ts.filled += 1
        if is_win:
            ts.wins += 1
        if is_complete and not is_win:
            ts.losses += 1
        ts.total_pnl_usd += pnl

        # by_session
        if sess not in by_session:
            by_session[sess] = SessionStats(session=sess)
        ss = by_session[sess]
        ss.detected += 1
        if is_win:
            ss.wins += 1
        ss.total_pnl_usd += pnl

        # by_regime
        if regime not in by_regime:
            by_regime[regime] = RegimeStats(regime=regime)
        rs = by_regime[regime]
        rs.detected += 1
        if is_win:
            rs.wins += 1
        rs.total_pnl_usd += pnl

    for row in all_setups:
        sid = row.get("setup_id", "")
        outcome = outcomes_by_id.get(sid)
        _process_row(row, outcome)

    for row in hist_rows:
        _process_row(row, row if row.get("final_status") in _TERMINAL else None)

    # Compute derived stats
    for ts in by_type.values():
        denom = ts.wins + ts.losses
        ts.win_rate = ts.wins / denom if denom > 0 else 0.0

    return SetupStats(
        generated_at=now,
        lookback_days=lookback_days,
        total_detected=len(all_setups) + hist_count,
        total_filled=total_filled,
        total_complete=total_complete,
        by_type=by_type,
        by_session=by_session,
        by_regime=by_regime,
        total_hypothetical_pnl_usd=round(total_pnl, 2),
        total_hypothetical_pnl_strength_7plus=round(pnl_7plus, 2),
        total_hypothetical_pnl_strength_8plus=round(pnl_8plus, 2),
        source_live_count=live_count,
        source_backtest_count=hist_count,
    )


def format_stats_card(stats: SetupStats) -> str:
    """Compact Telegram stats card, ~25-30 lines."""
    lines = [
        f"📊 SETUP STATS — {stats.generated_at.strftime('%Y-%m-%d %H:%M UTC')}",
        f"Период: {stats.lookback_days}д | Live: {stats.source_live_count} | Backtest: {stats.source_backtest_count}",
        "",
        f"Всего детектировано: {stats.total_detected}",
        f"Вход исполнен: {stats.total_filled}",
        f"Завершено (TP/SL/exp): {stats.total_complete}",
        f"Hypothetical PnL: {stats.total_hypothetical_pnl_usd:+.0f} USD",
        f"  Strength ≥7: {stats.total_hypothetical_pnl_strength_7plus:+.0f} USD",
        f"  Strength ≥8: {stats.total_hypothetical_pnl_strength_8plus:+.0f} USD",
        "",
        "BY TYPE:",
    ]
    for ts in sorted(stats.by_type.values(), key=lambda x: -x.detected)[:6]:
        wr = f"{ts.win_rate*100:.0f}%" if ts.wins + ts.losses > 0 else "—"
        lines.append(
            f"  {ts.setup_type:30s} det={ts.detected} win={wr} pnl={ts.total_pnl_usd:+.0f}"
        )
    lines.append("")
    lines.append("BY SESSION:")
    for ss in sorted(stats.by_session.values(), key=lambda x: -x.detected)[:5]:
        lines.append(f"  {ss.session:12s} det={ss.detected} wins={ss.wins}")
    lines.append("")
    lines.append("BY REGIME:")
    for rs in sorted(stats.by_regime.values(), key=lambda x: -x.detected)[:5]:
        lines.append(f"  {rs.regime:20s} det={rs.detected} wins={rs.wins}")

    return "\n".join(lines)
