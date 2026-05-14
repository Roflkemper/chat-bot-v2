from __future__ import annotations

from dataclasses import dataclass

from core.orchestrator.portfolio_state import Category


@dataclass(frozen=True)
class ActionDecision:
    action: str
    reason: str
    reason_en: str
    reduce_size_pct: int | None = None


BASE_MATRIX_BTC = {
    "RANGE": {
        "btc_short": ActionDecision("RUN", "Боковик активирован (ATR<1.5%)", "BASE_RANGE"),
        "btc_long": ActionDecision("RUN", "Боковик активирован (ATR<1.5%)", "BASE_RANGE"),
        "btc_long_l2": ActionDecision("ARM", "Ждём импульс в боковике", "BASE_RANGE_L2_ARM"),
    },
    "TREND_UP": {
        "btc_short": ActionDecision("REDUCE", "Тренд вверх — сокращаем шорт", "BASE_TREND_UP", reduce_size_pct=50),
        "btc_long": ActionDecision("RUN", "Тренд вверх — лонг выгоден", "BASE_TREND_UP"),
        "btc_long_l2": ActionDecision("ARM", "Ждём импульс на откате", "BASE_TREND_UP_L2"),
    },
    "TREND_DOWN": {
        "btc_short": ActionDecision("RUN", "Тренд вниз — шорт работает", "BASE_TREND_DOWN"),
        "btc_long": ActionDecision("PAUSE", "Тренд вниз — лонг на паузу", "BASE_TREND_DOWN"),
        "btc_long_l2": ActionDecision("PAUSE", "Тренд вниз — импульсные стоп", "BASE_TREND_DOWN"),
    },
    "COMPRESSION": {
        "btc_short": ActionDecision("RUN", "Сжатие — сетки работают", "BASE_COMPRESSION"),
        "btc_long": ActionDecision("RUN", "Сжатие — сетки работают", "BASE_COMPRESSION"),
        "btc_long_l2": ActionDecision("ARM", "Ждём пробой из сжатия", "BASE_COMPRESSION_L2"),
    },
    "CASCADE_DOWN": {
        "btc_short": ActionDecision("RUN", "Каскад вниз — шорт усилен", "BASE_CASCADE_DOWN"),
        "btc_long": ActionDecision("STOP", "Каскад вниз — закрыть лонг", "BASE_CASCADE_DOWN"),
        "btc_long_l2": ActionDecision("STOP", "Каскад вниз — импульсные стоп", "BASE_CASCADE_DOWN"),
    },
    "CASCADE_UP": {
        "btc_short": ActionDecision("PAUSE", "Каскад вверх — шорт на паузу", "BASE_CASCADE_UP"),
        "btc_long": ActionDecision("RUN", "Каскад вверх — лонг активен", "BASE_CASCADE_UP"),
        "btc_long_l2": ActionDecision("PAUSE", "Каскад вверх — импульсные стоп", "BASE_CASCADE_UP"),
    },
}

BASE_MATRIX_XRP = {
    "RANGE": {
        "xrp_short": ActionDecision("ARM", "Боковик XRP — ждём импульс вверх", "XRP_BASE_RANGE"),
        "xrp_long": ActionDecision("ARM", "Боковик XRP — ждём импульс вниз", "XRP_BASE_RANGE"),
        "xrp_long_big": ActionDecision("ARM", "Боковик XRP — ждём крупный вынос", "XRP_BASE_RANGE"),
    },
    "TREND_UP": {
        "xrp_short": ActionDecision("ARM", "Тренд вверх XRP", "XRP_TREND_UP"),
        "xrp_long": ActionDecision("ARM", "Тренд вверх XRP", "XRP_TREND_UP"),
        "xrp_long_big": ActionDecision("ARM", "Тренд вверх XRP", "XRP_TREND_UP"),
    },
    "TREND_DOWN": {
        "xrp_short": ActionDecision("ARM", "Тренд вниз XRP — ждём памп", "XRP_TREND_DOWN"),
        "xrp_long": ActionDecision("PAUSE", "Тренд вниз XRP — лонг на паузу", "XRP_TREND_DOWN"),
        "xrp_long_big": ActionDecision("PAUSE", "Тренд вниз XRP — лонг на паузу", "XRP_TREND_DOWN"),
    },
    "COMPRESSION": {
        "xrp_short": ActionDecision("ARM", "Сжатие XRP", "XRP_COMPRESSION"),
        "xrp_long": ActionDecision("ARM", "Сжатие XRP", "XRP_COMPRESSION"),
        "xrp_long_big": ActionDecision("ARM", "Сжатие XRP", "XRP_COMPRESSION"),
    },
    "CASCADE_DOWN": {
        "xrp_short": ActionDecision("STOP", "Каскад вниз — шорт поздно", "XRP_CASCADE_DOWN"),
        "xrp_long": ActionDecision("STOP", "Каскад вниз — лонг стоп", "XRP_CASCADE_DOWN"),
        "xrp_long_big": ActionDecision("ARM", "Каскад вниз — ключевой вынос", "XRP_CASCADE_DOWN_BIG_ARM"),
    },
    "CASCADE_UP": {
        "xrp_short": ActionDecision("ARM", "Каскад вверх — ключевой вынос", "XRP_CASCADE_UP_ARM"),
        "xrp_long": ActionDecision("STOP", "Каскад вверх — лонг стоп", "XRP_CASCADE_UP"),
        "xrp_long_big": ActionDecision("STOP", "Каскад вверх — лонг стоп", "XRP_CASCADE_UP"),
    },
}

UNIVERSAL_FALLBACK = {
    ("SHORT", "GRID_L1"): {
        "RANGE": ActionDecision("RUN", "Боковик — шорт работает", "UNIV_RANGE_SHORT_L1"),
        "TREND_UP": ActionDecision("REDUCE", "Тренд вверх — шорт сокращаем", "UNIV_TREND_UP_SHORT_L1", reduce_size_pct=50),
        "TREND_DOWN": ActionDecision("RUN", "Тренд вниз — шорт активен", "UNIV_TREND_DOWN_SHORT_L1"),
        "COMPRESSION": ActionDecision("RUN", "Сжатие — шорт работает", "UNIV_COMPRESSION_SHORT_L1"),
        "CASCADE_DOWN": ActionDecision("RUN", "Каскад вниз — шорт усилен", "UNIV_CASCADE_DOWN_SHORT_L1"),
        "CASCADE_UP": ActionDecision("PAUSE", "Каскад вверх — шорт пауза", "UNIV_CASCADE_UP_SHORT_L1"),
    },
    ("LONG", "GRID_L1"): {
        "RANGE": ActionDecision("RUN", "Боковик — лонг работает", "UNIV_RANGE_LONG_L1"),
        "TREND_UP": ActionDecision("RUN", "Тренд вверх — лонг выгоден", "UNIV_TREND_UP_LONG_L1"),
        "TREND_DOWN": ActionDecision("PAUSE", "Тренд вниз — лонг пауза", "UNIV_TREND_DOWN_LONG_L1"),
        "COMPRESSION": ActionDecision("RUN", "Сжатие — лонг работает", "UNIV_COMPRESSION_LONG_L1"),
        "CASCADE_DOWN": ActionDecision("STOP", "Каскад вниз — лонг стоп", "UNIV_CASCADE_DOWN_LONG_L1"),
        "CASCADE_UP": ActionDecision("RUN", "Каскад вверх — лонг активен", "UNIV_CASCADE_UP_LONG_L1"),
    },
    ("LONG", "GRID_L2_IMPULSE"): {
        "RANGE": ActionDecision("ARM", "Ждём импульс", "UNIV_L2_ARM"),
        "TREND_UP": ActionDecision("ARM", "Ждём импульс на откате", "UNIV_L2_ARM"),
        "TREND_DOWN": ActionDecision("PAUSE", "Тренд вниз — импульсные стоп", "UNIV_L2_TREND_DOWN"),
        "COMPRESSION": ActionDecision("ARM", "Ждём пробой", "UNIV_L2_ARM"),
        "CASCADE_DOWN": ActionDecision("STOP", "Каскад — импульсные стоп", "UNIV_L2_CASCADE"),
        "CASCADE_UP": ActionDecision("PAUSE", "Каскад — импульсные пауза", "UNIV_L2_CASCADE"),
    },
    ("SHORT", "GRID_L2_IMPULSE"): {
        "RANGE": ActionDecision("ARM", "Ждём импульс", "UNIV_L2_ARM"),
        "TREND_UP": ActionDecision("PAUSE", "Тренд вверх — шорт-импульсные стоп", "UNIV_L2_TREND_UP"),
        "TREND_DOWN": ActionDecision("ARM", "Ждём импульс на отскоке", "UNIV_L2_ARM"),
        "COMPRESSION": ActionDecision("ARM", "Ждём пробой вниз", "UNIV_L2_ARM"),
        "CASCADE_DOWN": ActionDecision("PAUSE", "Каскад — импульсные пауза", "UNIV_L2_CASCADE"),
        "CASCADE_UP": ActionDecision("STOP", "Каскад — импульсные стоп", "UNIV_L2_CASCADE"),
    },
}


def get_base_decision(regime: str, category: Category) -> ActionDecision | None:
    if category.asset.upper() == "BTC":
        specific = BASE_MATRIX_BTC.get(regime, {}).get(category.key)
        if specific:
            return specific
    elif category.asset.upper() == "XRP":
        specific = BASE_MATRIX_XRP.get(regime, {}).get(category.key)
        if specific:
            return specific

    strategy_type = "GRID_L2_IMPULSE" if category.key.endswith("_l2") else "GRID_L1"
    side = category.side.upper()
    return UNIVERSAL_FALLBACK.get((side, strategy_type), {}).get(regime)


def apply_modifiers(base: ActionDecision, category: Category, modifiers: list[str]) -> ActionDecision:
    result = base
    side = category.side.upper()
    is_long = side == "LONG"
    is_l2 = category.key.endswith("_l2")

    if "NEWS_BLACKOUT" in modifiers:
        return ActionDecision("STOP", "Новостной блэкаут — всё стоит", "MOD_NEWS_BLACKOUT")

    if "HUGE_DOWN_GAP" in modifiers and is_long:
        return ActionDecision("PAUSE", "Крупный гэп вниз — лонг на паузу 48ч", "MOD_HUGE_DOWN_GAP")

    if "TREND_UP_SUSPECTED" in modifiers and side == "SHORT" and result.action == "REDUCE":
        result = ActionDecision("RUN", "Тренд вверх под вопросом — шорт работает нормально", "MOD_TREND_UP_SUSPECTED")

    if "TREND_DOWN_SUSPECTED" in modifiers and is_long and result.action == "PAUSE":
        result = ActionDecision("RUN", "Тренд вниз под вопросом — лонг работает нормально", "MOD_TREND_DOWN_SUSPECTED")

    if "POST_FUNDING_HOUR" in modifiers and is_l2 and result.action == "ARM":
        result = ActionDecision("PAUSE", "После фандинга — L2 ждут 30 минут", "MOD_POST_FUNDING_HOUR")

    if "WEEKEND_LOW_VOL" in modifiers and is_l2:
        result = ActionDecision("STOP", "Выходные — импульсные на стоп", "MOD_WEEKEND_LOW_VOL")

    return result


def decide_category_action(regime: str, modifiers: list[str], category: Category) -> ActionDecision:
    base = get_base_decision(regime, category)
    if base is None:
        return ActionDecision(
            "RUN",
            f"Нет правила для {category.key} в {regime}, сохраняем RUN",
            "NO_RULE_FALLBACK",
        )
    return apply_modifiers(base, category, modifiers)
