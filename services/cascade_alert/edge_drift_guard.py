"""Edge drift guard: circuit-breaker для cascade alert.

Логика:
- читает summary() из accuracy_tracker
- по каждому бакету (long/short/mega_*) × горизонту (4h/12h/24h):
  если n >= MIN_SAMPLES и accuracy < MIN_ACCURACY_PCT — отмечаем edge как drifted
- сохраняет state в state/cascade_edge_drift.json:
  {"long_12h": {"drifted": True, "accuracy": 52.3, "n": 15, "ts": "..."}, ...}
- предоставляет is_drifted(direction, threshold) для cascade_alert/loop.py
- при первом обнаружении drift — посылает TG-предупреждение (idempotent)

Контекст: 13.05 LONG-каскад в 03:11 предсказывал +1.14%/12h, факт −0.92%.
Backtest n=103 (фев-июнь 2024) может устареть. Этот guard поймает дрейф автоматически.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

STATE_PATH = Path("state/cascade_edge_drift.json")

MIN_SAMPLES = 10            # требуем >=10 событий чтобы делать вывод
MIN_ACCURACY_PCT = 60.0     # ниже — edge считается выдохшимся
PRIMARY_HORIZON = "12h"     # ключевой горизонт для решения


@dataclass
class DriftStatus:
    bucket: str          # "long" / "short" / "mega_long" / "mega_short"
    horizon: str         # "4h" / "12h" / "24h"
    n: int
    accuracy: float
    drifted: bool
    detected_at: Optional[str] = None  # ISO ts when first marked drifted


def _read_state(path: Path = STATE_PATH) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_state(state: dict, path: Path = STATE_PATH) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        logger.exception("edge_drift_guard.write_failed")


def evaluate_drift(
    *,
    summary_fn: Callable[..., dict],
    send_fn: Optional[Callable[[str], None]] = None,
    state_path: Path = STATE_PATH,
    min_samples: int = MIN_SAMPLES,
    min_accuracy: float = MIN_ACCURACY_PCT,
    now: Optional[datetime] = None,
) -> list[DriftStatus]:
    """Прочитать summary, оценить дрейф по всем (bucket, horizon).

    Returns: список DriftStatus (только те где есть данные >= min_samples).
    Side-effects: записывает state, при первом обнаружении drift шлёт send_fn.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    state = _read_state(state_path)
    summary = summary_fn(min_samples=min_samples)
    by_bucket = summary.get("by_bucket", {})

    statuses: list[DriftStatus] = []
    newly_drifted: list[DriftStatus] = []

    for bucket, horizons in by_bucket.items():
        for h_key, s in horizons.items():
            n = int(s.get("n", 0))
            acc = float(s.get("accuracy", 0.0))
            if n < min_samples:
                continue
            drifted = acc < min_accuracy
            state_key = f"{bucket}_{h_key}"
            prev = state.get(state_key, {})
            was_drifted = bool(prev.get("drifted", False))

            detected_at = prev.get("detected_at")
            if drifted and not was_drifted:
                detected_at = now.isoformat(timespec="seconds")
                newly_drifted.append(DriftStatus(
                    bucket=bucket, horizon=h_key, n=n, accuracy=acc,
                    drifted=True, detected_at=detected_at,
                ))
            elif not drifted:
                detected_at = None

            state[state_key] = {
                "drifted": drifted,
                "accuracy": acc,
                "n": n,
                "horizon": h_key,
                "bucket": bucket,
                "detected_at": detected_at,
                "last_eval": now.isoformat(timespec="seconds"),
            }
            statuses.append(DriftStatus(
                bucket=bucket, horizon=h_key, n=n, accuracy=acc,
                drifted=drifted, detected_at=detected_at,
            ))

    _write_state(state, state_path)

    if newly_drifted and send_fn is not None:
        for ds in newly_drifted:
            text = (
                f"⚠️ EDGE DRIFT detected\n"
                f"bucket: {ds.bucket}, horizon: {ds.horizon}\n"
                f"accuracy: {ds.accuracy:.1f}% (n={ds.n}, threshold {min_accuracy:.0f}%)\n"
                f"→ cascade-alerts по этому направлению помечаются как stale.\n"
                f"Backtest n=103 из фев-июн 2024 возможно устарел, нужен re-sweep."
            )
            try:
                send_fn(text)
            except Exception:
                logger.exception("edge_drift_guard.send_failed")

    return statuses


def is_drifted(
    direction: str,
    threshold_btc: float,
    *,
    horizon: str = PRIMARY_HORIZON,
    state_path: Path = STATE_PATH,
) -> bool:
    """Quick lookup: дрейфует ли edge для (direction, threshold) на данном горизонте."""
    state = _read_state(state_path)
    bucket = f"mega_{direction}" if threshold_btc >= 10.0 else direction
    entry = state.get(f"{bucket}_{horizon}", {})
    return bool(entry.get("drifted", False))


def get_status_summary(*, state_path: Path = STATE_PATH) -> dict:
    """Human-readable summary всех текущих drift-флагов."""
    state = _read_state(state_path)
    drifted = [k for k, v in state.items() if v.get("drifted")]
    healthy = [k for k, v in state.items() if not v.get("drifted")]
    return {
        "drifted_count": len(drifted),
        "healthy_count": len(healthy),
        "drifted": drifted,
        "all_entries": state,
    }
