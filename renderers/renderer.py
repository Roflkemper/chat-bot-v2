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

    return f"""⚡ {s['symbol']} [{s['tf']} | {s['timestamp']}]

СТАТУС: {s['state']}
АКТИВНЫЙ БЛОК: {_block_name(s['active_block'])}
СТОРОНА: {s['execution_side']} | ГЛУБИНА В БЛОКЕ: {s['block_depth_pct']}% [{s['depth_label']}]

ПОЗИЦИЯ В ДИАПАЗОНЕ: {s['range_position_pct']}%
ДО АКТИВНОГО КРАЯ: {s['distance_to_active_edge']}$ ({s['active_edge_distance_pct']}% блока)
ДО ВЕРХНЕГО КРАЯ: {s['distance_to_upper_edge']}$
ДО НИЖНЕГО КРАЯ: {s['distance_to_lower_edge']}$

TRIGGER: {trigger_text}
ПРИЧИНА: {s['trigger_note']}

ACTION: {s['action']} | ENTRY: {entry_line}
КОНСЕНСУС: {_arrow(s['consensus_direction'])} {s['consensus_direction']} | {s['execution_confidence']} ({s['consensus_votes']})

ПРОГНОЗ:
• СКАЛЬП: {_arrow(fc['short']['direction'])} {fc['short']['direction']} | {fc['short']['strength']} | {fc['short']['note']}
• СЕССИЯ: {_arrow(fc['session']['direction'])} {fc['session']['direction']} | {fc['session']['strength']} | {fc['session']['note']}
• СРЕДНЕСРОК: {_arrow(fc['medium']['direction'])} {fc['medium']['direction']} | {fc['medium']['strength']} | {fc['medium']['phase']} | {fc['medium']['note']}

GINAREA:
• LONG GRID: {gin['long_grid']}
• SHORT GRID: {gin['short_grid']}
• AGGRESSION: {gin['aggression']}
• LIFECYCLE: {gin['lifecycle']}

HEDGE:
• STATE: {s['hedge_state']}
• ARM UP: {s['hedge_arm_up']}
• ARM DOWN: {s['hedge_arm_down']}
"""
