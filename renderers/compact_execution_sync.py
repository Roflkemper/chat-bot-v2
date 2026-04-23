from __future__ import annotations

from typing import Dict


def render_compact_execution_sync(snapshot: Dict[str, object], *, symbol: str = "BTC", tf: str = "1h", updated_at: str = "") -> str:
    metrics = snapshot.get("metrics", {}) if isinstance(snapshot.get("metrics"), dict) else {}
    header = f"⚡ {symbol} [{tf}"
    if updated_at:
        header += f" | {updated_at}"
    header += "]"

    lines = [header, ""]
    lines.append(f"СТАТУС: {snapshot.get('state', 'MID_RANGE')}")
    lines.append(f"ДЕЙСТВИЕ: ГОТОВИТЬ {snapshot.get('action_side', 'NEUTRAL')}")
    lines.append("")
    lines.append(f"ПОЗИЦИЯ В ДИАПАЗОНЕ: {metrics.get('range_position_pct', 0)}%")
    lines.append(f"АКТИВНАЯ ЗОНА: {metrics.get('active_side', 'NEUTRAL')} BLOCK")
    lines.append(f"ГЛУБИНА В БЛОКЕ: {metrics.get('block_depth_pct', 0)}%")
    near_edge = " ⚠️ БЛИЗКО К КРАЮ" if metrics.get("near_edge") else ""
    lines.append(f"ДО ВЕРХНЕГО КРАЯ: {metrics.get('distance_to_upper', 0)}${near_edge}")
    lines.append(f"ДО НИЖНЕГО КРАЯ: {metrics.get('distance_to_lower', 0)}$")
    lines.append("")
    lines.append(f"TRIGGER: {snapshot.get('trigger_text', '')}")
    lines.append(f"ОТМЕНА: {snapshot.get('invalidation_text', '')}")
    lines.append(f"HEDGE: {snapshot.get('hedge_arm_text', '')}")
    if snapshot.get("note"):
        lines.append(f"NOTE: {snapshot['note']}")
    return "\n".join(lines)
