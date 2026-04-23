from __future__ import annotations

from typing import Any, Dict, Optional


def _fmt_money(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    value = float(value)
    if abs(value) >= 1000:
        return f"{value/1000:.2f}k$"
    return f"{value:.0f}$"


def _fmt_pct(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.0f}%"


def render_compact_execution(snapshot: Dict[str, Any], symbol: str = "BTC", tf: str = "1h", updated_at: str = "") -> str:
    state = snapshot.get("state", "MID_RANGE")
    action = snapshot.get("action") or snapshot.get("execution_action") or "WAIT"
    side = snapshot.get("active_block_side") or snapshot.get("side") or "NONE"
    consensus = snapshot.get("consensus_label") or "NONE"
    depth = snapshot.get("block_depth_pct")
    active_edge = snapshot.get("distance_to_active_edge")
    upper_edge = snapshot.get("distance_to_upper_edge")
    lower_edge = snapshot.get("distance_to_lower_edge")
    overrun = bool(snapshot.get("overrun_flag"))
    invalidation = snapshot.get("invalidation") or "n/a"
    trigger = snapshot.get("trigger") or "n/a"
    hedge_arm_up = snapshot.get("hedge_arm_up")
    hedge_arm_down = snapshot.get("hedge_arm_down")

    near_edge = False
    if active_edge is not None:
        ref_price = snapshot.get("price")
        try:
            near_edge = float(active_edge) / max(float(ref_price), 1.0) < 0.005
        except Exception:
            near_edge = False

    head = f"⚡ {symbol} [{tf}"
    if updated_at:
        head += f" | {updated_at}"
    head += "]"
    if near_edge:
        head = "⚠️ " + head

    lines = [
        head,
        "",
        f"СТАТУС: {state}",
        f"ДЕЙСТВИЕ: {action}",
        f"ЗОНА: {side}",
        f"ГЛУБИНА В БЛОКЕ: {_fmt_pct(depth)}" + (" ⚠️ риск прошивки" if depth is not None and float(depth) >= 50 else ""),
        f"ДО АКТИВНОГО КРАЯ: {_fmt_money(active_edge)}",
        f"ДО ВЕРХНЕГО КРАЯ: {_fmt_money(upper_edge)}",
        f"ДО НИЖНЕГО КРАЯ: {_fmt_money(lower_edge)}",
        f"КОНСЕНСУС: {consensus}",
        f"ТРИГГЕР: {trigger}",
        f"ОТМЕНА: {invalidation}",
        "HEDGE:",
        f"ARM UP: {_fmt_money(hedge_arm_up)}",
        f"ARM DOWN: {_fmt_money(hedge_arm_down)}",
    ]

    if overrun:
        lines.insert(4, "OVERRUN: да — вход блокировать")

    if snapshot.get("pattern_visible") is False:
        lines.append("ПАТТЕРН: скрыт — шум ниже порога")

    return "\n".join(lines)
