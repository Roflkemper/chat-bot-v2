"""Дозаполняет outcome поля в state/advise_audit.jsonl.

Запускается раз в час из supervisor'а или scheduled task'и.
Для каждой записи где price_after_4h/24h == None и прошло >= 4h / 24h —
читает живой OHLCV, проставляет фактическую цену и считает correctness.

Verdict correctness (упрощённое):
  LONG verdict → correct если цена выросла >= 0.3% за окно
  SHORT verdict → correct если цена упала >= 0.3%
  RANGE / БОКОВИК / WAIT → correct если |move| < 0.5%
  иначе incorrect

Запуск: python scripts/advise_outcome_filler.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

AUDIT_PATH = Path("state/advise_audit.jsonl")
OHLCV_1M = Path("market_live/market_1m.csv")


def _read_price_at(target_ts: datetime) -> float | None:
    """Читает close из market_1m.csv ближайший к target_ts (±5 минут)."""
    if not OHLCV_1M.exists():
        return None
    import csv
    target_epoch = target_ts.timestamp()
    best: tuple[float, float] | None = None  # (abs_diff, price)
    try:
        with OHLCV_1M.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    ts_str = row.get("ts_utc") or row.get("timestamp") or row.get("ts") or ""
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).timestamp()
                    diff = abs(ts - target_epoch)
                    if diff > 600:  # >10 min — пропускаем
                        continue
                    price = float(row.get("close") or 0)
                    if best is None or diff < best[0]:
                        best = (diff, price)
                except (ValueError, KeyError):
                    continue
    except OSError:
        return None
    return best[1] if best else None


def _verdict_outcome(verdict: str, price_then: float, price_now: float) -> bool | None:
    """True если вердикт совпал с движением, False — нет, None — нельзя оценить."""
    if not price_then or not price_now:
        return None
    move_pct = (price_now / price_then - 1) * 100
    v = (verdict or "").upper()
    if "LONG" in v or "BULL" in v:
        return move_pct >= 0.3
    if "SHORT" in v or "BEAR" in v:
        return move_pct <= -0.3
    if "RANGE" in v or "БОКОВИК" in v or "WAIT" in v or "ПАУЗА" in v:
        return abs(move_pct) < 0.5
    return None


def fill_outcomes() -> dict:
    if not AUDIT_PATH.exists():
        return {"updated": 0, "reason": "no audit file"}

    now = datetime.now(timezone.utc)
    entries = []
    updated = 0

    with AUDIT_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            entries.append(e)

    for e in entries:
        try:
            ts_call = datetime.fromisoformat(e["ts_utc"].replace("Z", "+00:00"))
        except (ValueError, KeyError):
            continue
        price_then = e.get("btc_price")
        if price_then is None:
            continue

        # 4h outcome
        if e.get("price_after_4h") is None and now - ts_call >= timedelta(hours=4):
            target = ts_call + timedelta(hours=4)
            price_4h = _read_price_at(target)
            if price_4h is not None:
                e["price_after_4h"] = price_4h
                e["verdict_correct_4h"] = _verdict_outcome(e.get("verdict", ""), price_then, price_4h)
                updated += 1

        # 24h outcome
        if e.get("price_after_24h") is None and now - ts_call >= timedelta(hours=24):
            target = ts_call + timedelta(hours=24)
            price_24h = _read_price_at(target)
            if price_24h is not None:
                e["price_after_24h"] = price_24h
                e["verdict_correct_24h"] = _verdict_outcome(e.get("verdict", ""), price_then, price_24h)
                updated += 1

    if updated:
        with AUDIT_PATH.open("w", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")

    return {"updated": updated, "total_entries": len(entries)}


if __name__ == "__main__":
    result = fill_outcomes()
    print(json.dumps(result, ensure_ascii=False, indent=2))
