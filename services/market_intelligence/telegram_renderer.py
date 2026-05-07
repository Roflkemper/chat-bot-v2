"""Telegram message renderer for market intelligence alerts.

Alert types:
  1. Session open brief  — at start of each killzone session
  2. Pattern confluence  — when confluence score crosses alert threshold
  3. Key event alert     — funding extreme / OI spike / pin bar at structure
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from .ict_killzones import KillzoneState, Session
from .mtf_confluence import ConfluenceBias, ConfluenceScore
from .order_blocks import OrderBlock
from .premium_discount import FVG, PremiumDiscountLevel, PriceZone
from .event_detectors import FundingSignal, FundingBias, OIDeltaSignal, OIBias, TakerSignal, TakerBias

_BIAS_ICONS = {
    ConfluenceBias.STRONG_BULL: "🟢🟢",
    ConfluenceBias.BULL:        "🟢",
    ConfluenceBias.NEUTRAL:     "⚪",
    ConfluenceBias.BEAR:        "🔴",
    ConfluenceBias.STRONG_BEAR: "🔴🔴",
}

_SESSION_LABELS = {
    Session.ASIA:     "АЗИЯ",
    Session.LONDON:   "ЛОНДОН",
    Session.NY_AM:    "НЬЮ-ЙОРК AM",
    Session.NY_LUNCH: "НЬЮ-ЙОРК ОБЕД",
    Session.NY_PM:    "НЬЮ-ЙОРК PM",
    Session.NONE:     "ВНЕ СЕССИИ",
}

_ZONE_LABELS = {
    PriceZone.PREMIUM:     "ПРЕМИУМ (перекуп)",
    PriceZone.DISCOUNT:    "ДИСКОНТ (перепрод)",
    PriceZone.EQUILIBRIUM: "РАВНОВЕСИЕ",
    PriceZone.UNKNOWN:     "—",
}


def format_session_brief(
    kz: KillzoneState,
    pd_level: Optional[PremiumDiscountLevel],
    current_price: float,
) -> str:
    """Format session open brief message."""
    ts = datetime.now(timezone.utc).strftime("%H:%M UTC")
    sess_label = _SESSION_LABELS.get(kz.active_session, kz.active_session.value)

    lines = [
        f"🕐 ОТКРЫТИЕ СЕССИИ | {ts}",
        f"Сессия: {sess_label}",
        f"BTC: ${current_price:,.1f}",
        f"Диапазон сессии: ${kz.session_low:,.1f} — ${kz.session_high:,.1f}",
        f"Середина: ${kz.session_midpoint:,.1f}",
    ]

    if pd_level:
        zone_label = _ZONE_LABELS.get(pd_level.current_zone, "")
        lines.append(f"Зона цены: {zone_label} ({pd_level.zone_pct:.0f}% диапазона)")

    if kz.sweep_high_confirmed:
        lines.append("⚠️ Подтверждён снос хая сессии")
    if kz.sweep_low_confirmed:
        lines.append("⚠️ Подтверждён снос лоя сессии")

    return "\n".join(lines)


def format_confluence_alert(
    confluence: ConfluenceScore,
    current_price: float,
    pd_level: Optional[PremiumDiscountLevel] = None,
    obs: Optional[list[OrderBlock]] = None,
    fvgs: Optional[list[FVG]] = None,
) -> str:
    """Format MTF confluence alert when score crosses threshold."""
    if not confluence.alert_worthy:
        return ""

    ts = datetime.now(timezone.utc).strftime("%H:%M UTC")
    icon = _BIAS_ICONS.get(confluence.bias, "⚪")
    bias_ru = {
        ConfluenceBias.STRONG_BULL: "СИЛЬНЫЙ БЫЧИЙ",
        ConfluenceBias.BULL: "Бычий",
        ConfluenceBias.NEUTRAL: "Нейтральный",
        ConfluenceBias.BEAR: "Медвежий",
        ConfluenceBias.STRONG_BEAR: "СИЛЬНЫЙ МЕДВЕЖИЙ",
    }.get(confluence.bias, confluence.bias.value)

    lines = [
        f"{icon} MTF КОНФЛЮЭНС | {ts}",
        f"",
        f"Направление: {bias_ru}",
        f"Оценка: {confluence.score:+.0f}/100",
        f"BTC: ${current_price:,.1f}",
        f"",
        f"Сигналы:",
    ]

    for sig in confluence.contributing_signals[:6]:
        lines.append(f"  • {sig}")

    if pd_level:
        zone_label = _ZONE_LABELS.get(pd_level.current_zone, "")
        lines.append(f"  • Зона: {zone_label} ({pd_level.zone_pct:.0f}%)")

    if obs:
        active_obs = [o for o in obs if not o.mitigated]
        if active_obs:
            lines.append(f"  • OB активных: {len(active_obs)}")

    if fvgs:
        active_fvgs = [g for g in fvgs if not g.filled]
        if active_fvgs:
            lines.append(f"  • FVG незакрытых: {len(active_fvgs)}")

    if confluence.timeframes_agree:
        lines.append(f"")
        lines.append(f"✅ Все таймфреймы подтверждают направление")

    return "\n".join(lines)


def format_key_event_alert(
    event_type: str,
    event_note: str,
    current_price: float,
) -> str:
    """Format a single key market event alert."""
    ts = datetime.now(timezone.utc).strftime("%H:%M UTC")
    icons = {
        "funding": "💰",
        "oi": "📊",
        "taker": "⚡",
        "pin_bar": "📍",
        "rsi_div": "〰️",
    }
    icon = icons.get(event_type.split("_")[0], "🔔")

    return (
        f"{icon} СОБЫТИЕ РЫНКА | {ts}\n"
        f"Тип: {event_type}\n"
        f"BTC: ${current_price:,.1f}\n"
        f"Детали: {event_note}"
    )
