from __future__ import annotations


def _layer_line(row):
    mark = '✅' if row.get('active') else '❌'
    return f"  → сетка {row['layer']} ({row['threshold_pct']}%): {mark}"



def render_grid_view(s):
    g = s.get('grid_context') or {}
    gin = s['ginarea']
    bias = g.get('bias', s.get('consensus_direction', 'NONE'))
    priority_side = g.get('priority_side', 'NEUTRAL')
    lines = [
        "GRID VIEW",
        f"STATUS: {g.get('status', s.get('state', 'MID_RANGE'))}",
        f"BIAS: {bias} (среднесрочный)" if bias in {'LONG', 'SHORT'} else f"BIAS: {bias}",
        f"PRIORITY SIDE: {priority_side}",
    ]
    if priority_side == 'NEUTRAL' and bias in {'LONG', 'SHORT'}:
        lines.append("⚠️ локально нейтрально — сетки обе рабочие")
    lines.extend([
        "",
        f"DOWN IMPULSE: {g.get('down_impulse_pct', 0.0)}% → LIQUIDITY BELOW: {g.get('liquidity_below', 'NONE')}",
    ])
    for row in g.get('down_layers', []):
        lines.append(_layer_line(row))
    lines.extend([
        "",
        f"UP IMPULSE: {g.get('up_impulse_pct', 0.0)}% → LIQUIDITY ABOVE: {g.get('liquidity_above', 'NONE')}",
    ])
    for row in g.get('up_layers', []):
        lines.append(_layer_line(row))

    lines.extend([
        "",
        "GINAREA:",
        f"• LONG GRID: {gin['long_grid']}",
        f"• SHORT GRID: {gin['short_grid']}",
        f"• AGGRESSION: {gin['aggression']}",
        f"• LIFECYCLE: {gin['lifecycle']}",
    ])
    return "\n".join(lines)
