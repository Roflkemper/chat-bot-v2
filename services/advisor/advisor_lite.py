"""Advisor lite — 1-screen TG card with plain-language conclusions.

Replaces the verbose `build_advisor_v2_text` (50+ lines of raw data)
with a 12-15 line summary where every number is interpreted into a
trader-actionable conclusion.

Design rule: "вывод важнее цифры".
Bad:  "Funding: +0.0021% (нейтрально)"
Good: "📌 Funding +0.0021% — лонги платят шортам, давление вниз слабое"

Source data is the same as advisor_v2:
  - state/regime_state.json — multi-TF regime
  - market_live/market_1m.csv — last BTC price
  - state/setups.jsonl — recent active setups
  - state/paper_trades.jsonl — currently open paper trades
  - features computed live by services.advisor.advisor_v2._read_features_last
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from services.advisor.advisor_v2 import (
    _classify_v2_live,
    _load_open_paper_trades,
    _load_recent_setups,
    _read_features_last,
    _read_last_price,
    _read_margin_block,
)


def _funding_verdict(funding_pct: float | None) -> str:
    """Interpret funding rate."""
    if funding_pct is None:
        return "Funding: н/д"
    f = funding_pct * 100  # convert decimal to %
    if f > 0.02:
        return f"📈 Funding +{f:.4f}% — лонги перегреты, шорт-сквиз риск"
    if f > 0.005:
        return f"📈 Funding +{f:.4f}% — лонги платят шортам, лёгкое давление вниз"
    if f < -0.02:
        return f"📉 Funding {f:.4f}% — шорты перегреты, риск squeeze вверх"
    if f < -0.005:
        return f"📉 Funding {f:.4f}% — шорты платят лонгам, давление вверх"
    return f"⚖️ Funding {f:+.4f}% — нейтрально"


def _ls_verdict(long_pct: float | None, label: str = "топ-трейдеры") -> str:
    """Interpret long/short ratio."""
    if long_pct is None:
        return f"{label}: н/д"
    if long_pct >= 60:
        return f"🟢 {label}: {long_pct:.0f}% long — сильная вера в рост"
    if long_pct >= 53:
        return f"🟢 {label}: {long_pct:.0f}% long — умеренная вера в рост"
    if long_pct <= 40:
        return f"🔴 {label}: {long_pct:.0f}% long — сильно шортят"
    if long_pct <= 47:
        return f"🔴 {label}: {long_pct:.0f}% long — умеренно шортят"
    return f"⚖️ {label}: {long_pct:.0f}% long — сбалансировано"


def _oi_verdict(oi_change_pct: float | None) -> str:
    """Interpret OI 1h change."""
    if oi_change_pct is None:
        return "OI: н/д"
    if abs(oi_change_pct) < 0.3:
        return f"⏸️ OI 1ч {oi_change_pct:+.2f}% — flat, ждём пробоя"
    if oi_change_pct > 1.0:
        return f"🔼 OI 1ч {oi_change_pct:+.2f}% — резкое наращивание позиций"
    if oi_change_pct < -1.0:
        return f"🔽 OI 1ч {oi_change_pct:+.2f}% — деleveraging, позиции закрываются"
    if oi_change_pct > 0:
        return f"📈 OI 1ч +{oi_change_pct:.2f}% — позиции растут"
    return f"📉 OI 1ч {oi_change_pct:.2f}% — позиции уменьшаются"


def _rsi_verdict(rsi: float | None) -> str:
    """Interpret RSI 1h."""
    if rsi is None:
        return "RSI: н/д"
    if rsi >= 70:
        return f"🔴 RSI 1ч {rsi:.0f} — перекуплено, риск отката"
    if rsi >= 60:
        return f"🟡 RSI 1ч {rsi:.0f} — высокий, но в норме"
    if rsi <= 30:
        return f"🟢 RSI 1ч {rsi:.0f} — перепродано, риск отскока"
    if rsi <= 40:
        return f"🟡 RSI 1ч {rsi:.0f} — низкий, но в норме"
    return f"⚖️ RSI 1ч {rsi:.0f} — нейтрально"


def _regime_verdict(regime: dict[str, Any]) -> tuple[str, str]:
    """Interpret multi-TF regime → (1-line verdict, action).

    regime schema is: {"4h": ["LABEL", {...}], "1h": [...], "15m": [...]}
    """
    if not regime:
        return ("Режим: н/д", "ждать данных")

    def _label(tf_key: str) -> str:
        v = regime.get(tf_key)
        if isinstance(v, (list, tuple)) and v:
            return str(v[0])
        if isinstance(v, dict):
            return str(v.get("label", "?"))
        return "?"

    tf4h = _label("4h")
    tf1h = _label("1h")
    tf15m = _label("15m")

    summary = f"4ч={tf4h} 1ч={tf1h} 15м={tf15m}"

    if "RANGE" in tf4h or "RANGE" in tf1h:
        if "UP" in tf4h:
            return (f"📊 {summary}", "📈 макро вверх, micro range — лонг у нижнего края")
        if "DOWN" in tf4h:
            return (f"📊 {summary}", "📉 макро вниз, micro range — шорт у верхнего края")
        return (f"📊 {summary}", "⏸️ range везде — ждать пробой")
    if "UP" in tf4h and "UP" in tf1h:
        return (f"🚀 {summary}", "📈 тренд вверх — лонги с откатов")
    if "DOWN" in tf4h and "DOWN" in tf1h:
        return (f"📉 {summary}", "🔴 тренд вниз — шорты с подскоков")
    return (f"⚠️ {summary}", "разнонаправленность TF — осторожно")


def _setup_summary(setups: list[dict]) -> str:
    """Top 3 active setups in one line each — without TP/SL noise."""
    if not setups:
        return "🎯 Активных сетапов нет"
    # Filter: only trade setups (not P-15 lifecycle)
    trade = [s for s in setups if not str(s.get("setup_type", "")).startswith("p15_")]
    if not trade:
        return "🎯 Активных trade сетапов нет (только P-15 lifecycle)"
    out = [f"🎯 Активные сетапы ({len(trade)}):"]
    DETECTOR_RU = {
        "long_pdl_bounce": "LONG отбой PDL",
        "long_dump_reversal": "LONG разворот после дампа",
        "long_double_bottom": "LONG двойное дно",
        "short_pdh_rejection": "SHORT от PDH",
        "short_rally_fade": "SHORT fade rally",
        "short_mfi_multi_ga": "SHORT MFI multi",
        "long_multi_divergence": "LONG мульти-див",
    }
    for s in trade[:3]:
        det = s.get("setup_type", "?")
        ru = DETECTOR_RU.get(det, det)
        pair = s.get("pair", "?")
        conf = s.get("confidence_pct", 0)
        out.append(f"  • {ru} ({pair}) — уверенность {conf:.0f}%")
    return "\n".join(out)


def build_advisor_lite_text() -> str:
    """Build compact 1-screen advisor card with conclusions."""
    now = datetime.now(timezone.utc)
    price_info = _read_last_price()
    regime = _classify_v2_live() or {}
    features = _read_features_last() or {}
    setups = _load_recent_setups(within_hours=6)
    margin = _read_margin_block() or {}

    lines = []
    # Header
    if price_info:
        price, age_min = price_info
        fresh = "" if age_min < 10 else f" ⚠️ устарело {age_min:.0f}мин"
        lines.append(f"🎯 ADVISOR — BTC ${price:,.0f}  ({now:%H:%M UTC}{fresh})")
    else:
        lines.append(f"🎯 ADVISOR — ⚠️ нет live price  ({now:%H:%M UTC})")
    lines.append("")

    # ── РЕЖИМ + ДЕЙСТВИЕ
    regime_summary, action = _regime_verdict(regime)
    lines.append(regime_summary)
    lines.append(f"➡️ {action}")
    lines.append("")

    # ── КЛЮЧЕВЫЕ ФАКТОРЫ (5 строк — каждая с выводом)
    funding = features.get("funding_rate") or features.get("funding_rate_8h")
    oi_change = features.get("oi_delta_1h") or features.get("oi_change_1h_pct")
    rsi_1h = features.get("rsi_14") or features.get("rsi_1h")
    top_long = features.get("top_trader_long_pct")
    global_long = features.get("global_long_account_pct")

    lines.append("📊 РЫНОК:")
    lines.append(f"  {_rsi_verdict(rsi_1h)}")
    lines.append(f"  {_oi_verdict(oi_change)}")
    lines.append(f"  {_funding_verdict(funding)}")
    if top_long is not None:
        lines.append(f"  {_ls_verdict(top_long, 'топ-трейдеры')}")
    if global_long is not None and (top_long is None
                                       or abs(top_long - global_long) > 5):
        # Show retail only when it diverges from top traders
        lines.append(f"  {_ls_verdict(global_long, 'все retail')}")
    lines.append("")

    # ── МОЯ МАРЖА
    coef = margin.get("coefficient")
    dist = margin.get("distance_to_liquidation_pct")
    if coef is not None and dist is not None:
        if dist < 5:
            margin_emoji = "🚨 МАРЖА: КРИТИЧНО"
        elif dist < 10:
            margin_emoji = "⚠️ МАРЖА: близко к liq"
        elif coef >= 0.95:
            margin_emoji = "🟡 МАРЖА: высокий coef но дистанция ОК"
        else:
            margin_emoji = "🟢 МАРЖА: ок"
        lines.append(f"{margin_emoji} ({dist:.0f}% до liq, coef {coef:.2f})")
        lines.append("")

    # ── СЕТАПЫ
    lines.append(_setup_summary(setups))
    lines.append("")

    # ── ИТОГ
    lines.append("📋 ИТОГ:")
    lines.append(f"  • {action}")
    # Risk warnings
    warnings = []
    if dist is not None and dist < 10:
        warnings.append(f"маржа близко к liq ({dist:.0f}%)")
    if funding is not None and abs(funding * 100) > 0.02:
        warnings.append("funding перегрет — squeeze risk")
    if oi_change is not None and abs(oi_change) < 0.3:
        warnings.append("OI flat — пробой даст направление")
    for w in warnings:
        lines.append(f"  ⚠️ {w}")

    return "\n".join(lines)
