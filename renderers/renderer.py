def _arrow(side: str) -> str:
    return "↘" if side == "SHORT" else "↗"

def _block_name(block: str) -> str:
    return "SHORT BLOCK" if block == "SHORT" else "LONG BLOCK"

def render(s):
    return f"""⚡ BTC [{s['tf']} | {s['timestamp']}]

СТАТУС: {s['state']}
АКТИВНЫЙ БЛОК: {_block_name(s['active_block'])}
СТОРОНА: {s['side']} | ГЛУБИНА В БЛОКЕ: {s['block_depth_pct']}% [{s['depth_label']}]

ПОЗИЦИЯ В ДИАПАЗОНЕ: {s['range_position_pct']}%
ДО АКТИВНОГО КРАЯ: {s['distance_to_active_edge']}$ 
ДО ВЕРХНЕГО КРАЯ: {s['distance_to_upper_edge']}$ 
ДО НИЖНЕГО КРАЯ: {s['distance_to_lower_edge']}$

КОНСЕНСУС: {_arrow(s['consensus_direction'])} {s['consensus_direction']} | {s['consensus_confidence']} ({s['consensus_votes']})

HEDGE: ARM UP {s['hedge_arm_up']} | ARM DOWN {s['hedge_arm_down']}
"""
