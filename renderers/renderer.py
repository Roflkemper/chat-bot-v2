def _arrow(side: str) -> str:
    if side == "SHORT":
        return "↘"
    if side == "LONG":
        return "↗"
    return "↔"

def _block_name(block: str) -> str:
    return "SHORT BLOCK" if block == "SHORT" else "LONG BLOCK"

def render_full_report(s):
    fc = s["forecast"]
    gin = s["ginarea"]
    entry_line = s["entry_type"] if s["entry_type"] else "NONE"
    trigger_text = s["trigger_type"] if s["trigger_type"] else "NONE"

    lines = [
        f"⚡ {s['symbol']} [{s['tf']} | {s['timestamp']}]",
        "",
        f"СТАТУС: {s['state']}",
        f"АКТИВНЫЙ БЛОК: {_block_name(s['active_block'])}",
        f"СТОРОНА: {s['execution_side']} | ГЛУБИНА В БЛОКЕ: {s['block_depth_pct']}% [{s['depth_label']}]",
        "",
        f"ПОЗИЦИЯ В ДИАПАЗОНЕ: {s['range_position_pct']}%",
    ]

    if s["active_block"] == "SHORT":
        lines.append(f"ДО ВЕРХНЕГО КРАЯ: {s['distance_to_upper_edge']}$ ({s['edge_distance_pct']}% блока)")
        lines.append(f"ДО НИЖНЕГО КРАЯ: {s['distance_to_lower_edge']}$")
    else:
        lines.append(f"ДО НИЖНЕГО КРАЯ: {s['distance_to_lower_edge']}$ ({s['edge_distance_pct']}% блока)")
        lines.append(f"ДО ВЕРХНЕГО КРАЯ: {s['distance_to_upper_edge']}$")

    lines.extend([
        "",
        f"TRIGGER: {trigger_text}",
        f"ПРИЧИНА: {s['trigger_note']}",
        "",
        f"ACTION: {s['action']} | ENTRY: {entry_line}",
        f"КОНСЕНСУС: {_arrow(s['consensus_direction'])} {s['consensus_direction']} | {s['execution_confidence']} ({s['consensus_votes']})",
    ])

    if s["warnings"]:
        lines.append("")
        lines.append("⚠️ ПРЕДУПРЕЖДЕНИЯ:")
        for w in s["warnings"]:
            lines.append(f"• {w}")

    lines.extend([
        "",
        "ПРОГНОЗ:",
        f"• СКАЛЬП: {_arrow(fc['short']['direction'])} {fc['short']['direction']} | {fc['short']['strength']} | {fc['short']['note']}",
        f"• СЕССИЯ: {_arrow(fc['session']['direction'])} {fc['session']['direction']} | {fc['session']['strength']} | {fc['session']['note']}",
        f"• СРЕДНЕСРОК: {_arrow(fc['medium']['direction'])} {fc['medium']['direction']} | {fc['medium']['strength']} | {fc['medium']['phase']} | {fc['medium']['note']}",
        "",
        "GINAREA:",
        f"• LONG GRID: {gin['long_grid']}",
        f"• SHORT GRID: {gin['short_grid']}",
        f"• AGGRESSION: {gin['aggression']}",
        f"• LIFECYCLE: {gin['lifecycle']}",
        "",
        "HEDGE:",
        f"• STATE: {s['hedge_state']}",
        f"• ARM UP: {s['hedge_arm_up']}",
        f"• ARM DOWN: {s['hedge_arm_down']}",
    ])
    return "\n".join(lines)
