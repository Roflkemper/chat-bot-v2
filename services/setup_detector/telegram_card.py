from __future__ import annotations

from .models import Setup, SetupType, setup_side

_LONG_ICON = "🟢"
_SHORT_ICON = "🔴"
_GRID_ICON = "⚙️"
_DEF_ICON = "⚠️"


def format_telegram_card(setup: Setup) -> str:
    side = setup_side(setup)
    if side == "long":
        return _format_trade_card(setup, direction="LONG", icon=_LONG_ICON)
    if side == "short":
        return _format_trade_card(setup, direction="SHORT", icon=_SHORT_ICON)
    if side == "grid":
        return _format_grid_card(setup)
    return _format_defensive_card(setup)


def _format_trade_card(setup: Setup, *, direction: str, icon: str) -> str:
    ts = setup.detected_at.strftime("%H:%M UTC")
    basis_lines = "\n".join(f"• {b.label}" for b in setup.basis[:5])
    cancel_lines = "\n".join(f"• {c}" for c in setup.cancel_conditions[:3])

    entry_str = f"${setup.entry_price:,.1f}" if setup.entry_price else "—"
    stop_str = f"${setup.stop_price:,.1f}" if setup.stop_price else "—"
    tp1_str = f"${setup.tp1_price:,.1f}" if setup.tp1_price else "—"
    tp2_str = f"${setup.tp2_price:,.1f}" if setup.tp2_price else "—"
    rr_str = f"1:{setup.risk_reward:.1f}" if setup.risk_reward else "—"

    return (
        f"{icon} {direction} SETUP — {setup.pair} | {ts}\n"
        f"\n"
        f"Цена ${setup.current_price:,.1f}\n"
        f"Сила: {setup.strength}/10 | Уверенность: {setup.confidence_pct:.0f}%\n"
        f"\n"
        f"ВХОД: {entry_str} (limit)\n"
        f"СТОП: {stop_str}\n"
        f"ЦЕЛИ: TP1 {tp1_str} | TP2 {tp2_str}\n"
        f"RR: {rr_str}\n"
        f"\n"
        f"ОСНОВАНИЕ:\n{basis_lines}\n"
        f"\n"
        f"ОТМЕНА:\n{cancel_lines}\n"
        f"\n"
        f"Портфель: {setup.portfolio_impact_note}\n"
        f"Размер: {setup.recommended_size_btc:.2f} BTC | Окно: {setup.window_minutes} мин"
    )


def _format_grid_card(setup: Setup) -> str:
    ts = setup.detected_at.strftime("%H:%M UTC")
    basis_lines = "\n".join(f"• {b.label}" for b in setup.basis[:5])
    bots_str = ", ".join(setup.grid_target_bots) if setup.grid_target_bots else "—"
    action_str = setup.grid_action or "—"

    return (
        f"{_GRID_ICON} GRID ACTION — {setup.pair} | {ts}\n"
        f"\n"
        f"Цена ${setup.current_price:,.1f}\n"
        f"Сила: {setup.strength}/10 | Уверенность: {setup.confidence_pct:.0f}%\n"
        f"\n"
        f"Действие: {action_str}\n"
        f"Боты: {bots_str}\n"
        f"\n"
        f"ОСНОВАНИЕ:\n{basis_lines}\n"
        f"\n"
        f"Окно: {setup.window_minutes} мин"
    )


def _format_defensive_card(setup: Setup) -> str:
    ts = setup.detected_at.strftime("%H:%M UTC")
    basis_lines = "\n".join(f"• {b.label}" for b in setup.basis[:5])
    cancel_lines = "\n".join(f"• {c}" for c in setup.cancel_conditions[:3])

    return (
        f"{_DEF_ICON} ЗАЩИТНЫЙ АЛЕРТ — {setup.pair} | {ts}\n"
        f"\n"
        f"Цена ${setup.current_price:,.1f}\n"
        f"Сила: {setup.strength}/10\n"
        f"\n"
        f"СИГНАЛ: {setup.portfolio_impact_note}\n"
        f"\n"
        f"ОСНОВАНИЕ:\n{basis_lines}\n"
        f"\n"
        f"ОТМЕНА:\n{cancel_lines}"
    )


def format_outcome_card(
    setup: Setup,
    new_status: str,
    current_price: float,
    hypothetical_pnl_usd: float | None,
    time_to_outcome_min: int | None,
) -> str:
    side = setup_side(setup)
    if new_status in ("tp1_hit", "tp2_hit"):
        icon = "✅"
        label = "TP1 HIT" if new_status == "tp1_hit" else "TP2 HIT"
    elif new_status == "stop_hit":
        icon = "❌"
        label = "STOP HIT"
    elif new_status == "expired":
        icon = "⏱"
        label = "EXPIRED"
    else:
        icon = "ℹ️"
        label = new_status.upper().replace("_", " ")

    direction = side.upper()
    pnl_str = f"Hypothetical: {hypothetical_pnl_usd:+.0f} USD" if hypothetical_pnl_usd is not None else ""
    time_str = f"Время: {time_to_outcome_min} мин" if time_to_outcome_min is not None else ""

    entry_str = f"${setup.entry_price:,.1f}" if setup.entry_price else "—"

    lines = [
        f"{icon} {label} — {direction} SETUP {setup.pair}",
        f"Entry: {entry_str} → Текущая: ${current_price:,.1f}",
    ]
    if pnl_str:
        lines.append(pnl_str)
    if time_str:
        lines.append(time_str)
    lines.append(f"Setup ID: {setup.setup_id}")

    return "\n".join(lines)
