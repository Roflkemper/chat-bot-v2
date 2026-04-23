from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from core.orchestrator.i18n_ru import (
    ACTION_EMOJI,
    ACTION_RU,
    BOT_STATE_RU,
    CATEGORY_RU,
    MODIFIER_RU,
    REGIME_RU,
    SESSION_RU,
    WEEKDAY_RU,
    tr,
)
from core.orchestrator.portfolio_state import Bot, Category, PortfolioSnapshot
from core.orchestrator.visuals import bias_scale, progress_bar, regime_header, separator


def _fmt_dt(dt: datetime | None, *, with_year: bool = False) -> str:
    if dt is None:
        return "—"
    value = dt.astimezone(timezone.utc)
    fmt = "%d.%m.%Y %H:%M UTC" if with_year else "%d.%m %H:%M"
    return value.strftime(fmt)


def _fmt_pct(value: Any, digits: int = 2) -> str:
    try:
        return f"{float(value):.{digits}f}%"
    except Exception:
        return "0.00%"


def _fmt_signed_pct(value: Any, digits: int = 2) -> str:
    try:
        return f"{float(value):+.{digits}f}%"
    except Exception:
        return "+0.00%"


def _fmt_float(value: Any, digits: int = 3) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except Exception:
        return "0"


def _fmt_age(age_bars: Any, tick_minutes: int = 15) -> str:
    try:
        total = int(age_bars or 0) * tick_minutes
    except Exception:
        total = 0
    hours, minutes = divmod(total, 60)
    if hours and minutes:
        return f"{hours} часов {minutes} минут"
    if hours:
        return f"{hours} часов"
    if minutes:
        return f"{minutes} минут"
    return "только что"


def _fmt_session_label(session: str, regime: dict[str, Any]) -> str:
    session_ru = tr(session, SESSION_RU)
    ts = regime.get("ts")
    if ts:
        if isinstance(ts, str):
            try:
                ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except Exception:
                ts = None
        if isinstance(ts, datetime):
            ts = ts.astimezone(timezone.utc)
            weekday = WEEKDAY_RU.get(ts.weekday(), "")
            return f"{session_ru} ({weekday} {ts.strftime('%H:%M')} UTC)"
    return session_ru


def _contract_display(cat: Category) -> str:
    if cat.contract_type == "inverse":
        return "inverse (XBTUSD)"
    if cat.contract_type == "linear":
        return "linear"
    return cat.contract_type or "—"


def _iter_category_bots(portfolio: PortfolioSnapshot, category_key: str) -> list[Bot]:
    return [bot for bot in portfolio.bots.values() if bot.category == category_key]


def render_portfolio(portfolio: PortfolioSnapshot, regime: dict[str, Any]) -> str:
    lines: list[str] = [
        separator(28),
        f"  💼 ПОРТФЕЛЬ  {_fmt_dt(portfolio.updated_at)}",
        separator(28),
        "",
    ]

    if regime and regime.get("primary"):
        primary = str(regime.get("primary") or "")
        age = regime.get("age_bars", 0)
        bias = int(regime.get("bias_score") or 0)
        session = tr(str(regime.get("session") or "OFF"), SESSION_RU)
        metrics = regime.get("metrics") if isinstance(regime.get("metrics"), dict) else {}
        atr = float(metrics.get("atr_pct_1h") or 0.0)
        adx = float(metrics.get("adx_1h") or 0.0)

        lines.append(f"📊 РЫНОК BTC: {regime_header(primary, age)}")
        lines.append(f"   Биас:  {bias_scale(bias)}  {bias:+d}")
        lines.append(f"   ATR 1ч: {atr:.1f}%  |  ADX: {adx:.0f}")
        lines.append(f"   Сессия: {session}")
        mods = list(regime.get("modifiers") or [])
        if mods:
            lines.append(f"   Модификаторы: {', '.join(tr(m, MODIFIER_RU) for m in mods)}")
        lines.append("")

    lines.extend(["📋 КАТЕГОРИИ", ""])
    for cat in portfolio.categories.values():
        action_emoji = tr(cat.orchestrator_action, ACTION_EMOJI, default="⚪")
        action_ru = tr(cat.orchestrator_action, ACTION_RU)
        lines.append(f" {action_emoji} {cat.label_ru:<18} {action_ru}")

        bots_here = _iter_category_bots(portfolio, cat.key)
        if not bots_here:
            lines.append("    └ (боты не настроены)")
        else:
            for bot in bots_here:
                state_ru = tr(bot.state, BOT_STATE_RU)
                lines.append(f"    └ {bot.key:<18} {state_ru}")
                lines.append(f"      Плечо: {_contract_display(cat)}")
                lines.append(f"      Стратегия: {bot.strategy_type}")
        lines.append("")

    lines.append(separator(28))
    lines.append(
        f"Маржа:  {progress_bar(portfolio.margin_used_pct, 100, 15, warn_threshold=70, danger_threshold=85)}"
    )
    pnl_str = f"+${portfolio.daily_pnl_usd:.0f}" if portfolio.daily_pnl_usd >= 0 else f"-${abs(portfolio.daily_pnl_usd):.0f}"
    pnl_suffix = "  (нет данных)" if abs(portfolio.daily_pnl_usd) < 1e-9 else ""
    lines.append(f"PnL сутки:  {pnl_str}{pnl_suffix}")
    lines.append(separator(28))
    lines.extend(
        [
            "",
            "Подробнее:",
            "  /regime       — детали рынка",
            "  /category <k> — категория",
            "  /bot <k>      — один бот",
        ]
    )
    return "\n".join(lines)


def render_regime_details(regime: dict[str, Any]) -> str:
    primary = str(regime.get("primary") or "RANGE")
    metrics = regime.get("metrics") if isinstance(regime.get("metrics"), dict) else {}
    bias = int(regime.get("bias_score") or 0)
    modifiers = list(regime.get("modifiers") or [])

    adx = float(metrics.get("adx_1h") or 0.0)
    if adx >= 30:
        adx_note = "сильный тренд"
    elif adx >= 20:
        adx_note = "умеренный тренд"
    else:
        adx_note = "слабый тренд"

    stack = int(metrics.get("ema_stack_1h") or 0)
    if stack >= 2:
        stack_text = "Close > EMA20 > EMA50 > EMA200"
    elif stack == 1:
        stack_text = "Close > EMA20 > EMA50, но ≤ EMA200"
    elif stack == 0:
        stack_text = "Close между EMA20/EMA50, EMA200 рядом"
    elif stack == -1:
        stack_text = "Close < EMA20 < EMA50, но ≥ EMA200"
    else:
        stack_text = "Close < EMA20 < EMA50 < EMA200"

    lines = [
        separator(28),
        "  📊 РЕЖИМ РЫНКА BTC",
        separator(28),
        "",
        f"Режим:  {regime_header(primary, 0).split('  (')[0]}",
        f"Стоит:  {_fmt_age(regime.get('age_bars', 0))}",
        f"Сессия: {_fmt_session_label(str(regime.get('session') or 'OFF'), regime)}",
        "",
        "МЕТРИКИ",
        f"  ATR 1ч:    {_fmt_pct(metrics.get('atr_pct_1h'), 2)}",
        f"  ATR 4ч:    {_fmt_pct(metrics.get('atr_pct_4h'), 2)}",
        f"  ATR 5м:    {_fmt_pct(metrics.get('atr_pct_5m'), 2)}",
        f"  ADX 1ч:    {adx:.0f}  ({adx_note})",
        f"  BB ширина: {_fmt_pct(metrics.get('bb_width_pct_1h'), 1)}",
        f"  До EMA200: {_fmt_signed_pct(metrics.get('dist_to_ema200_pct'), 1)}",
        f"  Биас:  {bias_scale(bias)}  {bias:+d}",
        "",
        "EMA-СТЕК",
        f"  {stack_text}  (стек: {stack:+d})",
        "",
        "ДВИЖЕНИЕ",
        f"  За 5м:   {_fmt_signed_pct(metrics.get('last_move_pct_5m'), 2)}",
        f"  За 15м:  {_fmt_signed_pct(metrics.get('last_move_pct_15m'), 2)}",
        f"  За 1ч:   {_fmt_signed_pct(metrics.get('last_move_pct_1h'), 2)}",
        f"  За 4ч:   {_fmt_signed_pct(metrics.get('last_move_pct_4h'), 2)}",
        "",
        "ОБЪЁМ/ФАНДИНГ",
        f"  Объём 24ч: {_fmt_float(metrics.get('volume_ratio_24h'), 2)}× от среднего",
        f"  Фандинг:   {_fmt_signed_pct(metrics.get('funding_rate'), 3)}",
        "",
        "МОДИФИКАТОРЫ",
    ]
    if modifiers:
        lines.extend(f"  {tr(mod, MODIFIER_RU)}" for mod in modifiers)
    else:
        lines.append("  (нет активных)")
    lines.append(separator(28))
    return "\n".join(lines)


def render_category(cat: Category, bots: Iterable[Bot]) -> str:
    bots_list = list(bots)
    modifiers = ", ".join(tr(mod, MODIFIER_RU) for mod in cat.modifiers_active) if cat.modifiers_active else "нет"
    lines = [
        separator(28),
        f"  📂 {cat.label_ru} ({cat.key})",
        separator(28),
        "",
        f"Действие:  {tr(cat.orchestrator_action, ACTION_EMOJI, default='⚪')} {tr(cat.orchestrator_action, ACTION_RU)}",
        f"Причина:   {cat.base_reason or 'нет данных'}",
        f"Модификаторы: {modifiers}",
        "",
        "ПАРАМЕТРЫ КАТЕГОРИИ",
        f"  Актив:    {cat.asset}",
        f"  Сторона:  {cat.side}",
        f"  Контракт: {_contract_display(cat)}",
        f"  Активна:  {'да' if cat.enabled else 'нет'}",
        f"  Изменено: {_fmt_dt(cat.last_command_at, with_year=True)}",
        "",
        f"БОТЫ В КАТЕГОРИИ ({len(bots_list)})",
    ]
    if not bots_list:
        lines.append("  └ (боты не настроены)")
    else:
        for bot in bots_list:
            lines.append(f" • {bot.key}")
            lines.append(f"     Статус:    {tr(bot.state, BOT_STATE_RU)}")
            lines.append(f"     Стратегия: {bot.strategy_type}")
            lines.append(f"     Уровень:   {bot.stage}")
            lines.append("     Параметры:")
            for key in ("step_pct", "target_pct", "max_orders"):
                if key not in bot.params:
                    continue
                value = bot.params.get(key)
                if key.endswith("_pct"):
                    value_str = _fmt_pct(value, 3 if key == "step_pct" else 2)
                else:
                    value_str = str(value)
                pretty_key = {"step_pct": "step", "target_pct": "target", "max_orders": "max orders"}[key]
                lines.append(f"       {pretty_key}:    {value_str}")
    lines.append(separator(28))
    return "\n".join(lines)


def render_bot(bot: Bot, category: Category | None) -> str:
    category_label = f"{category.label_ru} ({category.key})" if category else bot.category
    action_line = "  сейчас: —"
    if category is not None:
        action_line = (
            f"  сейчас: {tr(category.orchestrator_action, ACTION_EMOJI, default='⚪')} "
            f"{tr(category.orchestrator_action, ACTION_RU)} ({category.base_reason or '—'})"
        )

    lines = [
        separator(28),
        f"  🤖 {bot.key}",
        separator(28),
        "",
        f"Название:  {bot.label}",
        f"Категория: {category_label}",
        f"Статус:    {tr(bot.state, BOT_STATE_RU)}",
        f"Стратегия: {bot.strategy_type}",
        f"Уровень:   {bot.stage}",
        "",
        "ПАРАМЕТРЫ",
    ]
    for key, value in bot.params.items():
        if isinstance(value, (int, float)) and key.endswith("_pct"):
            value_str = _fmt_pct(value, 3 if key == "step_pct" else 3)
        else:
            value_str = str(value)
        lines.append(f"  {key}:    {value_str}")

    lines.extend(
        [
            "",
            "МЕТА",
            f"  Создан:  {_fmt_dt(bot.created_at, with_year=True)}",
            f"  Стопов подряд: {bot.consecutive_stops}",
            f"  Kill-switch:   {'да' if bot.killswitch_triggered else 'нет'}",
            "",
            "ДЕЙСТВИЕ КАТЕГОРИИ",
            action_line,
            separator(28),
        ]
    )
    return "\n".join(lines)


def render_action_alert(
    change: Any,
    regime: str,
    modifiers: list[str],
    regime_metrics: dict[str, Any] | None = None,
) -> str:
    cat_name_ru = tr(change.category_key, CATEGORY_RU)
    action_ru = tr(change.to_action, ACTION_RU)
    regime_ru = tr(regime, REGIME_RU)

    if change.to_action in {"STOP", "PAUSE"}:
        title = f"⚠️ ДЕЙСТВИЕ: {cat_name_ru} → {action_ru}"
    else:
        title = f"ℹ️ СМЕНА РЕЖИМА: {cat_name_ru} → {action_ru}"

    lines = [title, "", f"Причина:  {change.reason_ru}", f"Режим:    {regime_ru}"]

    if modifiers:
        lines.append(f"Модификаторы: {', '.join(tr(m, MODIFIER_RU) for m in modifiers)}")
    else:
        lines.append("Модификаторы: нет")

    if change.affected_bots:
        lines.extend(["", "Затронуты боты:"])
        lines.extend(f"  • {bot_key}" for bot_key in change.affected_bots)

    lines.extend(["", "ДЕЙСТВИЕ В GinArea:"])
    lines.extend(f"  {hint}" for hint in _get_action_hint(change.to_action, change.affected_bots))

    if regime_metrics:
        adx = float(regime_metrics.get("adx_1h") or 0.0)
        bias = int(regime_metrics.get("bias_score") or 0)
        lines.extend(["", "МЕТРИКИ:", f"  • ADX 1ч: {adx:.0f}", f"  • Биас: {bias:+d}"])

    lines.extend(["", separator(28)])
    return "\n".join(lines)


def _get_action_hint(action: str, bot_keys: list[str]) -> list[str]:
    bot_list = ", ".join(bot_keys) if bot_keys else "(нет активных)"
    if action == "STOP":
        return [f"— остановить боты: {bot_list}", "— закрыть текущие позиции"]
    if action == "PAUSE":
        return [f"— приостановить боты: {bot_list}", "— позиции оставить (будут закрыты ботом по TP)"]
    if action == "REDUCE":
        return ["— уменьшить размер ордеров в 2 раза в ботах:", f"  {bot_list}"]
    if action == "RUN":
        return ["— возобновить работу ботов:", f"  {bot_list if bot_keys else '(уже работают)'}"]
    if action == "ARM":
        return ["— боты в режиме ожидания триггера", "  (ничего не нужно менять вручную)"]
    return ["— проверить настройки ботов"]
