"""Cascade prognosis accuracy tracker.

Записывает каждый каскадный alert (LONG/SHORT, 5BTC/10BTC mega), сохраняет
prediction (например +1.14% за 12ч) и spot-price. Через 4ч/12ч/24ч после
события проверяет realized движение цены и записывает correct/missed.

Это feedback-loop для проверки актуальности backtest-цифр на реальном рынке.
13.05 наблюдалось: каскад LONG в 03:11 предсказывал +1.14% за 12ч, факт
−0.92% — статистика 67%/73% возможно устарела (backtest fev-jun 2024).
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

JOURNAL_PATH = Path("state/cascade_accuracy.jsonl")

# Horizons we evaluate (matches cascade_alert backtest stats)
HORIZONS_HOURS = (4, 12, 24)


@dataclass
class CascadePrognosis:
    ts: str                        # ISO when alert fired
    direction: str                 # "long" / "short" (which side was liquidated)
    threshold_btc: float           # 5.0 / 10.0
    spot_price: float
    qty_btc: float
    predicted_pct_12h: float       # avg from backtest
    # Filled by evaluator
    realized_pct_4h: float | None = None
    realized_pct_12h: float | None = None
    realized_pct_24h: float | None = None
    correct_4h: bool | None = None
    correct_12h: bool | None = None
    correct_24h: bool | None = None
    evaluated_at: str | None = None


def record_prognosis(p: CascadePrognosis, *, path: Path = JOURNAL_PATH) -> None:
    """Append a new prognosis row to journal."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(p), ensure_ascii=False) + "\n")
    except OSError:
        logger.exception("accuracy_tracker.append_failed")


def read_journal(*, path: Path = JOURNAL_PATH) -> list[dict]:
    if not path.exists():
        return []
    out = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError:
        return []
    return out


def write_journal(rows: list[dict], *, path: Path = JOURNAL_PATH) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    except OSError:
        logger.exception("accuracy_tracker.write_failed")


def _parse_ts(s: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def evaluate_pending(
    *,
    get_price_fn,
    now: datetime | None = None,
    path: Path = JOURNAL_PATH,
) -> int:
    """Заполнить realized_pct для прогнозов где прошло >= horizons часов.

    get_price_fn: callable(datetime) -> price at given ts (or close approximation).
    Returns count of newly evaluated horizons.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    rows = read_journal(path=path)
    n_filled = 0
    for r in rows:
        ts = _parse_ts(r.get("ts", ""))
        if ts is None:
            continue
        spot = r.get("spot_price")
        if spot is None or spot <= 0:
            continue
        # LONG-cascade ⇒ predicted UP. SHORT-cascade ⇒ predicted UP too historically,
        # but we track signed direction:
        direction = r.get("direction", "long")
        expected_sign = +1  # both LONG and SHORT cascades backtest predicts UP move
        for h in HORIZONS_HOURS:
            key = f"realized_pct_{h}h"
            if r.get(key) is not None:
                continue  # already evaluated
            target_ts = ts + timedelta(hours=h)
            if now < target_ts:
                continue
            try:
                future_price = get_price_fn(target_ts)
            except Exception:
                logger.exception("accuracy_tracker.price_fn_failed")
                continue
            if future_price is None or future_price <= 0:
                continue
            change_pct = (future_price - spot) / spot * 100.0
            r[key] = round(change_pct, 3)
            r[f"correct_{h}h"] = (change_pct * expected_sign > 0)
            n_filled += 1
        r["evaluated_at"] = now.isoformat()
    if n_filled > 0:
        write_journal(rows, path=path)
    return n_filled


def summary(
    *,
    path: Path = JOURNAL_PATH,
    min_samples: int = 5,
) -> dict:
    """Return aggregate accuracy stats by direction × horizon."""
    rows = read_journal(path=path)
    if not rows:
        return {"total": 0, "by_horizon": {}}
    out: dict[str, dict] = {"long": {}, "short": {}, "mega_long": {}, "mega_short": {}}
    for r in rows:
        d = r.get("direction", "long")
        thresh = r.get("threshold_btc", 5.0)
        bucket = f"mega_{d}" if thresh >= 10.0 else d
        b = out.setdefault(bucket, {})
        for h in HORIZONS_HOURS:
            key = f"correct_{h}h"
            corr = r.get(key)
            if corr is None:
                continue
            stats = b.setdefault(h, {"correct": 0, "total": 0})
            stats["total"] += 1
            if corr:
                stats["correct"] += 1
    result: dict = {"total": len(rows), "by_bucket": {}}
    for bucket, horizons in out.items():
        result["by_bucket"][bucket] = {}
        for h, s in horizons.items():
            if s["total"] < min_samples:
                continue
            result["by_bucket"][bucket][f"{h}h"] = {
                "n": s["total"],
                "accuracy": round(s["correct"] / s["total"] * 100, 1),
            }
    return result
