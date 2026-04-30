from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import pandas as pd

from .indicators import (
    compute_rsi,
    compute_volume_ratio,
    find_pdh_pdl,
    reversal_wick_count,
    count_touches_at_level,
)
from .models import Setup, SetupBasis, SetupType, make_setup
from .scorer import compute_confidence, compute_strength


@dataclass
class PortfolioSnapshot:
    free_margin_pct: float = 100.0
    net_btc: float = 0.0
    available_usd: float = 1000.0
    liq_above_price: float | None = None
    liq_below_price: float | None = None


@dataclass
class DetectionContext:
    pair: str
    current_price: float
    regime_label: str
    session_label: str
    ohlcv_1m: pd.DataFrame   # columns: open, high, low, close, volume
    ohlcv_1h: pd.DataFrame
    portfolio: PortfolioSnapshot = field(default_factory=PortfolioSnapshot)


DetectorFn = Callable[[DetectionContext], Setup | None]


# ── LONG_DUMP_REVERSAL ────────────────────────────────────────────────────────

def detect_long_dump_reversal(ctx: DetectionContext) -> Setup | None:
    """P-7 base: dump ≥2% in 4h + RSI oversold + reversal wicks + volume + PDL."""
    df1h = ctx.ohlcv_1h
    df1m = ctx.ohlcv_1m
    if len(df1h) < 6 or len(df1m) < 30:
        return None

    price_4h_ago = float(df1h["close"].iloc[-5])
    price_change_4h = (ctx.current_price - price_4h_ago) / max(price_4h_ago, 1.0) * 100.0
    cond_dump = price_change_4h <= -2.0

    rsi_1h = compute_rsi(df1h["close"], period=14)
    cond_rsi = rsi_1h < 35.0

    wick_cnt = reversal_wick_count(
        df1m["open"].iloc[-10:],
        df1m["high"].iloc[-10:],
        df1m["low"].iloc[-10:],
        df1m["close"].iloc[-10:],
        direction="long",
    )
    cond_wicks = wick_cnt >= 3

    vol_ratio = compute_volume_ratio(df1m["volume"], lookback=30)
    cond_volume = vol_ratio >= 1.3

    lookback_h = min(24, len(df1h))
    _, pdl = find_pdh_pdl(df1h.iloc[-lookback_h:])
    near_pdl = pdl > 0.0 and abs(ctx.current_price - pdl) / pdl * 100.0 <= 0.6
    pdl_tests = count_touches_at_level(df1m["low"], pdl, tolerance_pct=0.15) if pdl > 0.0 else 0
    cond_pdl = near_pdl

    conditions_met = sum([cond_dump, cond_rsi, cond_wicks, cond_volume, cond_pdl])
    if conditions_met < 3:
        return None

    basis_items: list[SetupBasis] = []
    if cond_dump:
        basis_items.append(SetupBasis(f"Дамп {price_change_4h:.1f}% за 4ч", price_change_4h, 1.0))
    if cond_rsi:
        basis_items.append(SetupBasis(f"RSI 1h = {rsi_1h:.0f} (перепродан)", rsi_1h, 1.0))
    if cond_wicks:
        basis_items.append(SetupBasis(f"Разворотные свечи ({wick_cnt}/10 pin bars)", wick_cnt, 0.8))
    if cond_volume:
        basis_items.append(SetupBasis(f"Объём x{vol_ratio:.1f} от среднего", vol_ratio, 0.9))
    if cond_pdl and pdl > 0.0:
        pdl_label = f"PDL ${pdl:,.0f}" + (f" ({pdl_tests}× тест)" if pdl_tests > 0 else "")
        basis_items.append(SetupBasis(pdl_label, pdl, min(1.0, 0.7 + pdl_tests * 0.1)))

    basis = tuple(basis_items)
    strength = compute_strength(basis)
    if strength < 6:
        return None

    confidence = compute_confidence(SetupType.LONG_DUMP_REVERSAL, basis, ctx.regime_label, ctx.session_label)

    recent_low = float(df1m["low"].iloc[-20:].min())
    entry = ctx.current_price * 0.997
    stop = min(recent_low * 0.995, entry * 0.993)
    risk = max(entry - stop, entry * 0.001)
    tp1 = entry + risk
    tp2 = entry + 2.0 * risk
    rr = risk / max(entry - stop, 1e-9)

    return make_setup(
        setup_type=SetupType.LONG_DUMP_REVERSAL,
        pair=ctx.pair,
        current_price=ctx.current_price,
        regime_label=ctx.regime_label,
        session_label=ctx.session_label,
        entry_price=round(entry, 1),
        stop_price=round(stop, 1),
        tp1_price=round(tp1, 1),
        tp2_price=round(tp2, 1),
        risk_reward=round(rr, 2),
        strength=strength,
        confidence_pct=round(confidence, 1),
        basis=basis,
        cancel_conditions=(
            "Цена закрывается выше entry на 1ч свече без разворота",
            f"RSI 1h > 50 (перепроданность снята)",
            "Новый локальный минимум ниже стоп-уровня",
        ),
        window_minutes=120,
        portfolio_impact_note="P-7: добавляет к лонгам, осторожно при trend_down",
        recommended_size_btc=0.05,
    )


# ── SHORT_RALLY_FADE ──────────────────────────────────────────────────────────

def detect_short_rally_fade(ctx: DetectionContext) -> Setup | None:
    """P-1 base: rally ≥2% in 4h + RSI overbought + rejection wicks + volume + PDH."""
    df1h = ctx.ohlcv_1h
    df1m = ctx.ohlcv_1m
    if len(df1h) < 6 or len(df1m) < 30:
        return None

    price_4h_ago = float(df1h["close"].iloc[-5])
    price_change_4h = (ctx.current_price - price_4h_ago) / max(price_4h_ago, 1.0) * 100.0
    cond_rally = price_change_4h >= 2.0

    rsi_1h = compute_rsi(df1h["close"], period=14)
    cond_rsi = rsi_1h > 65.0

    wick_cnt = reversal_wick_count(
        df1m["open"].iloc[-10:],
        df1m["high"].iloc[-10:],
        df1m["low"].iloc[-10:],
        df1m["close"].iloc[-10:],
        direction="short",
    )
    cond_wicks = wick_cnt >= 3

    vol_ratio = compute_volume_ratio(df1m["volume"], lookback=30)
    cond_volume = vol_ratio >= 1.3

    lookback_h = min(24, len(df1h))
    pdh, _ = find_pdh_pdl(df1h.iloc[-lookback_h:])
    near_pdh = pdh > 0.0 and abs(ctx.current_price - pdh) / pdh * 100.0 <= 0.6
    pdh_tests = count_touches_at_level(df1m["high"], pdh, tolerance_pct=0.15) if pdh > 0.0 else 0
    cond_pdh = near_pdh

    conditions_met = sum([cond_rally, cond_rsi, cond_wicks, cond_volume, cond_pdh])
    if conditions_met < 3:
        return None

    basis_items: list[SetupBasis] = []
    if cond_rally:
        basis_items.append(SetupBasis(f"Ралли +{price_change_4h:.1f}% за 4ч", price_change_4h, 1.0))
    if cond_rsi:
        basis_items.append(SetupBasis(f"RSI 1h = {rsi_1h:.0f} (перекуплен)", rsi_1h, 1.0))
    if cond_wicks:
        basis_items.append(SetupBasis(f"Отбойные свечи ({wick_cnt}/10 pin bars)", wick_cnt, 0.8))
    if cond_volume:
        basis_items.append(SetupBasis(f"Объём x{vol_ratio:.1f} от среднего", vol_ratio, 0.9))
    if cond_pdh and pdh > 0.0:
        pdh_label = f"PDH ${pdh:,.0f}" + (f" ({pdh_tests}× тест)" if pdh_tests > 0 else "")
        basis_items.append(SetupBasis(pdh_label, pdh, min(1.0, 0.7 + pdh_tests * 0.1)))

    basis = tuple(basis_items)
    strength = compute_strength(basis)
    if strength < 6:
        return None

    confidence = compute_confidence(SetupType.SHORT_RALLY_FADE, basis, ctx.regime_label, ctx.session_label)

    recent_high = float(df1m["high"].iloc[-20:].max())
    entry = ctx.current_price * 1.003
    stop = max(recent_high * 1.005, entry * 1.007)
    risk = max(stop - entry, entry * 0.001)
    tp1 = entry - risk
    tp2 = entry - 2.0 * risk
    rr = risk / max(stop - entry, 1e-9)

    return make_setup(
        setup_type=SetupType.SHORT_RALLY_FADE,
        pair=ctx.pair,
        current_price=ctx.current_price,
        regime_label=ctx.regime_label,
        session_label=ctx.session_label,
        entry_price=round(entry, 1),
        stop_price=round(stop, 1),
        tp1_price=round(tp1, 1),
        tp2_price=round(tp2, 1),
        risk_reward=round(rr, 2),
        strength=strength,
        confidence_pct=round(confidence, 1),
        basis=basis,
        cancel_conditions=(
            "Цена закрывается ниже entry на 1ч свече без отката",
            f"RSI 1h < 50 (перекупленность снята)",
            "Новый локальный максимум выше стоп-уровня",
        ),
        window_minutes=120,
        portfolio_impact_note="P-1: добавляет к шортам, осторожно при trend_up",
        recommended_size_btc=0.05,
    )


# ── DEFENSIVE_MARGIN_LOW ──────────────────────────────────────────────────────

def detect_defensive_margin_low(ctx: DetectionContext) -> Setup | None:
    """Alert when free margin < 25%."""
    if ctx.portfolio.free_margin_pct >= 25.0:
        return None

    margin = ctx.portfolio.free_margin_pct
    basis = (
        SetupBasis(f"Свободная маржа {margin:.1f}%", margin, 1.0),
        SetupBasis("Риск принудительной ликвидации", "", 1.0),
    )
    strength = 9
    confidence = 95.0

    return make_setup(
        setup_type=SetupType.DEFENSIVE_MARGIN_LOW,
        pair=ctx.pair,
        current_price=ctx.current_price,
        regime_label=ctx.regime_label,
        session_label=ctx.session_label,
        strength=strength,
        confidence_pct=confidence,
        basis=basis,
        cancel_conditions=(
            "Маржа восстановилась выше 30%",
            "Позиция сокращена",
        ),
        window_minutes=60,
        portfolio_impact_note="Защитный алерт: маржа критически низкая",
        recommended_size_btc=0.0,
    )


# ── GRID_BOOSTER_ACTIVATE ─────────────────────────────────────────────────────

def detect_grid_booster_activate(ctx: DetectionContext) -> Setup | None:
    """P-16: activate booster bot when RSI oversold in range/consolidation."""
    if ctx.regime_label not in ("range_tight", "range_wide", "consolidation"):
        return None

    df1h = ctx.ohlcv_1h
    if len(df1h) < 16:
        return None

    rsi_1h = compute_rsi(df1h["close"], period=14)
    if rsi_1h >= 35.0:
        return None

    liq_boost = ctx.portfolio.liq_below_price is not None
    near_liq = (
        liq_boost
        and ctx.portfolio.liq_below_price is not None
        and ctx.portfolio.liq_below_price > 0.0
        and abs(ctx.current_price - ctx.portfolio.liq_below_price) / ctx.current_price * 100.0 <= 1.5
    )

    basis_items: list[SetupBasis] = [
        SetupBasis(f"RSI 1h = {rsi_1h:.0f} (перепродан в рэнже)", rsi_1h, 1.0),
        SetupBasis(f"Режим: {ctx.regime_label}", ctx.regime_label, 0.8),
    ]
    if near_liq and ctx.portfolio.liq_below_price is not None:
        basis_items.append(
            SetupBasis(f"Ликвидность ниже ${ctx.portfolio.liq_below_price:,.0f}", ctx.portfolio.liq_below_price, 0.9)
        )

    basis = tuple(basis_items)
    strength = compute_strength(basis)
    if strength < 6:
        return None

    confidence = compute_confidence(SetupType.GRID_BOOSTER_ACTIVATE, basis, ctx.regime_label, ctx.session_label)

    return make_setup(
        setup_type=SetupType.GRID_BOOSTER_ACTIVATE,
        pair=ctx.pair,
        current_price=ctx.current_price,
        regime_label=ctx.regime_label,
        session_label=ctx.session_label,
        grid_action="activate_booster",
        grid_target_bots=("Bot 6399265299",),
        strength=strength,
        confidence_pct=round(confidence, 1),
        basis=basis,
        cancel_conditions=(
            "Режим сменился на trend",
            "RSI 1h восстановился выше 50",
        ),
        window_minutes=90,
        portfolio_impact_note="P-16: активация буст-бота при перепроданности в рэнже",
        recommended_size_btc=0.0,
    )


# ── Registry ──────────────────────────────────────────────────────────────────

DETECTOR_REGISTRY: tuple[DetectorFn, ...] = (
    detect_long_dump_reversal,
    detect_short_rally_fade,
    detect_defensive_margin_low,
    detect_grid_booster_activate,
)
