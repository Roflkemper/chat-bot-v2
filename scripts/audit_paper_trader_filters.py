"""Retrospective audit фильтров paper_trader.

Прогоняет existing paper_trades.jsonl + liquidations.csv и считает:
- сколько OPEN-событий за последние N дней попали бы под cascade_filter
- сколько проигрышей streak_guard заблокировал бы
- какой % убытка сэкономлен

Запуск: python scripts/audit_paper_trader_filters.py [--days 7]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.paper_trader.cascade_filter import recent_cascade_volume_btc, THRESHOLD_BTC, COOLDOWN_MIN
from services.paper_trader.streak_guard import MAX_LOSS_STREAK, PAUSE_HOURS


JOURNAL = ROOT / "state" / "paper_trades.jsonl"
LIQ_CSV = ROOT / "market_live" / "liquidations.csv"


def _parse_ts(ts_str: str) -> datetime | None:
    try:
        ts = datetime.fromisoformat(ts_str)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts
    except (ValueError, TypeError):
        return None


def _load_journal(path: Path) -> list[dict]:
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


def _reconstruct_trades(events: list[dict]) -> list[dict]:
    """Сворачиваем OPEN + closing event в одну запись."""
    by_id: dict[str, dict] = {}
    for e in events:
        tid = e.get("trade_id")
        if not tid:
            continue
        action = e.get("action")
        if action == "OPEN":
            by_id[tid] = {"open": e, "close": None}
        elif action in ("SL", "TP1", "TP2", "EXPIRE", "CANCEL") and tid in by_id:
            if by_id[tid]["close"] is None:  # keep first closing event
                by_id[tid]["close"] = e
    return list(by_id.values())


def _simulate_streak_block(trades: list[dict], max_streak: int = MAX_LOSS_STREAK, pause_hours: int = PAUSE_HOURS) -> set[str]:
    """Возвращаем set trade_id'ов которые были бы заблокированы streak_guard."""
    trades_sorted = sorted(trades, key=lambda t: t["open"].get("ts", ""))
    streak = 0
    last_sl_ts: datetime | None = None
    blocked: set[str] = set()
    for t in trades_sorted:
        open_ts = _parse_ts(t["open"].get("ts", ""))
        if open_ts is None:
            continue
        if streak >= max_streak and last_sl_ts is not None:
            elapsed_h = (open_ts - last_sl_ts).total_seconds() / 3600
            if elapsed_h < pause_hours:
                blocked.add(t["open"].get("trade_id", ""))
                continue
        close = t.get("close")
        if close is None:
            continue
        action = close.get("action")
        if action == "SL":
            streak += 1
            last_sl_ts = _parse_ts(close.get("ts", ""))
        elif action in ("TP1", "TP2"):
            streak = 0
            last_sl_ts = None
    return blocked


def audit(days: int = 7) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    events = _load_journal(JOURNAL)
    trades = _reconstruct_trades(events)
    recent = [
        t for t in trades
        if (open_ts := _parse_ts(t["open"].get("ts", ""))) and open_ts >= cutoff
        and t["open"].get("strategy") != "p15"  # p15 не идёт через open_paper_trade
    ]

    streak_blocked = _simulate_streak_block(recent)

    cascade_blocked: list[dict] = []
    survived: list[dict] = []
    for t in recent:
        open_ev = t["open"]
        tid = open_ev.get("trade_id", "")
        if tid in streak_blocked:
            continue  # streak уже заблокировал
        open_ts = _parse_ts(open_ev.get("ts", ""))
        if open_ts is None:
            continue
        vol = recent_cascade_volume_btc(now=open_ts, csv_path=LIQ_CSV)
        rec = {
            "trade_id": tid,
            "ts": open_ev.get("ts"),
            "side": open_ev.get("side"),
            "type": open_ev.get("setup_type"),
            "pnl": (t["close"] or {}).get("realized_pnl_usd"),
            "recent_liq_btc": round(vol, 1),
        }
        if vol >= THRESHOLD_BTC:
            cascade_blocked.append(rec)
        else:
            survived.append(rec)

    streak_blocked_records = [
        {
            "trade_id": t["open"].get("trade_id"),
            "ts": t["open"].get("ts"),
            "side": t["open"].get("side"),
            "type": t["open"].get("setup_type"),
            "pnl": (t["close"] or {}).get("realized_pnl_usd"),
        }
        for t in recent if t["open"].get("trade_id") in streak_blocked
    ]

    def _sum_pnl(rs: list[dict]) -> float:
        return sum((r.get("pnl") or 0.0) for r in rs)

    print(f"=== Paper-trader filter audit ({days}d window) ===\n")
    print(f"Total OPEN events:    {len(recent)}")
    print(f"Blocked by streak:    {len(streak_blocked_records)}")
    print(f"Blocked by cascade:   {len(cascade_blocked)}")
    print(f"Survived both:        {len(survived)}\n")

    pnl_streak = _sum_pnl(streak_blocked_records)
    pnl_cascade = _sum_pnl(cascade_blocked)
    pnl_survived = _sum_pnl(survived)
    pnl_all = _sum_pnl([{"pnl": (t["close"] or {}).get("realized_pnl_usd")} for t in recent])

    print(f"PnL без фильтров:     {pnl_all:+.0f} $")
    print(f"PnL заблокированных streak:  {pnl_streak:+.0f} $ (saved)")
    print(f"PnL заблокированных cascade: {pnl_cascade:+.0f} $ (saved)")
    print(f"PnL после фильтров:   {pnl_survived:+.0f} $")
    print(f"Δ улучшение:          {pnl_survived - pnl_all:+.0f} $\n")

    if cascade_blocked:
        print("--- Cascade-blocked trades ---")
        for r in cascade_blocked:
            pnl_v = r.get("pnl") or 0
            print(f"  {r['ts']}  {r['side']:5s} {r['type']:35s} liq={r['recent_liq_btc']:6.1f} BTC  pnl={pnl_v:+.0f}$")
    if streak_blocked_records:
        print("\n--- Streak-blocked trades ---")
        for r in streak_blocked_records:
            pnl = r.get("pnl") or 0
            print(f"  {r['ts']}  {r['side']:5s} {r['type']:35s} pnl={pnl:+.0f}$")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()
    audit(days=args.days)
