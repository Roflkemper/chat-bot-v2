"""Ordered trigger cascade — evaluates features + portfolio → Recommendation."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

from .portfolio import PortfolioState
from .size_mode import MODE_TO_SIZE

LIQ_OVERRIDE_THRESHOLD_PCT: float = 15.0

_PLAY_META: dict[str, dict] = {
    "P-1":  {"name": "Поднять границу +0.3%",       "win": 0.13, "dd_pct": 0.0, "params": {"offset_pct": 0.3}},
    "P-2":  {"name": "Стак-шорт на остановке",       "win": 0.59, "dd_pct": 1.5, "params": {}},
    "P-4":  {"name": "Стоп шорт-ботов",              "win": 0.23, "dd_pct": 0.0, "params": {}},
    "P-6":  {"name": "Стак-шорт + поднять границу",  "win": 0.69, "dd_pct": 1.4, "params": {"offset_pct": 1.0}},
    "P-7":  {"name": "Стак-лонг после дампа",        "win": 0.67, "dd_pct": 2.1, "params": {}},
    "P-12": {"name": "Adaptive tighten",             "win": 0.09, "dd_pct": 0.0, "params": {"gs_factor": 0.85, "target_factor": 0.8}},
}

_EXPECTED_PNL: dict[str, dict[str, float]] = {
    "P-6":  {"conservative": 28.0,  "normal": 84.0,  "aggressive": 134.0},
    "P-2":  {"conservative": 10.0,  "normal": 26.0,  "aggressive": 38.0},
    "P-7":  {"conservative": 7.0,   "normal": 15.0,  "aggressive": 26.0},
    "P-4":  {"conservative": 0.0,   "normal": 0.0,   "aggressive": 0.0},
    "P-1":  {"conservative": 0.0,   "normal": 0.0,   "aggressive": 0.0},
    "P-12": {"conservative": 0.0,   "normal": 0.0,   "aggressive": 0.0},
}


@dataclass
class Recommendation:
    play_id: str
    play_name: str
    trigger: str
    size_mode: str
    size_btc: float
    expected_pnl: float
    win_rate: float
    dd_pct: float
    params: dict = field(default_factory=dict)
    reason: str = ""
    ts_utc: str = ""
    symbol: str = "BTCUSDT"

    def __post_init__(self) -> None:
        if not self.ts_utc:
            self.ts_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _make(
    play_id: str,
    trigger: str,
    size_mode: str,
    size_btc: float,
    reason: str,
    symbol: str = "BTCUSDT",
) -> Recommendation:
    meta = _PLAY_META[play_id]
    return Recommendation(
        play_id=play_id,
        play_name=meta["name"],
        trigger=trigger,
        size_mode=size_mode,
        size_btc=size_btc,
        expected_pnl=_EXPECTED_PNL.get(play_id, {}).get(size_mode, 0.0),
        win_rate=meta["win"],
        dd_pct=meta["dd_pct"],
        params=dict(meta["params"]),
        reason=reason,
        symbol=symbol,
    )


def _delta_1h(features: dict[str, Any]) -> float | None:
    for key in ("delta_1h_pct", "delta_1h"):
        v = features.get(key)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    return None


_STALE_MAX_SEC_DEFAULT: float = 300.0


def _check_stale(features: dict[str, Any]) -> bool:
    """Return True (and log warning) if features snapshot is older than ADVISOR_STALE_MAX_SEC."""
    ts_str = features.get("ts_utc")
    if not ts_str:
        return False  # no ts_utc = old snapshot format, allow for backward compat
    try:
        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        age_sec = (datetime.now(timezone.utc) - ts).total_seconds()
    except Exception:
        return False

    try:
        from config import ADVISOR_STALE_MAX_SEC
        max_sec = float(ADVISOR_STALE_MAX_SEC)
    except Exception:
        max_sec = _STALE_MAX_SEC_DEFAULT

    if age_sec > max_sec:
        logger.warning(
            "[ADVISOR] snapshot stale (%.0fs > %.0fs) — skipping cascade",
            age_sec, max_sec,
        )
        return True
    return False


def evaluate(
    features: dict[str, Any],
    portfolio: PortfolioState,
    size_mode: str,
    symbol: str = "BTCUSDT",
) -> Recommendation | None:
    """Evaluate cascade and return the first matching Recommendation, or None.

    TZ-036: tries live parquet (read_latest_features) first.
    Falls back to the features dict passed in (from build_full_snapshot or caller).
    If no parquet and no fallback features, returns None for non-BTC symbols.
    """
    # ── TZ-036: prefer live parquet over synchronous snapshot ─────────────────
    live_features: dict[str, Any] | None = None
    try:
        from .feature_writer import read_latest_features
        live_features = read_latest_features(symbol)
    except Exception:
        pass

    if live_features is not None:
        logger.debug("[ADVISOR] using live features symbol=%s", symbol)
        resolved = live_features
    elif features:
        logger.debug("[ADVISOR] fallback build_full_snapshot symbol=%s", symbol)
        resolved = features
    else:
        # No parquet, no fallback (ETH/XRP cold start — writer hasn't run yet)
        return None

    if _check_stale(resolved):
        return None

    size_btc = MODE_TO_SIZE.get(size_mode, 0.10)

    current_price = float(resolved.get("price") or 0)
    if current_price > 0:
        min_dist = portfolio.min_liq_distance_pct(current_price)
        if min_dist < LIQ_OVERRIDE_THRESHOLD_PCT:
            return _make(
                "P-4",
                trigger=f"Ликвидация близко ({min_dist:.1f}%<{LIQ_OVERRIDE_THRESHOLD_PCT}%)",
                size_mode=size_mode,
                size_btc=0.0,
                reason="LIQ override — только защитные действия",
                symbol=symbol,
            )

    delta = _delta_1h(resolved)
    momentum_exhausted = bool(resolved.get("momentum_exhausted"))
    consec_up = resolved.get("consec_1h_up")
    distance_to_upper = resolved.get("distance_to_upper_edge")

    # P-6: rally_critical (Δ1h > 3%)
    if delta is not None and delta >= 3.0:
        return _make(
            "P-6",
            trigger=f"Δ1h={delta:.2f}%≥3% (rally_critical)",
            size_mode=size_mode,
            size_btc=size_btc,
            reason="Ралли критическое — стак-шорт + поднять границу",
            symbol=symbol,
        )

    # P-2: rally_strong (Δ1h 2-3%) + momentum loss
    if delta is not None and 2.0 <= delta < 3.0 and momentum_exhausted:
        return _make(
            "P-2",
            trigger=f"Δ1h={delta:.2f}% + momentum_exhausted",
            size_mode=size_mode,
            size_btc=size_btc,
            reason="Рост 2-3% + потеря моментума — шорт на остановке",
            symbol=symbol,
        )

    # P-7: dump + reversal (momentum_exhausted used as reversal proxy)
    if delta is not None and delta <= -2.0 and momentum_exhausted:
        return _make(
            "P-7",
            trigger=f"Δ1h={delta:.2f}%≤-2% + reversal",
            size_mode=size_mode,
            size_btc=size_btc,
            reason="Дамп + разворот — стак-лонг",
            symbol=symbol,
        )

    # P-4: no-pullback 3h+ + shorts in DD
    shorts_in_dd = any(
        b.position == "SHORT" and b.current_profit < 0
        for b in portfolio.bots
    )
    if consec_up is not None and float(consec_up) >= 3 and shorts_in_dd:
        return _make(
            "P-4",
            trigger=f"consec_up={consec_up}≥3 + шорты в DD",
            size_mode=size_mode,
            size_btc=0.0,
            reason="Длинный безоткатный рост — стоп шорт-ботов, удержание",
            symbol=symbol,
        )

    # P-1: price above short boundary
    if distance_to_upper is not None:
        try:
            d = float(distance_to_upper)
            if d < 0:
                return _make(
                    "P-1",
                    trigger=f"distance_to_upper={d:.2f}%<0",
                    size_mode=size_mode,
                    size_btc=0.0,
                    reason="Цена выше верхней границы — поднять на +0.3%",
                    symbol=symbol,
                )
        except (TypeError, ValueError):
            pass

    # P-12: bot in deep DD (proxy: unrealized < -$200)
    heavy_dd = [
        b for b in portfolio.bots
        if b.current_profit < -200 and b.position not in ("", "NONE")
    ]
    if heavy_dd:
        worst = min(heavy_dd, key=lambda b: b.current_profit)
        label = worst.alias or worst.name or worst.bot_id
        return _make(
            "P-12",
            trigger=f"Бот {label}: PnL={worst.current_profit:.0f}$",
            size_mode=size_mode,
            size_btc=0.0,
            reason="Бот в глубокой просадке — adaptive tighten",
            symbol=symbol,
        )

    return None
