"""Дашборд эффективности фильтров paper_trader: накопительные метрики по дням.

Прогоняет journal + источники фильтров (CSV ликвидаций + decision_log) и
группирует результаты по календарным дням UTC. Для каждого дня считает:
- сколько сделок было бы открыто (raw)
- сколько отрезано каждым фильтром
- PnL без фильтров vs PnL после фильтров vs Δ улучшение

CLI: `python scripts/filter_dashboard.py --days 14`
TG:  `/filter_dashboard [N]`
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from services.paper_trader.audit_report import (
    _load_journal,
    _parse_ts,
    _reconstruct,
    _simulate_streak,
)
from services.paper_trader.cascade_filter import THRESHOLD_BTC, recent_cascade_volume_btc
from services.paper_trader.regime_filter import WINDOW_MIN as REGIME_WINDOW_MIN
from services.paper_trader.regime_filter import recent_instability_stability

ROOT = Path(__file__).resolve().parents[2]
LIQ_CSV = ROOT / "market_live" / "liquidations.csv"


class _DayBucket:
    __slots__ = (
        "date", "total", "streak", "cascade", "regime", "survived",
        "pnl_total", "pnl_streak", "pnl_cascade", "pnl_regime", "pnl_survived",
    )

    def __init__(self, date: str) -> None:
        self.date = date
        self.total = 0
        self.streak = 0
        self.cascade = 0
        self.regime = 0
        self.survived = 0
        self.pnl_total = 0.0
        self.pnl_streak = 0.0
        self.pnl_cascade = 0.0
        self.pnl_regime = 0.0
        self.pnl_survived = 0.0


def collect_daily(days: int = 14) -> list[_DayBucket]:
    """Группирует сделки по UTC-дню и считает per-bucket метрики."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    trades = _reconstruct(_load_journal())
    recent = [
        t for t in trades
        if (ts := _parse_ts(t["open"].get("ts", ""))) and ts >= cutoff
        and t["open"].get("strategy") != "p15"
    ]
    streak_blocked = _simulate_streak(recent)
    buckets: dict[str, _DayBucket] = {}

    for t in recent:
        ts = _parse_ts(t["open"].get("ts", ""))
        if ts is None:
            continue
        day = ts.date().isoformat()
        b = buckets.get(day)
        if b is None:
            b = _DayBucket(day)
            buckets[day] = b
        pnl = (t.get("close") or {}).get("realized_pnl_usd") or 0.0
        b.total += 1
        b.pnl_total += pnl
        tid = t["open"].get("trade_id", "")
        if tid in streak_blocked:
            b.streak += 1
            b.pnl_streak += pnl
            continue
        vol = recent_cascade_volume_btc(now=ts, csv_path=LIQ_CSV, use_cache=False)
        if vol >= THRESHOLD_BTC:
            b.cascade += 1
            b.pnl_cascade += pnl
            continue
        if recent_instability_stability(now=ts, window_min=REGIME_WINDOW_MIN) is not None:
            b.regime += 1
            b.pnl_regime += pnl
            continue
        b.survived += 1
        b.pnl_survived += pnl

    return sorted(buckets.values(), key=lambda x: x.date)


def render_dashboard(days: int = 14) -> str:
    """Текстовый отчёт для TG/CLI."""
    rows = collect_daily(days=days)
    if not rows:
        return f"📊 Дашборд фильтров ({days}д): нет сделок в окне."

    cum_total = sum(b.total for b in rows)
    cum_blocked = sum(b.streak + b.cascade + b.regime for b in rows)
    cum_pnl_total = sum(b.pnl_total for b in rows)
    cum_pnl_survived = sum(b.pnl_survived for b in rows)
    cum_pnl_blocked = sum(b.pnl_streak + b.pnl_cascade + b.pnl_regime for b in rows)
    delta = cum_pnl_survived - cum_pnl_total

    lines = [
        f"📊 Дашборд фильтров paper_trader — {days}д",
        "",
        "День       | Total | Strk | Csc | Rgm | Surv |  PnL | After | Δ",
        "-" * 70,
    ]
    for b in rows:
        delta_row = b.pnl_survived - b.pnl_total
        lines.append(
            f"{b.date} | {b.total:>5} | {b.streak:>4} | {b.cascade:>3} | "
            f"{b.regime:>3} | {b.survived:>4} | "
            f"{b.pnl_total:+5.0f} | {b.pnl_survived:+5.0f} | {delta_row:+5.0f}"
        )
    lines += [
        "-" * 70,
        f"ИТОГО: {cum_total} сделок, заблочено {cum_blocked} "
        f"({cum_blocked / max(cum_total, 1) * 100:.0f}%)",
        f"PnL без фильтров: {cum_pnl_total:+.0f}$  |  "
        f"После: {cum_pnl_survived:+.0f}$  |  Δ {delta:+.0f}$",
        f"Заблочено PnL: {cum_pnl_blocked:+.0f}$ "
        f"(streak {sum(b.pnl_streak for b in rows):+.0f} / "
        f"cascade {sum(b.pnl_cascade for b in rows):+.0f} / "
        f"regime {sum(b.pnl_regime for b in rows):+.0f})",
    ]
    return "\n".join(lines)
