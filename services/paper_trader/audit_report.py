"""Audit-отчёт для TG: эффективность фильтров paper_trader за N дней.

Используется как:
- CLI скриптом `scripts/audit_paper_trader_filters.py` (детальный stdout)
- TG-командой `/audit_filters [N]` (компактный markdown)

Логика блокировки идентична `services/paper_trader/trader.open_paper_trade`:
streak → cascade → regime (в этом порядке).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from services.paper_trader.cascade_filter import THRESHOLD_BTC, recent_cascade_volume_btc
from services.paper_trader.regime_filter import WINDOW_MIN as REGIME_WINDOW_MIN
from services.paper_trader.regime_filter import recent_instability_stability
from services.paper_trader.streak_guard import MAX_LOSS_STREAK, PAUSE_HOURS

ROOT = Path(__file__).resolve().parents[2]
JOURNAL_PATH = ROOT / "state" / "paper_trades.jsonl"
LIQ_CSV = ROOT / "market_live" / "liquidations.csv"


def _parse_ts(ts_str: str) -> datetime | None:
    try:
        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts
    except (ValueError, TypeError):
        return None


def _load_journal(path: Path = JOURNAL_PATH) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _reconstruct(events: list[dict]) -> list[dict]:
    by_id: dict[str, dict] = {}
    for e in events:
        tid = e.get("trade_id")
        if not tid:
            continue
        action = e.get("action")
        if action == "OPEN":
            by_id[tid] = {"open": e, "close": None}
        elif action in ("SL", "TP1", "TP2", "EXPIRE", "CANCEL") and tid in by_id:
            if by_id[tid]["close"] is None:
                by_id[tid]["close"] = e
    return list(by_id.values())


def _simulate_streak(trades: list[dict]) -> set[str]:
    trades_sorted = sorted(trades, key=lambda t: t["open"].get("ts", ""))
    streak = 0
    last_sl_ts: datetime | None = None
    blocked: set[str] = set()
    for t in trades_sorted:
        open_ts = _parse_ts(t["open"].get("ts", ""))
        if open_ts is None:
            continue
        if streak >= MAX_LOSS_STREAK and last_sl_ts is not None:
            if (open_ts - last_sl_ts).total_seconds() / 3600 < PAUSE_HOURS:
                blocked.add(t["open"].get("trade_id", ""))
                continue
        close = t.get("close")
        if close is None:
            continue
        a = close.get("action")
        if a == "SL":
            pnl = close.get("realized_pnl_usd") or 0.0
            if pnl >= 0:
                continue  # break-even SL — не считаем как реальный убыток
            streak += 1
            last_sl_ts = _parse_ts(close.get("ts", ""))
        elif a in ("TP1", "TP2"):
            streak = 0
            last_sl_ts = None
    return blocked


def build_filter_audit(days: int = 7) -> str:
    """Возвращает markdown-отчёт для TG."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    events = _load_journal()
    trades = _reconstruct(events)
    recent = [
        t for t in trades
        if (ts := _parse_ts(t["open"].get("ts", ""))) and ts >= cutoff
        and t["open"].get("strategy") != "p15"
    ]

    if not recent:
        return f"📊 Аудит фильтров paper_trader (за {days}д)\n\nНет OPEN-событий в этом окне."

    streak_blocked = _simulate_streak(recent)
    cascade_n = 0
    regime_n = 0
    survived_n = 0
    pnl_streak = pnl_cascade = pnl_regime = pnl_survived = 0.0

    for t in recent:
        pnl = (t.get("close") or {}).get("realized_pnl_usd") or 0.0
        tid = t["open"].get("trade_id", "")
        if tid in streak_blocked:
            pnl_streak += pnl
            continue
        open_ts = _parse_ts(t["open"].get("ts", ""))
        if open_ts is None:
            continue
        vol = recent_cascade_volume_btc(now=open_ts, csv_path=LIQ_CSV, use_cache=False)
        if vol >= THRESHOLD_BTC:
            cascade_n += 1
            pnl_cascade += pnl
            continue
        low_stab = recent_instability_stability(now=open_ts, window_min=REGIME_WINDOW_MIN)
        if low_stab is not None:
            regime_n += 1
            pnl_regime += pnl
        else:
            survived_n += 1
            pnl_survived += pnl

    pnl_all = sum((t.get("close") or {}).get("realized_pnl_usd") or 0.0 for t in recent)
    delta = pnl_survived - pnl_all
    saved = pnl_streak + pnl_cascade + pnl_regime

    arrow = "📈" if delta > 0 else ("📉" if delta < 0 else "➖")
    lines = [
        f"📊 Аудит фильтров paper_trader — {days}д",
        "",
        f"OPEN-событий:  *{len(recent)}*",
        f"• streak блок: {len(streak_blocked)}",
        f"• cascade блок: {cascade_n}",
        f"• regime блок: {regime_n}",
        f"• выжили:      {survived_n}",
        "",
        f"PnL без фильтров: {pnl_all:+.0f}$",
        f"Заблочено (streak): {pnl_streak:+.0f}$",
        f"Заблочено (cascade): {pnl_cascade:+.0f}$",
        f"Заблочено (regime): {pnl_regime:+.0f}$",
        f"PnL после фильтров: {pnl_survived:+.0f}$",
        "",
        f"{arrow} Δ улучшение: *{delta:+.0f}$* (заблочено {saved:+.0f}$)",
    ]
    return "\n".join(lines)
