"""Русскоязычные переводы для Telegram UI.

Принцип: код работает на английских константах (RUN, PAUSE, RANGE).
Перевод применяется только при рендеринге сообщений в Telegram.
"""

REGIME_RU = {
    "RANGE":        "БОКОВИК",
    "TREND_UP":     "ТРЕНД ВВЕРХ",
    "TREND_DOWN":   "ТРЕНД ВНИЗ",
    "COMPRESSION":  "СЖАТИЕ",
    "CASCADE_UP":   "КАСКАД ВВЕРХ",
    "CASCADE_DOWN": "КАСКАД ВНИЗ",
}

REGIME_EMOJI = {
    "RANGE":        "📊",
    "TREND_UP":     "📈",
    "TREND_DOWN":   "📉",
    "COMPRESSION":  "🔒",
    "CASCADE_UP":   "⚡",
    "CASCADE_DOWN": "⚡",
}

ACTION_RU = {
    "RUN":     "РАБОТАЕТ",
    "REDUCE":  "УМЕНЬШЕН",
    "ARM":     "ВЗВЕДЁН",
    "PAUSE":   "ПАУЗА",
    "STOP":    "СТОП",
    "KILLSWITCH": "KILLSWITCH",
    "RESET":   "СБРОС",
}

ACTION_EMOJI = {
    "RUN":     "🟢",
    "REDUCE":  "🟡",
    "ARM":     "⚪",
    "PAUSE":   "⏸",
    "STOP":    "🔴",
    "KILLSWITCH": "🚨",
    "RESET":   "🔄",
}

MODIFIER_RU = {
    "WEEKEND_LOW_VOL":        "ВЫХОДНЫЕ: НИЗКАЯ ВОЛАТИЛЬНОСТЬ",
    "WEEKEND_GAP_DETECTED":   "ГЭП ВЫХОДНЫХ",
    "HUGE_DOWN_GAP":          "КРУПНЫЙ ГЭП ВНИЗ",
    "TREND_UP_SUSPECTED":     "ТРЕНД ВВЕРХ ПОД ВОПРОСОМ",
    "TREND_DOWN_SUSPECTED":   "ТРЕНД ВНИЗ ПОД ВОПРОСОМ",
    "POST_FUNDING_HOUR":      "ПОСЛЕ ФАНДИНГА",
    "NEWS_BLACKOUT":          "БЛЭКАУТ НА НОВОСТИ",
}

CATEGORY_RU = {
    "btc_short":    "BTC ШОРТ",
    "btc_long":     "BTC ЛОНГ",
    "btc_long_l2":  "BTC ЛОНГ ИМПУЛЬС",
    "xrp_short":    "XRP ШОРТ",
    "xrp_long":     "XRP ЛОНГ",
    "xrp_long_big": "XRP ЛОНГ КРУПНЫЙ",
    "eth_short":    "ETH ШОРТ",
    "eth_long":     "ETH ЛОНГ",
    "sol_short":    "SOL ШОРТ",
    "sol_long":     "SOL ЛОНГ",
}

BOT_STATE_RU = {
    "ACTIVE":            "🟢 работает",
    "PAUSED_BY_REGIME":  "⏸ на паузе (режим)",
    "PAUSED_MANUAL":     "⏸ на паузе (вручную)",
    "READY":             "⚪ готов",
    "PLANNED":           "📋 запланирован",
    "KILLSWITCH":        "🔴 kill-switch",
    "ARCHIVED":          "🗃 в архиве",
}

SESSION_RU = {
    "ASIAN": "Азия",
    "EU":    "Европа",
    "US":    "Америка",
    "OFF":   "вне сессии",
}

WEEKDAY_RU = {
    0: "Пн", 1: "Вт", 2: "Ср", 3: "Чт", 4: "Пт", 5: "Сб", 6: "Вс",
}


def tr(key: str, section: dict, default: str | None = None) -> str:
    """Translate key using given section dict.
    
    Returns translated value, or default/key if not found.
    Never raises — graceful fallback for unknown keys.
    """
    if default is None:
        default = key
    return section.get(key, default)
