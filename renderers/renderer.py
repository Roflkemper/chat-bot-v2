def _layer_marks(layers: int) -> str:
    l1 = "✅" if layers >= 1 else "❌"
    l2 = "✅" if layers >= 2 else "❌"
    l3 = "✅" if layers >= 3 else "❌"
    return f"сетка 1 {l1}  сетка 2 {l2}  сетка 3 {l3}"


def _arrow(side: str) -> str:
    if side == "SHORT":
        return "↘"
    if side == "LONG":
        return "↗"
    return "↔"


def _block_name(block: str) -> str:
    return "SHORT BLOCK" if block == "SHORT" else "LONG BLOCK"


def _action_label(action: str) -> str:
    mapping = {
        "BOOST": "приоритет / можно усиливать",
        "ENABLE": "держать готовыми",
        "HOLD": "держать",
        "REDUCE": "не усиливать / сократить",
        "PAUSE": "пауза",
    }
    return mapping.get(action, action)


def render_full_report(s):
    fc = s["forecast"]
    ga = s.get("grid_action", {})
    entry_line = s["entry_type"] if s["entry_type"] else "NONE"
    trigger_text = s["trigger_type"] if s["trigger_type"] else "NONE"
    if s.get('trigger_blocked') and trigger_text != 'NONE':
        trigger_text = f"{trigger_text} ⚠️ ЗАБЛОКИРОВАН"

    lines = [
        f"⚡ {s['symbol']} [{s['tf']} | {s['timestamp']}]",
        "",
        "TRADER VIEW",
        f"СТАТУС: {s['state']}",
        f"АКТИВНЫЙ БЛОК: {_block_name(s['active_block'])}",
        f"СТОРОНА: {s['execution_side']} | ГЛУБИНА В БЛОКЕ: {s['block_depth_pct']}% [{s['depth_label']}]",
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

    if s["warnings"]:
        lines.append("")
        lines.append("⚠️ ПРЕДУПРЕЖДЕНИЯ:")
        for w in s["warnings"]:
            lines.append(w)

    lines.extend([
        "",
        "ПРОГНОЗ:",
        f"• СКАЛЬП: {_arrow(fc['short']['direction'])} {fc['short']['direction']} | {fc['short']['strength']} | {fc['short']['note']}",
        f"• СЕССИЯ: {_arrow(fc['session']['direction'])} {fc['session']['direction']} | {fc['session']['strength']} | {fc['session']['note']}",
        f"• СРЕДНЕСРОК: {_arrow(fc['medium']['direction'])} {fc['medium']['direction']} | {fc['medium']['strength']} | {fc['medium']['phase']} | {fc['medium']['note']}",
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
        "HEDGE:",
        f"• STATE: {s['hedge_state']}",
        f"• ARM UP: {s['hedge_arm_up']}",
        f"• ARM DOWN: {s['hedge_arm_down']}",
        "",
        "────────────────────",
        "",
        "GRID VIEW",
        f"РЕЖИМ: {ga.get('grid_regime', 'SAFE')}",
        f"BIAS: {ga.get('bias_side', 'NEUTRAL')} (среднесрочно)",
        f"STRUCTURE: {ga.get('structural_side', 'NEUTRAL')}",
        f"PRIORITY: {ga.get('priority_side', 'NEUTRAL')}",
        "",
        "ЛИКВИДНОСТЬ:",
        f"↓ DOWN TARGET: {ga.get('down_target', 0.0)}",
        f"↑ UP TARGET:   {ga.get('up_target', 0.0)}",
        "",
        "ИМПУЛЬСЫ:",
        f"DOWN: {ga.get('down_impulse_pct', 0.0):.2f}% → {_layer_marks(int(ga.get('down_layers', 0)))}",
        f"UP:   {ga.get('up_impulse_pct', 0.0):.2f}% → {_layer_marks(int(ga.get('up_layers', 0)))}",
        "",
        "ДЕЙСТВИЕ:",
        f"LONG  — {_action_label(ga.get('long_action', 'HOLD'))}",
        f"SHORT — {_action_label(ga.get('short_action', 'HOLD'))}",
    ])

    if ga.get('risk_lines'):
        lines.extend(["", "РИСК:", f"{ga['risk_lines'][0]}"])
    if ga.get('review_level_up') is not None and ga.get('review_level_down') is not None:
        lines.extend(["", "ПЕРЕСМОТР:", f"выше {ga['review_level_up']}", f"ниже {ga['review_level_down']}"])
    return "\n".join(lines)
