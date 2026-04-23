from __future__ import annotations

from typing import Any

from core.orchestrator.visuals import separator


def render_killswitch_alert(reason: str, reason_value: Any) -> str:
    labels = {
        "MARGIN_DRAWDOWN": "ПРОСАДКА МАРЖИ",
        "LIQUIDATION_CASCADE": "КАСКАД ЛИКВИДАЦИЙ",
        "FLASH_MOVE": "АНОМАЛЬНОЕ ДВИЖЕНИЕ",
        "MANUAL": "РУЧНАЯ ОСТАНОВКА",
    }
    lines = ["🚨 KILLSWITCH АКТИВИРОВАН", "", f"Причина: {labels.get(reason, reason)}"]
    if reason == "MARGIN_DRAWDOWN":
        lines.append(f"Просадка: -{float(reason_value):.2f}%")
    elif reason == "LIQUIDATION_CASCADE":
        lines.append(f"Режим: {reason_value}")
    elif reason == "FLASH_MOVE":
        lines.append(f"Движение: ±{float(reason_value):.2f}% за 1 мин")
    else:
        lines.append(f"Значение: {reason_value}")
    lines.extend(["", "Все боты остановлены.", separator(28)])
    return "\n".join(lines)
