from __future__ import annotations

from typing import Any, Dict


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def analyze_impulse_from_payload(data: Dict[str, Any] | None) -> Dict[str, Any]:
    data = data or {}
    signal = str(data.get("final_decision") or data.get("signal") or "NEUTRAL").upper()
    range_state = str(data.get("range_state") or "").lower()
    ct_now = str(data.get("ct_now") or "").lower()
    conf = _to_float(data.get("forecast_confidence"), 0.0)
    reversal = str(data.get("reversal") or "NO_REVERSAL").upper()
    reversal_conf = _to_float(data.get("reversal_confidence"), 0.0)

    score = conf
    if "середина" in range_state or "middle" in range_state:
        score -= 12
    if ("ниж" in range_state or "low" in range_state) and "LONG" in signal:
        score += 6
    if ("верх" in range_state or "high" in range_state) and "SHORT" in signal:
        score += 6
    if "перевес" in ct_now:
        score += 5
    if reversal not in {"", "NO_REVERSAL", "NONE"} and reversal_conf >= 50:
        score -= 15

    score = max(0.0, min(100.0, score))

    direction = "NEUTRAL"
    if "LONG" in signal or "ЛОНГ" in signal:
        direction = "LONG"
    elif "SHORT" in signal or "ШОРТ" in signal:
        direction = "SHORT"

    if direction == "NEUTRAL":
        state = "IMPULSE_UNCERTAIN_NEUTRAL"
        can_enter = False
        comment = "Нет направленного импульса. Лучше ждать более чистую структуру."
    elif score >= 60:
        state = f"IMPULSE_CONTINUES_{direction}"
        can_enter = not ("середина" in range_state or "middle" in range_state)
        comment = "Импульс пока продолжается. Вход лучше искать по подтверждению, а не в случайной точке внутри диапазона."
    elif score >= 40:
        state = f"IMPULSE_UNCERTAIN_{direction}"
        can_enter = False
        comment = "Импульс уже не идеальный. Лучше дождаться подтверждения: удержания уровня, сильной свечи продолжения или обновления локального экстремума."
    else:
        state = f"IMPULSE_EXHAUSTING_{direction}"
        can_enter = False
        comment = "Импульс затухает. Входить прямо сейчас рискованно. Лучше ждать откат в сильную зону или новый импульсный запуск."

    if direction == "LONG":
        watch_conditions = [
            "удержание локальной поддержки",
            "сильная свеча продолжения вверх",
            "обновление локального high без резкого отката",
            "не терять поддержку после ретеста",
        ]
    elif direction == "SHORT":
        watch_conditions = [
            "удержание локального сопротивления",
            "сильная свеча продолжения вниз",
            "обновление локального low без сильного выкупа",
            "не возвращаться выше сопротивления после ретеста",
        ]
    else:
        watch_conditions = [
            "выход из локального сжатия",
            "явная направленная свеча",
            "закрепление над или под важной зоной",
        ]

    return {
        "state": state,
        "score": round(score, 1),
        "direction": direction,
        "can_enter": can_enter,
        "comment": comment,
        "watch_conditions": watch_conditions,
    }
