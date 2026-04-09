def _arrow(side: str) -> str:
    if side == "SHORT":
        return "↘"
    if side == "LONG":
        return "↗"
    return "↔"


def _block_name(block: str) -> str:
    return "SHORT BLOCK" if block == "SHORT" else "LONG BLOCK"


def _render_warning_block(s):
    primary = s.get("primary_warning")
    secondary = s.get("secondary_warnings") or []
    context = s.get("context_warnings") or []
    if not primary and not secondary and not context:
        return []
    lines = ["", "⚠️ ПРЕДУПРЕЖДЕНИЯ:"]
    if primary:
        title = f"БЛОКИРОВКА: {primary}" if s.get("trigger_blocked") else primary
        lines.append(title)
    for w in secondary:
        lines.append(f"   • {w}" if primary else f"• {w}")
    for w in context:
        lines.append(f"   • {w}" if primary else f"• {w}")
    return lines


def _render_entry_block(s):
    lines = [
        "",
        "ENTRY:",
        f"• QUALITY: {s.get('entry_quality', 'NO_TRADE')} | {s.get('entry_quality_reason', '')}",
        f"• PROFILE: {s.get('execution_profile', 'NO_ENTRY')} | {s.get('execution_profile_reason', '')}",
        f"• RISK MODE: {s.get('entry_risk_mode', 'MINIMAL')}",
        f"• PARTIAL ENTRY: {'YES' if s.get('partial_entry_allowed') else 'NO'}" + (f" ({s.get('partial_entry_size')})" if s.get('partial_entry_allowed') and s.get('partial_entry_size') else ""),
        f"• SCALE-IN: {'YES' if s.get('scale_in_allowed') else 'NO'}",
    ]
    return lines


def _render_trade_plan(s):
    plan = s.get("trade_plan")
    if not isinstance(plan, dict):
        return []
    lines = ["", "TRADE PLAN:"]
    if plan.get("mode") == "GRID":
        lines.extend([
            f"• MODE: GRID",
            f"• ENTRY ZONE: {plan.get('entry_zone_low')} – {plan.get('entry_zone_high')}",
            f"• ENTRY TYPE: {plan.get('entry_type')}",
            f"• INVALIDATION: {plan.get('invalidation_level')}",
            f"• PROFIT TARGET $: {plan.get('profit_target_usd')}",
            f"• REDUCE TRIGGER: {plan.get('reduce_trigger')}",
            f"• CLOSE TRIGGER: {plan.get('grid_close_trigger')}",
            f"• LIFECYCLE: {plan.get('lifecycle_mode')}",
            f"• SUMMARY: {plan.get('summary')}",
        ])
        return lines

    lines.extend([
        f"• MODE: DIRECTIONAL",
        f"• ENTRY TYPE: {plan.get('entry_type')}",
        f"• ENTRY ZONE: {plan.get('entry_zone_low')} – {plan.get('entry_zone_high')}",
        f"• COMMENT: {plan.get('entry_comment')}",
        f"• TP1: {plan.get('tp1_price')}",
        f"• TP2: {plan.get('tp2_price')}",
        f"• STOP: {plan.get('sl_price')} (buffer {plan.get('sl_buffer')})",
        f"• INVALIDATION: {plan.get('invalidation_type')}",
        f"• BE AFTER: {plan.get('be_trigger_r')}R",
        f"• MANAGEMENT: {plan.get('management_mode')}",
        f"• SUMMARY: {plan.get('trade_plan_summary')}",
    ])
    return lines


def render_full_report(s):
    fc = s["forecast"]
    gin = s["ginarea"]
    entry_line = s["entry_type"] if s["entry_type"] else "NONE"
    trigger_text = s["trigger_type"] if s["trigger_type"] else "NONE"
    if s.get("trigger_blocked") and trigger_text != "NONE":
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
    if s.get("trigger_blocked"):
        lines.append(f"ПРИЧИНА БЛОКИРОВКИ: {s.get('trigger_block_reason_text')}")

    lines.extend([
        "",
        f"ACTION: {s['action']} | ENTRY: {entry_line}",
        f"CONTEXT: {s.get('trigger_context_label', 'NO CONTEXT')} ({s.get('trigger_context_score', 0)}/3)" + (" ⚠️" if s.get('trigger_context_score') == 1 else ""),
        f"КОНСЕНСУС: {_arrow(s['consensus_direction'])} {s['consensus_direction']} | {s['execution_confidence']} ({s['consensus_votes']})",
    ])

    lines.extend(_render_warning_block(s))

    lines.extend([
        "",
        "ПРОГНОЗ:",
        f"• СКАЛЬП: {_arrow(fc['short']['direction'])} {fc['short']['direction']} | {fc['short']['strength']} | {fc['short']['note']}",
        f"• СЕССИЯ: {_arrow(fc['session']['direction'])} {fc['session']['direction']} | {fc['session']['strength']} | {fc['session']['note']}",
        f"• СРЕДНЕСРОК: {_arrow(fc['medium']['direction'])} {fc['medium']['direction']} | {fc['medium']['strength']} | {fc['medium']['phase']} | {fc['medium']['note']}",
    ])

    lines.extend(_render_entry_block(s))
    lines.extend(_render_trade_plan(s))

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
