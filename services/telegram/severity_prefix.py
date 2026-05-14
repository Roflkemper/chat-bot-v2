"""Severity prefix для TG-сообщений.

Чтобы в общем потоке оператор мгновенно отличал критичное от рутинного,
каждое сообщение префиксуется одним из 4 маркеров:

  🔴 CRITICAL  — редкое, action-required (mega-spike, истощение 4+/6, conf>=80% setup)
  🟠 IMPORTANT — обычный alert/setup, action-recommended
  🟡 INFO      — P-15 lifecycle (OPEN/CLOSE), edge contextual
  ⚪ ROUTINE   — layer/harvest/level_break (sent в отдельный канал, prefix
                опционален т.к. канал уже отделён)

Использование:
    from services.telegram.severity_prefix import classify_severity, with_prefix
    sev = classify_severity(emitter="LIQ_CASCADE", text=text, meta={"qty_btc": 13.5})
    text = with_prefix(sev, text)

Правила классификации:
  CRITICAL:
    - LIQ_CASCADE с qty_btc >= 10 (мега-спайк) или title содержит "МЕГА"
    - GRID_EXHAUSTION с signals_count >= 4
    - SETUP_ON / SETUP_OFF с conf >= 80
    - PNL_EXTREME, MARGIN_ALERT, BOUNDARY_BREACH — всегда critical
  IMPORTANT:
    - Остальные SETUP_ON/SETUP_OFF/PNL_EVENT/GRID_EXHAUSTION/LIQ_CASCADE
  INFO:
    - P15_OPEN / P15_CLOSE
    - REGIME_CHANGE, PARAM_CHANGE, BOT_STATE_CHANGE
  ROUTINE:
    - P15_REENTRY / P15_HARVEST / LEVEL_BREAK / PAPER_TRADE
"""
from __future__ import annotations

from typing import Any

CRITICAL = "CRITICAL"
IMPORTANT = "IMPORTANT"
INFO = "INFO"
ROUTINE = "ROUTINE"

_PREFIX = {
    CRITICAL: "🔴",
    IMPORTANT: "🟠",
    INFO: "🟡",
    ROUTINE: "⚪",
}

# Emitters that are ALWAYS critical regardless of meta
_ALWAYS_CRITICAL: set[str] = {
    "PNL_EXTREME",
    "MARGIN_ALERT",
    "BOUNDARY_BREACH",
    "ENGINE_ALERT",
}

# Emitters that get INFO level by default
_INFO_EMITTERS: set[str] = {
    "P15_OPEN", "P15_CLOSE",
    "REGIME_CHANGE", "PARAM_CHANGE", "BOT_STATE_CHANGE",
    "POSITION_CHANGE",
}

# Emitters that are routine noise
_ROUTINE_EMITTERS: set[str] = {
    "P15_REENTRY", "P15_HARVEST", "LEVEL_BREAK", "PAPER_TRADE",
    "RSI_EXTREME", "AUTO_EDGE_ALERT", "SETUP_DETECTOR_DEEP",
}


def classify_severity(emitter: str, text: str = "", meta: dict[str, Any] | None = None) -> str:
    """Pick severity for an outgoing TG message."""
    meta = meta or {}

    if emitter in _ALWAYS_CRITICAL:
        return CRITICAL

    # Mega liquidation cascade — qty_btc >= 10 OR title mentions МЕГА
    if emitter == "LIQ_CASCADE":
        qty = meta.get("qty_btc")
        if isinstance(qty, (int, float)) and qty >= 10.0:
            return CRITICAL
        if "МЕГА" in text or "MEGA" in text.upper():
            return CRITICAL
        return IMPORTANT

    # Grid exhaustion — critical only when 4+ из 6 сигналов
    if emitter == "GRID_EXHAUSTION":
        n = meta.get("signals_count")
        if isinstance(n, (int, float)) and n >= 4:
            return CRITICAL
        return IMPORTANT

    # Setup detector — critical when confidence is high
    if emitter in {"SETUP_ON", "SETUP_OFF"}:
        conf = meta.get("confidence")
        if isinstance(conf, (int, float)) and conf >= 80.0:
            return CRITICAL
        return IMPORTANT

    if emitter in _INFO_EMITTERS:
        return INFO

    if emitter in _ROUTINE_EMITTERS:
        return ROUTINE

    # Unknown — default IMPORTANT (fail-safe: визуально заметно но не шокирует)
    return IMPORTANT


def prefix_for(severity: str) -> str:
    return _PREFIX.get(severity, "")


def with_prefix(severity: str, text: str) -> str:
    """Prepend severity emoji to text. Idempotent — если префикс уже есть, не дублирует."""
    p = prefix_for(severity)
    if not p:
        return text
    if text.startswith(p):
        return text
    return f"{p} {text}"
