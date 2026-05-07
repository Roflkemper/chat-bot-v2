"""Дозаполняет outcome поля в state/exit_advisor_decisions.jsonl.

Запускать раз в час из cron / supervisor / scheduled task.
Для каждой decision где outcome_*h_pnl_change == None и прошло >= 1h/4h/24h:
- Читает live state (current_price из deriv_live)
- Читает старый snapshot (btc_price на момент decision)
- Пишет btc_move_pct
- pnl_change оставляет None (требует position_state historical, не реализовано)

Ограничение: pnl_change честно нельзя посчитать без historical position snapshots.
Сейчас ограничиваемся только btc_move (как proxy для overall portfolio impact).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.exit_advisor.decisions_log import load_decisions, overwrite_decisions, DECISIONS_PATH


def _read_btc_price_at(target_ts: datetime) -> float | None:
    """Read close price from market_1m.csv ближайший к target_ts."""
    import csv
    p = ROOT / "market_live" / "market_1m.csv"
    if not p.exists():
        return None
    target_epoch = target_ts.timestamp()
    best: tuple[float, float] | None = None
    try:
        with p.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ts_s = row.get("ts_utc") or row.get("timestamp") or ""
                if not ts_s:
                    continue
                try:
                    ts = datetime.fromisoformat(ts_s.replace("Z", "+00:00")).timestamp()
                except ValueError:
                    continue
                diff = abs(ts - target_epoch)
                if diff > 600:
                    continue
                try:
                    price = float(row.get("close") or 0)
                except ValueError:
                    continue
                if price <= 0:
                    continue
                if best is None or diff < best[0]:
                    best = (diff, price)
    except OSError:
        return None
    return best[1] if best else None


def fill_outcomes() -> dict:
    decisions = load_decisions()
    now = datetime.now(timezone.utc)
    updated = 0

    for d in decisions:
        try:
            ts_dec = datetime.fromisoformat(d["ts_utc"].replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        snap = d.get("snapshot", {}) or {}
        price_then = snap.get("btc_price") or 0
        if price_then <= 0:
            continue

        for hours, key in [(1, "1h"), (4, "4h"), (24, "24h")]:
            field = f"outcome_{key}_btc_move_pct"
            if d.get(field) is not None:
                continue
            if now - ts_dec < timedelta(hours=hours):
                continue
            target = ts_dec + timedelta(hours=hours)
            price_then_v = float(price_then)
            price_target = _read_btc_price_at(target)
            if price_target is None:
                continue
            move_pct = (price_target / price_then_v - 1) * 100
            d[field] = round(move_pct, 3)
            updated += 1

    if updated:
        overwrite_decisions(decisions)

    return {"updated": updated, "total_decisions": len(decisions)}


if __name__ == "__main__":
    res = fill_outcomes()
    print(json.dumps(res, ensure_ascii=False, indent=2))
