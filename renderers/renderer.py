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
    structural = s.get('structural_context', {})
    grid = s.get('grid_context', {})

    entry_line = s["entry_type"] if s["entry_type"] else "NONE"
    trigger_text = s["trigger_type"] if s["trigger_type"] else "NONE"
    if s.get('trigger_blocked') and trigger_text != 'NONE':
        trigger_text = f"{trigger_text} ⚠️ ЗАБЛОКИРОВАН"

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
    ])
    if s.get('trigger_block_reason'):
        lines.append(f"ПРИЧИНА БЛОКИРОВКИ: {s['trigger_block_reason']}")
    lines.extend([
        "",
        f"ACTION: {s['action']} | ENTRY: {entry_line}",
        f"CONTEXT: {s.get('context_label', 'NO CONTEXT')} ({s.get('context_score', 0)}/3)",
    ])
    cdir = s['consensus_direction']
    if cdir in {'LONG', 'SHORT'}:
        lines.append(f"КОНСЕНСУС: {_arrow(cdir)} {cdir} | {s['consensus_confidence']} ({s['consensus_votes']})")
    else:
        lines.append(f"КОНСЕНСУС: CONFLICTED ({s['consensus_votes']})")

    if s.get('block_flip_warning'):
        lines.append(f"⚠️ {_block_name(s['active_block'])} под давлением — возможна смена активной зоны")
        lines.append(f"• инвалидация {_block_name(s['active_block'])}: {s['scenario_flip_trigger']}")

    if s["warnings"]:
        lines.append("")
        lines.append("⚠️ ПРЕДУПРЕЖДЕНИЯ:")
        for w in s["warnings"]:
            lines.append(w)

    if structural:
        lines.extend([
            "",
            "СТРУКТУРА 1H:",
            f"• BIAS: {_arrow(structural.get('bias', 'NEUTRAL'))} {structural.get('bias', 'NEUTRAL')} | {structural.get('strength', 'LOW')}",
            f"• PHASE: {structural.get('phase', 'BALANCE')}",
            f"• DETAIL: {structural.get('reason', 'нет данных')}",
        ])
        if structural.get('upper_cluster_level') is not None:
            lines.append(f"• UPPER SWEEP: {structural['upper_cluster_level']} | шипов: {structural.get('upper_rejections_count', 0)}")
        if structural.get('lower_cluster_level') is not None:
            lines.append(f"• LOWER SWEEP: {structural['lower_cluster_level']} | шипов: {structural.get('lower_rejections_count', 0)}")

    lines.extend([
        "",
        "ПРОГНОЗ:",
        f"• СКАЛЬП: {_arrow(fc['short']['direction'])} {fc['short']['direction']} | {fc['short']['strength']} | {fc['short']['note']}",
        f"• СЕССИЯ: {_arrow(fc['session']['direction'])} {fc['session']['direction']} | {fc['session']['strength']} | {fc['session']['note']}",
        f"• СРЕДНЕСРОК: {_arrow(fc['medium']['direction'])} {fc['medium']['direction']} | {fc['medium']['strength']} | {fc['medium']['phase']} | {fc['medium']['note']}",
    ])

    if s.get('scenario_base_probability') is not None:
        lines.extend([
            "",
            "СЦЕНАРИИ:",
            f"• БАЗОВЫЙ ({s['scenario_base_probability']}%): {s['scenario_base_text']}",
            f"• АЛЬТЕРНАТИВНЫЙ ({s['scenario_alt_probability']}%): {s['scenario_alt_text']}",
            "",
            "ТРИГГЕР СМЕНЫ СЦЕНАРИЯ:",
            f"• {s['scenario_flip_trigger']}",
        ])

    if s.get('watch_side') in {'LONG', 'SHORT'}:
        watch_side = s['watch_side']
        lines.extend([
            "",
            f"{watch_side} WATCH:",
            f"• {watch_side} пока не активен",
            f"• триггер внимания: {s['scenario_flip_trigger']}",
            f"• после подтверждения пробоя искать активацию {watch_side}-сценария",
        ])

    if s.get('flip_prep_status') and s.get('flip_prep_status') != 'IDLE':
        lines.extend([
            "",
            "FLIP PREP:",
            f"• статус: {s['flip_prep_status']}",
            f"• новое направление: {s['flip_prep_side']}",
            f"• уровень активации: {s['flip_prep_level']:.2f}" if s.get('flip_prep_level') is not None else "• уровень активации: нет данных",
            f"• прогресс: {s.get('flip_prep_progress_bars', 0)}/{s.get('flip_prep_confirm_bars_needed', 2)} баров",
        ])
        if s.get('candidate_status') == 'PREPARED':
            lines.append(f"• {s['flip_prep_side']} scenario prepared — при 3-м баре возможен полный block flip")

    if grid:
        lines.extend([
            "",
            "GRID CONTEXT:",
            f"• PRIORITY SIDE: {grid.get('priority_side', 'NONE')}",
            f"• DOWN IMPULSE: {grid.get('impulse_down_pct', 0)}% | GRID LAYERS: {grid.get('grid_trigger_down', 0)}",
            f"• UP IMPULSE: {grid.get('impulse_up_pct', 0)}% | GRID LAYERS: {grid.get('grid_trigger_up', 0)}",
        ])
        if grid.get('liquidity_below') is not None:
            lines.append(f"• LIQUIDITY BELOW: {grid['liquidity_below']}")
        if grid.get('liquidity_above') is not None:
            lines.append(f"• LIQUIDITY ABOVE: {grid['liquidity_above']}")

    lines.extend([
        "",
        "ENTRY:",
        f"• QUALITY: {s.get('entry_quality', 'NO_TRADE')}",
        f"• PROFILE: {s.get('execution_profile', 'NO_ENTRY')}",
        f"• RISK MODE: {s.get('risk_mode', 'MINIMAL')}",
        f"• PARTIAL ENTRY: {'YES' if s.get('partial_entry_allowed') else 'NO'}",
        f"• SCALE-IN: {'YES' if s.get('scale_in_allowed') else 'NO'}",
        "",
        "TRADE PLAN:",
    ])
    if s.get('trade_plan_active'):
        lines.append(f"• MODE: {s.get('trade_plan_mode', 'GRID')}")
    else:
        lines.append("• ⏸️ ОЖИДАНИЕ — план не активен")
        lines.append(f"• РЕЖИМ: {s.get('trade_plan_mode', 'GRID MONITORING')}")

    lines.extend([
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
