from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from statistics import mean
from typing import Dict, Iterable, List, Literal, Sequence

from storage.pattern_history_store import PatternRecord

Direction = Literal["LONG", "SHORT", "NEUTRAL"]

MIN_MOVE_THRESHOLD = 0.2
MIN_SAMPLE_COUNT = 10
WIN_RATE_THRESHOLD = 0.55
MIN_SIMILARITY_SCORE = 0.60


@dataclass
class MatchCandidate:
    ts: str
    similarity: float
    future_move_pct: float
    direction: Direction
    horizon_bars: int


@dataclass
class RegimeAwarePatternResult:
    direction: Direction
    avg_move_pct: float
    win_rate: float
    sample_count: int
    strength: int
    market_regime: str
    range_position: str
    top_matches: List[MatchCandidate]
    note: str = ""

    @property
    def meaningful(self) -> bool:
        return (
            abs(self.avg_move_pct) >= MIN_MOVE_THRESHOLD
            and self.sample_count >= MIN_SAMPLE_COUNT
            and self.win_rate >= WIN_RATE_THRESHOLD
        )


def _euclid(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 999.0
    return sqrt(sum((float(x) - float(y)) ** 2 for x, y in zip(a, b)))


def _compat_regime(candidate_regime: str, current_regime: str) -> bool:
    if candidate_regime == current_regime:
        return True
    trend_aliases = {"TREND", "TREND_UP", "TREND_DOWN"}
    if candidate_regime in trend_aliases and current_regime in trend_aliases:
        return True
    return False


def _compat_range_position(candidate: str, current: str) -> bool:
    if candidate == current:
        return True
    adjacency = {
        "EDGE_TOP": {"UPPER"},
        "UPPER": {"EDGE_TOP", "MID"},
        "MID": {"UPPER", "LOWER"},
        "LOWER": {"MID", "EDGE_BOT"},
        "EDGE_BOT": {"LOWER"},
    }
    return current in adjacency.get(candidate, set())


def similarity_score(current_closes: Sequence[float], record: PatternRecord, current_features: Dict[str, float]) -> float:
    shape_distance = _euclid(current_closes, record.normalized_closes)
    shape_sim = max(0.0, 1.0 - shape_distance / max(len(current_closes), 1))

    vol_sim = 1.0 - abs(float(current_features.get("atr_pct", 0.0)) - float(record.similarity_features.get("atr_pct", 0.0))) / max(
        abs(float(current_features.get("atr_pct", 0.0))),
        abs(float(record.similarity_features.get("atr_pct", 0.0))),
        1e-9,
    )
    vol_sim = max(0.0, min(1.0, vol_sim))

    range_sim = 1.0 - abs(float(current_features.get("range_pos", 0.5)) - float(record.similarity_features.get("range_pos", 0.5)))
    range_sim = max(0.0, min(1.0, range_sim))

    return round(shape_sim * 0.5 + vol_sim * 0.25 + range_sim * 0.25, 4)


def find_regime_aware_matches(
    current_closes: Sequence[float],
    current_regime: str,
    current_range_position: str,
    current_features: Dict[str, float],
    history: Iterable[PatternRecord],
    tf: str,
    top_k: int = 3,
) -> RegimeAwarePatternResult:
    candidates: List[MatchCandidate] = []

    for record in history:
        if record.tf != tf:
            continue
        if not _compat_regime(record.market_regime, current_regime):
            continue
        if not _compat_range_position(record.range_position, current_range_position):
            continue
        score = similarity_score(current_closes=current_closes, record=record, current_features=current_features)
        if score < MIN_SIMILARITY_SCORE:
            continue
        candidates.append(
            MatchCandidate(
                ts=record.ts,
                similarity=score,
                future_move_pct=record.future_move_pct,
                direction=record.direction,
                horizon_bars=record.horizon_bars,
            )
        )

    candidates.sort(key=lambda x: x.similarity, reverse=True)
    top_matches = candidates[:top_k]

    if not top_matches:
        return RegimeAwarePatternResult(
            direction="NEUTRAL",
            avg_move_pct=0.0,
            win_rate=0.0,
            sample_count=0,
            strength=0,
            market_regime=current_regime,
            range_position=current_range_position,
            top_matches=[],
            note="no compatible pattern matches",
        )

    avg_move_pct = round(mean(x.future_move_pct for x in top_matches), 4)
    win_count = sum(1 for x in top_matches if x.direction == ("LONG" if avg_move_pct > 0 else "SHORT" if avg_move_pct < 0 else "NEUTRAL"))
    win_rate = round(win_count / len(top_matches), 4)
    direction: Direction = "LONG" if avg_move_pct > 0 else "SHORT" if avg_move_pct < 0 else "NEUTRAL"

    strength = int(min(100, round(mean(x.similarity for x in top_matches) * 100)))
    result = RegimeAwarePatternResult(
        direction=direction,
        avg_move_pct=avg_move_pct,
        win_rate=win_rate,
        sample_count=len(top_matches),
        strength=strength,
        market_regime=current_regime,
        range_position=current_range_position,
        top_matches=top_matches,
    )

    if abs(result.avg_move_pct) < MIN_MOVE_THRESHOLD:
        result.note = "avg move below threshold"
    elif result.sample_count < MIN_SAMPLE_COUNT:
        result.note = "not enough samples"
    elif result.win_rate < WIN_RATE_THRESHOLD:
        result.note = "pattern edge too weak"
    else:
        result.note = "pattern edge valid"

    return result
