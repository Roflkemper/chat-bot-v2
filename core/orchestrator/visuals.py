"""Unicode визуализация для Telegram UI.

Ширина шкал — 10 или 15 символов для хорошего отображения на мобильных.
Используются блочные символы U+2580-U+259F которые надёжно рендерятся в Telegram.
"""


def bias_scale(score: int, width: int = 10) -> str:
    """Шкала bias от −100 до +100 с маркером позиции.
    
    score ∈ [-100, +100]
    width — общая ширина шкалы в символах (рекомендуется 10)
    
    Примеры:
      +24  →  ━━━━━▓━━━━  (справа от центра)
      −35  →  ━━━▓━━━━━━  (слева от центра)
        0  →  ━━━━━●━━━━  (точно по центру)
    """
    score = max(-100, min(100, score))
    center = width // 2
    # Позиция маркера от 0 до width
    pos = center + round(score / 100 * center)
    pos = max(0, min(width - 1, pos))
    
    marker = "●" if abs(score) < 5 else "▓"
    chars = ["━"] * width
    chars[pos] = marker
    return "".join(chars)


def progress_bar(value: float, vmax: float = 100, width: int = 15, 
                 warn_threshold: float | None = None,
                 danger_threshold: float | None = None) -> str:
    """Прогресс-бар с опциональными предупреждениями.
    
    value   — текущее значение
    vmax    — максимум
    width   — ширина в символах
    warn_threshold, danger_threshold — пороги для смены символа (не обязательны)
    
    Использует ▓ для заполнения, ░ для пустого места.
    При превышении warn threshold — добавляет ⚠, при danger — 🔴.
    
    Примеры:
      54%  →  ████████░░░░░░░  54%
      82%  →  ████████████▓░░  ⚠
      95%  →  ██████████████░  🔴
    """
    value = max(0, min(vmax, value))
    filled = round(value / vmax * width)
    bar = "█" * filled + "░" * (width - filled)
    
    pct = value / vmax * 100
    suffix = ""
    if danger_threshold and value >= danger_threshold:
        suffix = "  🔴"
    elif warn_threshold and value >= warn_threshold:
        suffix = "  ⚠"
    
    return f"{bar}  {pct:.0f}%{suffix}"


def regime_header(regime_en: str, age_bars: int, tick_minutes: int = 15) -> str:
    """Заголовок для режима с возрастом.
    
    Примеры:
      regime_header("RANGE", 48, 15)         → "📊 БОКОВИК  (12ч стоит)"
      regime_header("TREND_DOWN", 17, 15)    → "📉 ТРЕНД ВНИЗ  (4ч 15м)"
      regime_header("CASCADE_DOWN", 0, 15)   → "⚡ КАСКАД ВНИЗ  (только что)"
    """
    from .i18n_ru import REGIME_RU, REGIME_EMOJI, tr
    
    name = tr(regime_en, REGIME_RU)
    emoji = tr(regime_en, REGIME_EMOJI, default="")
    
    total_minutes = age_bars * tick_minutes
    if total_minutes == 0:
        age_str = "только что"
    elif total_minutes < 60:
        age_str = f"{total_minutes}м"
    else:
        hours = total_minutes // 60
        mins = total_minutes % 60
        if mins == 0:
            age_str = f"{hours}ч"
        else:
            age_str = f"{hours}ч {mins}м"
    
    return f"{emoji} {name}  ({age_str})"


def separator(width: int = 28) -> str:
    """Разделитель для сообщений."""
    return "━" * width
