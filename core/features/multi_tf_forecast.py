from __future__ import annotations

from dataclasses import dataclass, asdict
from statistics import mean
from typing import Dict, Iterable, List, Literal, Optional, Tuple

Direction = Literal["LONG", "SHORT", "NEUTRAL"]
Phase = Literal["ACCUMULATION", "DISTRIBUTION", "MARKUP", "MARKDOWN", "NEUTRAL"]
Candle = Dict[str, float]

MIN_MOVE_THRESHOLD = 0.2
MIN_SAMPLE_COUNT = 10
WIN_RATE_THRESHOLD = 0.55


@dataclass
class PatternMatch:
    date: str
    similarity: float
    avg_move_pct: float
    horizon_bars: int


@dataclass
class PatternResult:
    tf: str
    direction: Direction
    strength: int
    avg_move_pct: float
    sample_count: int
    win_rate: float
    market_regime: str
    range_position: str
    phase: Phase = "NEUTRAL"
    top_matches: Optional[List[PatternMatch]] = None
    note: str = ""

    def is_meaningful(self) -> bool:
        return (
            abs(self.avg_move_pct) >= MIN_MOVE_THRESHOLD
            and self.sample_count >= MIN_SAMPLE_COUNT
            and self.win_rate >= WIN_RATE_THRESHOLD
        )


@dataclass
class ShortTermFeatures:
    body_ratio: float
    direction_ratio: float
    tail_bias: float
    volume_trend: float
    pressure_proxy_pct: float
    vector: Direction
    strength_label: str


@dataclass
class SessionContext:
    compression_ratio: float
    compression_label: str
    prev_session_position: float
    bias: Direction
    upper_zone: Tuple[float, float]
    lower_zone: Tuple[float, float]


@dataclass
class MediumContext:
    phase: Phase
    bias: Direction
    note: str


@dataclass
class ForecastBundle:
    short_term: ShortTermFeatures
    session: SessionContext
    medium: MediumContext
    pattern_1h: PatternResult
    pattern_4h: PatternResult
    pattern_1d: PatternResult

    def to_dict(self) -> Dict[str, object]:
        return {
            "short_term": asdict(self.short_term),
            "session": asdict(self.session),
            "medium": asdict(self.medium),
            "pattern_1h": asdict(self.pattern_1h),
            "pattern_4h": asdict(self.pattern_4h),
            "pattern_1d": asdict(self.pattern_1d),
        }


def _safe_mean(values: Iterable[float], default: float = 0.0) -> float:
    vals = list(values)
    return mean(vals) if vals else default


def normalize_candles(candles: List[Candle]) -> List[Candle]:
    if not candles:
        return []
    base = float(candles[0]["open"])
    if base == 0:
        return []
    base_volume = max(float(candles[0].get("volume", 1.0)), 1.0)
    out: List[Candle] = []
    for c in candles:
        out.append(
            {
                "ts": c.get("ts"),
                "open": (float(c["open"]) - base) / base * 100.0,
                "high": (float(c["high"]) - base) / base * 100.0,
                "low": (float(c["low"]) - base) / base * 100.0,
                "close": (float(c["close"]) - base) / base * 100.0,
                "volume": float(c.get("volume", 0.0)) / base_volume,
            }
        )
    return out


def avg_true_range(candles: List[Candle], period: int = 14) -> float:
    if len(candles) < 2:
        return 0.0
    trs: List[float] = []
    prev_close = float(candles[0]["close"])
    for c in candles[1:]:
        high = float(c["high"])
        low = float(c["low"])
        close = float(c["close"])
        trs.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
        prev_close = close
    sample = trs[-period:] if len(trs) >= period else trs
    return _safe_mean(sample)


def range_position(candles: List[Candle]) -> float:
    if not candles:
        return 0.5
    low = min(float(c["low"]) for c in candles)
    high = max(float(c["high"]) for c in candles)
    price = float(candles[-1]["close"])
    width = max(high - low, 1e-9)
    return max(0.0, min(1.0, (price - low) / width))


def similarity_score(window_a: List[Candle], window_b: List[Candle]) -> float:
    if not window_a or not window_b or len(window_a) != len(window_b):
        return 0.0
    a = normalize_candles(window_a)
    b = normalize_candles(window_b)
    if not a or not b:
        return 0.0

    shape_error = _safe_mean(abs(a[i]["close"] - b[i]["close"]) for i in range(len(a)))
    shape_sim = max(0.0, 1.0 - shape_error / 5.0)

    atr_a = avg_true_range(a)
    atr_b = avg_true_range(b)
    vol_sim = 1.0 - abs(atr_a - atr_b) / max(abs(atr_a), abs(atr_b), 1e-9)
    vol_sim = max(0.0, min(1.0, vol_sim))

    pos_a = range_position(a)
    pos_b = range_position(b)
    ctx_sim = max(0.0, 1.0 - abs(pos_a - pos_b))

    score = shape_sim * 0.5 + vol_sim * 0.25 + ctx_sim * 0.25
    return round(max(0.0, min(1.0, score)), 4)


def classify_short_term(candles: List[Candle], lookback: int = 5) -> ShortTermFeatures:
    bars = candles[-lookback:]
    if not bars:
        return ShortTermFeatures(0, 0, 0, 1, 0, "NEUTRAL", "weak")

    body_ratios = []
    up_count = 0
    tail_biases = []
    vols = []
    buy_proxy = 0.0
    sell_proxy = 0.0

    for c in bars:
        o = float(c["open"])
        h = float(c["high"])
        l = float(c["low"])
        cl = float(c["close"])
        v = float(c.get("volume", 0.0))
        rng = max(h - l, 1e-9)
        body = abs(cl - o)
        body_ratio = body / rng
        body_ratios.append(body_ratio)
        vols.append(v)
        if cl > o:
            up_count += 1
        upper_tail = h - max(o, cl)
        lower_tail = min(o, cl) - l
        tail_biases.append(lower_tail - upper_tail)
        if cl >= o:
            buy_proxy += v * body_ratio
            sell_proxy += v * (1.0 - body_ratio)
        else:
            sell_proxy += v * body_ratio
            buy_proxy += v * (1.0 - body_ratio)

    pressure_total = max(buy_proxy + sell_proxy, 1e-9)
    pressure_proxy_pct = ((buy_proxy - sell_proxy) / pressure_total) * 100.0
    direction_ratio = up_count / len(bars)
    volume_trend = vols[-1] / max(_safe_mean(vols), 1e-9)

    if pressure_proxy_pct > 8 and direction_ratio >= 0.6:
        vector: Direction = "LONG"
        strength = "strong"
    elif pressure_proxy_pct < -8 and direction_ratio <= 0.4:
        vector = "SHORT"
        strength = "strong"
    elif pressure_proxy_pct > 0:
        vector = "LONG"
        strength = "medium"
    elif pressure_proxy_pct < 0:
        vector = "SHORT"
        strength = "medium"
    else:
        vector = "NEUTRAL"
        strength = "weak"

    return ShortTermFeatures(
        body_ratio=round(_safe_mean(body_ratios), 4),
        direction_ratio=round(direction_ratio, 4),
        tail_bias=round(_safe_mean(tail_biases), 4),
        volume_trend=round(volume_trend, 4),
        pressure_proxy_pct=round(pressure_proxy_pct, 2),
        vector=vector,
        strength_label=strength,
    )


def build_session_context(candles_1h: List[Candle], candles_4h: List[Candle]) -> SessionContext:
    if len(candles_1h) < 24 or len(candles_4h) < 6:
        return SessionContext(1.0, "normal", 0.5, "NEUTRAL", (0.0, 0.0), (0.0, 0.0))

    atr_current = avg_true_range(candles_1h[-14:], period=14)
    atr_baseline = avg_true_range(candles_4h[-30:], period=14)
    compression = atr_current / max(atr_baseline, 1e-9)
    if compression < 0.7:
        label = "compressed"
    elif compression > 1.3:
        label = "expanded"
    else:
        label = "normal"

    prev = candles_1h[-24:]
    prev_high = max(float(c["high"]) for c in prev)
    prev_low = min(float(c["low"]) for c in prev)
    price = float(candles_1h[-1]["close"])
    width = max(prev_high - prev_low, 1e-9)
    pos = (price - prev_low) / width

    if pos > 0.58:
        bias: Direction = "LONG"
    elif pos < 0.42:
        bias = "SHORT"
    else:
        bias = "NEUTRAL"

    zone_size = width * 0.22
    upper_zone = (round(prev_high - zone_size, 2), round(prev_high, 2))
    lower_zone = (round(prev_low, 2), round(prev_low + zone_size, 2))

    return SessionContext(
        compression_ratio=round(compression, 4),
        compression_label=label,
        prev_session_position=round(pos, 4),
        bias=bias,
        upper_zone=upper_zone,
        lower_zone=lower_zone,
    )


def detect_daily_phase(candles_1d: List[Candle]) -> MediumContext:
    if len(candles_1d) < 10:
        return MediumContext("NEUTRAL", "NEUTRAL", "not enough daily data")

    closes = [float(c["close"]) for c in candles_1d[-10:]]
    highs = [float(c["high"]) for c in candles_1d[-10:]]
    lows = [float(c["low"]) for c in candles_1d[-10:]]
    trend = closes[-1] - closes[0]
    width = max(max(highs) - min(lows), 1e-9)
    drift = trend / width

    if drift > 0.35:
        return MediumContext("MARKUP", "LONG", "daily trend expansion up")
    if drift < -0.35:
        return MediumContext("MARKDOWN", "SHORT", "daily trend expansion down")

    upper_rejects = sum(1 for c in candles_1d[-10:] if float(c["high"]) - max(float(c["open"]), float(c["close"])) > (float(c["high"]) - float(c["low"])) * 0.35)
    lower_rejects = sum(1 for c in candles_1d[-10:] if min(float(c["open"]), float(c["close"])) - float(c["low"]) > (float(c["high"]) - float(c["low"])) * 0.35)

    if upper_rejects >= 4:
        return MediumContext("DISTRIBUTION", "SHORT", "daily upper rejections cluster")
    if lower_rejects >= 4:
        return MediumContext("ACCUMULATION", "LONG", "daily lower rejections cluster")

    return MediumContext("NEUTRAL", "NEUTRAL", "mixed daily phase")
