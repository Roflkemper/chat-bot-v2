"""Humanize: технические коды → человеко-понятные русские имена.

Используется в TG-сообщениях и отчётах. Не меняет внутренние константы
(setup_type enum, scenario keys), только рендеринг для оператора.

Глоссарий: docs/STRATEGIES/NAMING_GLOSSARY.md
"""
from __future__ import annotations


SCENARIO_NAMES: dict[str, str] = {
    "baseline": "Без вмешательства",
    "pause_on_drawdown": "Защита от слива",
    "partial_unload_on_retrace": "Частичная фиксация",
    "trend_chase": "Подъём границ за трендом",
    "combined": "Защита+Фиксация+Догон",
}

SETUP_TYPE_NAMES: dict[str, str] = {
    "long_pdl_bounce": "Отбой от вчерашнего лоу (LONG)",
    "long_dump_reversal": "Разворот после слива (LONG)",
    "long_oversold_reclaim": "Возврат из перепроданности (LONG)",
    "long_liq_magnet": "Магнит ликвидаций (LONG)",
    "short_pdh_rejection": "Отбой от вчерашнего хая (SHORT)",
    "short_rally_fade": "Фейд после ралли (SHORT)",
    "short_overbought_fade": "Фейд из перекупленности (SHORT)",
    "short_liq_magnet": "Магнит ликвидаций (SHORT)",
    "long_double_bottom": "Двойное дно (LONG)",
    "short_double_top": "Двойная вершина (SHORT)",
    "long_multi_divergence": "Множественная дивергенция (LONG)",
    "long_div_bos_confirmed": "Дивергенция + слом структуры (LONG, 1h)",
    "long_div_bos_15m": "Дивергенция + слом структуры (LONG, 15m)",
    "short_div_bos_15m": "Дивергенция + слом структуры (SHORT, 15m)",
    "long_multi_asset_confluence": "Согласие BTC+ETH (LONG)",
    "long_multi_asset_confluence_v2": "Согласие BTC+ETH+XRP (LONG)",
    "long_mega_dump_bounce": "Мега-сетап: разворот + отбой (LONG)",
    "long_rsi_momentum_ga": "Импульс RSI вверх (LONG, найден GA)",
    "short_mfi_multi_ga": "Истощение объёма + 3 актива (SHORT, найден GA)",
    "p15_long_open": "Перебалансировка тренда — открытие (LONG, P-15)",
    "p15_long_harvest": "Перебалансировка тренда — фиксация (LONG, P-15)",
    "p15_long_reentry": "Перебалансировка тренда — перевход (LONG, P-15)",
    "p15_long_close": "Перебалансировка тренда — закрытие (LONG, P-15)",
    "p15_short_open": "Перебалансировка тренда — открытие (SHORT, P-15)",
    "p15_short_harvest": "Перебалансировка тренда — фиксация (SHORT, P-15)",
    "p15_short_reentry": "Перебалансировка тренда — перевход (SHORT, P-15)",
    "p15_short_close": "Перебалансировка тренда — закрытие (SHORT, P-15)",
}

BOT_ALIASES: dict[str, str] = {
    "5196832375": "TEST_1",
    "5017849873": "TEST_2",
    "4524162672": "TEST_3",
    "5188321731": "ШОРТ-ОБЪЁМ",
    "5773124036": "ЛОНГ-ОБЪЁМ",
    "5154651487": "ЛОНГ-ХЕДЖ",
    "5427983401": "ЛОНГ-B",
    "5312167170": "ЛОНГ-C",
    "6075975963": "ИМПУЛЬС",
}


def humanize_scenario(code: str) -> str:
    """combined → 'Защита+Фиксация+Догон'."""
    return SCENARIO_NAMES.get(code, code)


def humanize_setup_type(code: str) -> str:
    """long_multi_divergence → 'Множественная дивергенция (LONG)'."""
    return SETUP_TYPE_NAMES.get(code, code)


def humanize_bot(bot_id: str) -> str:
    """4524162672 → 'TEST_3'."""
    return BOT_ALIASES.get(str(bot_id).replace(".0", ""), str(bot_id))
