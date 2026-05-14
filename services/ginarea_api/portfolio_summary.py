"""Portfolio summary — текущее состояние live-ботов + прогнозы.

Объединяет:
- live-config tracker (что запущено и когда)
- ожидание по backtest (profit / vol / peak)
- линейная экстраполяция expected_so_far
- прогноз rebate на месяц
"""
from __future__ import annotations

from datetime import datetime, timezone

from services.ginarea_api.live_config_tracker import (
    active_configs,
    days_since,
    expected_so_far_usd,
)

REBATE_PER_VOL_MUSD = 250.0  # см. ginarea_scorer.py


def build_portfolio_summary() -> str:
    """Markdown-отчёт для TG."""
    configs = active_configs()
    if not configs:
        return "📊 Портфель GinArea\n\nНет активных live-ботов в трекере.\nЗапусти `python scripts/track_live_long.py <bot_id>` чтобы зарегистрировать."

    lines = ["📊 Портфель GinArea — активные конфиги", ""]

    total_expected_so_far = 0.0
    total_expected_3mo = 0.0
    total_vol_3mo = 0.0
    total_peak = 0.0

    for c in configs:
        days = days_since(c.get("started_at", ""))
        expected_so_far = expected_so_far_usd(c)
        total_expected_so_far += expected_so_far
        total_expected_3mo += c.get("expected_profit_3mo_usd", 0.0)
        total_vol_3mo += c.get("expected_vol_3mo_musd", 0.0)
        total_peak += c.get("expected_peak_usd", 0.0)

        lines.append(f"🤖 {c.get('name', c.get('bot_id'))}")
        lines.append(f"   bot_id: `{c.get('bot_id')}`")
        lines.append(
            f"   {c.get('side', '?').upper()} "
            f"gs={c.get('gs')} t={c.get('thresh')} TD={c.get('td')} "
            f"mult={c.get('mult')} TP={c.get('tp')}"
        )
        lines.append(f"   В live: {days:.1f} дней")
        lines.append(
            f"   Ожидание: +${c.get('expected_profit_3mo_usd', 0):,.0f} / 3мес "
            f"(vol {c.get('expected_vol_3mo_musd', 0):.1f}M$, "
            f"peak {c.get('expected_peak_usd', 0) / 1000:.0f}k$)"
        )
        lines.append(f"   К сейчас: ~+${expected_so_far:,.0f} (линейно)")
        lines.append("")

    # Σ
    vol_per_month = total_vol_3mo / 3.0
    rebate_per_month = vol_per_month * REBATE_PER_VOL_MUSD
    rebate_per_year = rebate_per_month * 12
    profit_per_year = total_expected_3mo * 4
    total_per_year = profit_per_year + rebate_per_year

    lines += [
        "═" * 30,
        f"Σ ожидание ({len(configs)} бот{'ов' if len(configs) != 1 else ''}):",
        f"  • К сейчас ожидание: ~+${total_expected_so_far:,.0f}",
        f"  • PnL за 3 мес: +${total_expected_3mo:,.0f}",
        f"  • Vol за 3 мес: {total_vol_3mo:.1f}M$",
        f"  • Σ peak USD-экспозиции: ${total_peak / 1000:.0f}k",
        "",
        "💰 Прогноз ребейтов BitMEX (~$250/M$ vol):",
        f"  • ${rebate_per_month:.0f}/мес = ${rebate_per_year:,.0f}/год",
        "",
        "📈 Σ годовое ожидание:",
        f"  • Profit: ${profit_per_year:,.0f}",
        f"  • + Rebate: ${rebate_per_year:,.0f}",
        f"  • = ${total_per_year:,.0f}/год",
    ]

    return "\n".join(lines)
