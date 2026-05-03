"""Russian-language morning brief generator.

Combines RegimeForecastSwitcher output, ICT levels, and virtual trader stats
into the format defined in TZ-FINAL. All section text in Russian; technical
jargon (MARKDOWN, RANGE, funding rate, R:R, ATR) preserved.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from .regime_switcher import ForecastResult


# ── Translation tables ────────────────────────────────────────────────────────

_REGIME_RU = {
    "MARKUP":       "MARKUP",        # technical jargon preserved
    "MARKDOWN":     "MARKDOWN",
    "RANGE":        "RANGE",
    "DISTRIBUTION": "DISTRIBUTION",
}

_QUAL_LABEL_RU = {
    "lean_up":           "бычий уклон",
    "lean_down":         "медвежий уклон",
    "lean_neutral":      "нейтральный уклон",
    "lean_top_unstable": "вершина диапазона, нестабильно",
    "uncertain":         "неопределённость",
}

_WATCH_RU = {
    "funding_flip":  "Funding flip (смена знака funding rate)",
    "volume_spike":  "Объёмный всплеск (>2× среднего) на пробое",
    "regime_change": "Смена режима 1д ({from_r} → {to_r})",
    "atr_compression": "Сжатие ATR — потенциал импульса",
    "session_break":   "Пробой ключевого уровня сессии",
}


# ── Data structures ──────────────────────────────────────────────────────────

@dataclass
class Level:
    """A key price level for the brief."""
    price: float
    label: str          # e.g. "зона предложения (хай NY-сессии)"
    kind: str           # "supply" | "demand"
    scenarios: list[dict] = field(default_factory=list)  # [{name, target, action_long, action_short, action_flat}]


@dataclass
class DayPotential:
    base_pct: int
    base_range: tuple[float, float]
    bear_pct: int
    bear_path: str
    bull_pct: int
    bull_path: str


@dataclass
class VirtualTraderSnapshot:
    today_setup: Optional[dict] = None       # {direction, entry, sl, tp1, tp2, ttl, rr1, rr2}
    open_positions: list[dict] = field(default_factory=list)
    stats_7d: Optional[dict] = None          # {signals, wins, losses, open, win_rate_pct, avg_rr}


# ── Section formatters ───────────────────────────────────────────────────────

def _format_header(ts: datetime, price: float, pct_24h: float) -> str:
    arrow = "+" if pct_24h >= 0 else ""
    return (
        "═══════════════════════════════\n"
        f"УТРЕННИЙ БРИФ • {ts.strftime('%d %b %H:%M UTC')}\n"
        f"BTC: {price:.0f} ({arrow}{pct_24h:.1f}% за 24ч)\n"
        "═══════════════════════════════"
    )


def _format_regime(regime: str, confidence: float, stable_bars: int, switch_pending: bool) -> str:
    return (
        f"\n📍 РЕЖИМ: {_REGIME_RU.get(regime, regime)}\n"
        f"   Уверенность: {confidence:.2f} | Стабильно: {stable_bars} баров\n"
        f"   Авто-переключение: {'YES' if switch_pending else 'NO'} "
        f"({'есть кандидат на смену' if switch_pending else 'нет признаков смены'})"
    )


def _format_forecast(forecasts: dict[str, ForecastResult]) -> str:
    lines = ["\n📊 ПРОГНОЗ:"]
    for hz in ("1h", "4h", "1d"):
        fr = forecasts[hz]
        if fr.mode == "numeric":
            prob_up = fr.value
            prob_down = 1.0 - prob_up
            if prob_up >= 0.55:
                arrow, pct, dir_label = "▲", prob_up, "вверх"
            elif prob_down >= 0.55:
                arrow, pct, dir_label = "▼", prob_down, "вниз"
            else:
                arrow, pct, dir_label = "•", max(prob_up, prob_down), "нейтрально"
            tag = "[числовой, надёжный]" if fr.confidence > 0.10 else "[числовой]"
            lines.append(f"   {hz:3s}  {arrow} {pct*100:.0f}% {dir_label}   {tag}")
        else:
            label = _QUAL_LABEL_RU.get(str(fr.value), str(fr.value))
            caveat_short = "большой разброс" if (fr.caveat and "transition" in fr.caveat) else "режимный"
            lines.append(f"   {hz:3s}  ◆ {label}  [качественный — {caveat_short}]")
    return "\n".join(lines)


def _format_levels(levels: list[Level], current_price: float) -> str:
    out = ["\n═══════════════════════════════", "🎯 КЛЮЧЕВЫЕ УРОВНИ", "═══════════════════════════════"]
    for lv in levels:
        dist_pct = (lv.price - current_price) / current_price * 100
        if abs(dist_pct) > 5.0:  # too far — skip per spec
            continue
        emoji = "🟥" if lv.kind == "supply" else "🟩"
        sign = "+" if dist_pct >= 0 else ""
        out.append(f"\n{emoji} {lv.price:.0f} — {lv.label}")
        out.append(f"   До цели: {sign}{dist_pct:.1f}% от текущей")
        for sc in lv.scenarios:
            out.append(f"\n   ▸ СЦЕНАРИЙ {sc['name']}: {sc['trigger']}")
            if sc.get("target"):
                out.append(f"     Потенциал: {sc['target']}")
            if sc.get("rr"):
                out.append(f"     R:R: {sc['rr']}")
            if any(sc.get(k) for k in ("action_long", "action_short", "action_flat")):
                out.append("\n     Что делать (для ручной торговли):")
                if sc.get("action_long"):
                    out.append(f"     • в лонге: {sc['action_long']}")
                if sc.get("action_short"):
                    out.append(f"     • в шорте: {sc['action_short']}")
                if sc.get("action_flat"):
                    out.append(f"     • вне позиции: {sc['action_flat']}")
    return "\n".join(out)


def _format_day_potential(dp: DayPotential) -> str:
    return (
        "\n═══════════════════════════════\n"
        "🎲 ПОТЕНЦИАЛ ДНЯ\n"
        "═══════════════════════════════\n"
        f"   Базовый ({dp.base_pct}%):   диапазон {dp.base_range[0]:.0f}–{dp.base_range[1]:.0f}\n"
        f"   Медвежий ({dp.bear_pct}%):  {dp.bear_path}\n"
        f"   Бычий ({dp.bull_pct}%):     {dp.bull_path}"
    )


def _format_virtual_trader(vt: VirtualTraderSnapshot) -> str:
    out = ["\n═══════════════════════════════", "🤖 ВИРТУАЛЬНАЯ ТОРГОВЛЯ БОТА", "═══════════════════════════════"]
    if vt.today_setup:
        s = vt.today_setup
        dir_ru = "Шорт" if s["direction"] == "short" else "Лонг"
        out.append(f"Сегодняшний сетап:")
        out.append(f"   {dir_ru} от {s['entry']:.0f} ({s.get('reason', '')})".rstrip())
        out.append(f"   Стоп: {s['sl']:.0f}")
        out.append(f"   Цель 1: {s['tp1']:.0f} (50%) — R:R {s.get('rr1', 0):.1f}")
        out.append(f"   Цель 2: {s['tp2']:.0f} (50%) — R:R {s.get('rr2', 0):.1f}")
        out.append(f"   Срок жизни: {s.get('ttl', '4 часа')}")
    else:
        out.append("Сегодняшний сетап: нет (forecast ниже порога 0.55 или качественный)")

    if vt.open_positions:
        out.append("\nОткрытые виртуальные позиции:")
        for i, p in enumerate(vt.open_positions, 1):
            dir_ru = "Шорт" if p["direction"] == "short" else "Лонг"
            pnl_sign = "+" if p["pnl_pct"] >= 0 else ""
            out.append(f"   {i}. {dir_ru} {p['entry']:.0f} от {p['entry_time_str']} → текущий PnL {pnl_sign}{p['pnl_pct']:.1f}%")
    else:
        out.append("\nОткрытые виртуальные позиции: нет")

    if vt.stats_7d:
        s = vt.stats_7d
        out.append(f"\nСтатистика за 7 дней:")
        out.append(f"   Сигналов: {s['signals']} | Win: {s['wins']} | Loss: {s['losses']} | Open: {s['open']}")
        if s["signals"] > 0:
            wr = s["wins"] / max(s["wins"] + s["losses"], 1) * 100
            out.append(f"   Win-rate: {wr:.0f}% | Avg R:R: {s.get('avg_rr', 0):.1f}")
        out.append("   (Это тренд для отладки модели, не торговый совет.)")
    return "\n".join(out)


def _format_watch(watches: list[dict]) -> str:
    out = ["\n═══════════════════════════════", "👀 СЛЕДИМ ЗА:", "═══════════════════════════════"]
    for w in watches:
        key = w["key"]
        tpl = _WATCH_RU.get(key, key)
        out.append(f"- {tpl.format(**w.get('args', {}))}")
    return "\n".join(out)


def _format_footer() -> str:
    return (
        "\n═══════════════════════════════\n"
        "⚠️ Этот бриф — модельный анализ, не торговый совет.\n"
        "   Виртуальная торговля бота независима от вашей.\n"
        "═══════════════════════════════"
    )


# ── Public entry point ───────────────────────────────────────────────────────

def generate_brief(
    timestamp: datetime,
    price: float,
    pct_24h: float,
    regime: str,
    regime_confidence: float,
    stable_bars: int,
    switch_pending: bool,
    forecasts: dict[str, ForecastResult],
    levels: list[Level],
    day_potential: DayPotential,
    virtual_trader: VirtualTraderSnapshot,
    watches: list[dict],
) -> str:
    """Render a complete morning brief (Russian markdown)."""
    sections = [
        _format_header(timestamp, price, pct_24h),
        _format_regime(regime, regime_confidence, stable_bars, switch_pending),
        _format_forecast(forecasts),
        _format_levels(levels, price),
        _format_day_potential(day_potential),
        _format_virtual_trader(virtual_trader),
        _format_watch(watches),
        _format_footer(),
    ]
    return "\n".join(sections)
