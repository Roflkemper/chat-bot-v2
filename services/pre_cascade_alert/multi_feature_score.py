"""Phase-2 multi-feature pre-cascade score.

Объединяет 4 источника в weighted total:
1. liq_cluster_score — мелкие liq на одной стороне за 5 мин (главный сигнал, R&D z=20).
2. oi_delta_score — рост OI за 1h (концентрация позиций).
3. funding_flip_score — резкое изменение funding в сторону экстрима.
4. ls_imbalance_score — global LS ratio crowded на одну сторону.

Каждый компонент нормализован к 0..1 (clamp). Weighted sum: 0..2+.
Threshold для high-confidence: total >= 1.5.

Логика выбора стороны:
- liq_cluster по long-liq → пре-сигнал LONG-каскада (continuation).
- funding_rate сильно отрицательный → shorts crowded → возможен LONG-squeeze.
- LS-ratio < 0.8 → shorts crowded → LONG-squeeze.
- Эти компоненты не всегда согласны — total идёт по доминирующей стороне.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DERIV_HISTORY_PATH = Path("state/deriv_live_history.jsonl")

# Нормировка (значение которое даёт score=1.0)
LIQ_NORM_BTC = 0.3                  # 0.3 BTC за 5 мин = score 1.0 (Phase-1 threshold)
OI_NORM_PCT_1H = 1.0                # OI рост >=+1% за 1h = score 1.0
FUNDING_FLIP_NORM = 0.0003          # дельта funding 0.03%/8h = score 1.0
LS_IMBALANCE_NORM = 0.5             # |LS - 1.0| >= 0.5 = score 1.0

# Weights (sum=1.0). liq не имеет hard cap — большой кластер сам high confidence.
W_LIQ = 0.5
W_OI = 0.2
W_FUNDING = 0.15
W_LS = 0.15

# Cap на liq_score: 3.0 (т.е. 0.9 BTC за 5 мин = 3× нормы)
LIQ_SCORE_CAP = 3.0

# High confidence: total >= 1.0 (т.е. либо liq=2.0 один, либо liq=1.0 + любые 2 других)
HIGH_CONFIDENCE_THRESHOLD = 1.0


@dataclass
class FeatureScore:
    side: str                    # "long" | "short"
    liq_score: float
    oi_score: float
    funding_flip_score: float
    ls_imbalance_score: float
    total: float                 # weighted sum
    components_text: str         # человекочитаемое описание для TG


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _read_history_tail(*, history_path: Path = DERIV_HISTORY_PATH,
                       n: int = 200) -> list[dict]:
    """Last N snapshots (most recent last)."""
    if not history_path.exists():
        return []
    try:
        lines = history_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    rows = []
    for line in lines[-n:]:
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _snapshot_at_offset(rows: list[dict], target_ts: datetime,
                       *, symbol: str = "BTCUSDT") -> Optional[dict]:
    """Find snapshot closest (and not after) target_ts."""
    best = None
    best_dt = None
    for r in rows:
        ts_str = r.get("last_updated", "")
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except ValueError:
            continue
        if ts > target_ts:
            continue
        dt = (target_ts - ts).total_seconds()
        if best_dt is None or dt < best_dt:
            best_dt = dt
            best = r.get(symbol)
    return best


def compute_score(
    *,
    liq_long_5min: float,
    liq_short_5min: float,
    symbol: str = "BTCUSDT",
    now: Optional[datetime] = None,
    history_path: Path = DERIV_HISTORY_PATH,
) -> FeatureScore:
    """Compute weighted Phase-2 score for current moment.

    Returns FeatureScore for the dominant side (whichever has higher total).
    """
    if now is None:
        now = datetime.now(timezone.utc)
    rows = _read_history_tail(history_path=history_path)
    now_snap = _snapshot_at_offset(rows, now, symbol=symbol) or {}
    past_snap = _snapshot_at_offset(rows, now - timedelta(hours=1), symbol=symbol) or {}

    # Side-agnostic components
    oi_change_pct = float(now_snap.get("oi_change_1h_pct") or 0.0)
    funding_now = float(now_snap.get("funding_rate_8h") or 0.0)
    funding_past = float(past_snap.get("funding_rate_8h") or 0.0)
    ls_ratio = float(now_snap.get("global_ls_ratio") or 1.0)

    oi_score = _clamp01(abs(oi_change_pct) / OI_NORM_PCT_1H)
    funding_delta = funding_now - funding_past
    funding_flip_score = _clamp01(abs(funding_delta) / FUNDING_FLIP_NORM)
    ls_imbalance_score = _clamp01(abs(ls_ratio - 1.0) / LS_IMBALANCE_NORM)

    # Per-side liq scores — capped at LIQ_SCORE_CAP, not 1.0 (главный сигнал)
    long_liq_score = max(0.0, min(LIQ_SCORE_CAP, liq_long_5min / LIQ_NORM_BTC))
    short_liq_score = max(0.0, min(LIQ_SCORE_CAP, liq_short_5min / LIQ_NORM_BTC))

    # Pick dominant side (which has bigger liq cluster)
    if long_liq_score >= short_liq_score:
        side = "long"
        liq_score = long_liq_score
    else:
        side = "short"
        liq_score = short_liq_score

    total = (W_LIQ * liq_score
             + W_OI * oi_score
             + W_FUNDING * funding_flip_score
             + W_LS * ls_imbalance_score)

    components_text = (
        f"liq={liq_score:.2f} oi={oi_score:.2f} fund_flip={funding_flip_score:.2f} ls={ls_imbalance_score:.2f}"
    )

    return FeatureScore(
        side=side,
        liq_score=round(liq_score, 3),
        oi_score=round(oi_score, 3),
        funding_flip_score=round(funding_flip_score, 3),
        ls_imbalance_score=round(ls_imbalance_score, 3),
        total=round(total, 3),
        components_text=components_text,
    )


def is_high_confidence(score: FeatureScore,
                       threshold: float = HIGH_CONFIDENCE_THRESHOLD) -> bool:
    return score.total >= threshold
