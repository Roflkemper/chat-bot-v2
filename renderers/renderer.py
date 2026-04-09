def _arrow(side: str) -> str:
    if side == "SHORT":
        return "↘"
    if side == "LONG":
        return "↗"
    return "↔"


def _block_name(block: str) -> str:
    return "SHORT BLOCK" if block == "SHORT" else "LONG BLOCK"


def _yes_no(flag: bool) -> str:
    return "YES" if flag else "NO"


def render_full_report(s):
    fc = s["forecast"]
    gin = s["ginarea"]
    trigger_text = s["trigger_type"] if s["trigger_type"] else "NONE"
    if s.get("trigger_blocked") and trigger_text != "NONE":
        trigger_text = f"{trigger_text} ⚠️ ЗАБЛОКИРОВАН"
    entry_line = s["entry_type"] if s["entry_type"] else "NONE"

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
    if s.get("trigger_block_reason_text"):
        lines.append(f"ПРИЧИНА БЛОКИРОВКИ: {s['trigger_block_reason_text']}")

    lines.extend([
        "",
        f"ACTION: {s['action']} | ENTRY: {entry_line}",
        f"CONTEXT: {s['context_label']} ({s['context_score']}/3)",
        (f"КОНСЕНСУС: CONFLICTED ({s['consensus_votes']}/3)" if s.get('consensus_votes', 0) == 0 or s.get('consensus_direction') in {'NONE', 'CONFLICT'} else f"КОНСЕНСУС: {_arrow(s['consensus_direction'])} {s['consensus_direction']} | {s['execution_confidence']} ({s['consensus_votes']}/3)"),
    ])

    if s.get("block_flip_warning"):
        lines.append(f"⚠️ {s.get('active_block')} BLOCK под давлением — возможна смена активной зоны")

    if s.get("primary_blocker") or s.get("secondary_factors") or s.get("context_risks"):
        lines.append("")
        lines.append("⚠️ ПРЕДУПРЕЖДЕНИЯ:")
        if s.get("primary_blocker"):
            lines.append(f"БЛОКИРОВКА: {s['primary_blocker']}")
        for w in s.get("secondary_factors") or []:
            lines.append(f"   • {w}")
        for w in s.get("context_risks") or []:
            lines.append(f"   • {w}")

    lines.extend([
        "",
        "ПРОГНОЗ:",
        f"• СКАЛЬП: {_arrow(fc['short']['direction'])} {fc['short']['direction']} | {fc['short']['strength']} | {fc['short']['note']}",
        f"• СЕССИЯ: {_arrow(fc['session']['direction'])} {fc['session']['direction']} | {fc['session']['strength']} | {fc['session']['note']}",
        f"• СРЕДНЕСРОК: {_arrow(fc['medium']['direction'])} {fc['medium']['direction']} | {fc['medium']['strength']} | {fc['medium']['phase']} | {fc['medium']['note']}",
        "",
        "ENTRY:",
        f"• QUALITY: {s['entry_quality']}",
        f"• PROFILE: {s['execution_profile']}",
        f"• RISK MODE: {s['entry_risk_mode']}",
        f"• PARTIAL ENTRY: {_yes_no(s['partial_entry_allowed'])}",
        f"• SCALE-IN: {_yes_no(s['scale_in_allowed'])}",
    ])

    fb = s.get("feedback") or {}
    lines.extend([
        "",
        "FEEDBACK:",
        f"• setup key: {s.get('setup_key', '-')}",
        f"• setup history: {fb.get('history', 'INSUFFICIENT DATA')}",
        f"• confidence: {fb.get('confidence', 'LOW')}",
    ])
    if fb.get("note"):
        lines.append(f"• note: {fb['note']}")

    plan = s.get("trade_plan") or {}
    lines.extend(["", "TRADE PLAN:"])
    if not s.get("trade_plan_active"):
        lines.extend([
            "• ⏸️ ОЖИДАНИЕ — план не активен",
            "• РЕЖИМ: GRID MONITORING" if gin.get('lifecycle') else "• РЕЖИМ: MONITORING",
        ])
    elif plan.get("mode") == "GRID":
        lines.extend([
            f"• MODE: GRID",
            f"• ENTRY ZONE: {plan.get('entry_zone_low')} – {plan.get('entry_zone_high')}",
            f"• PROFIT TARGET $: {plan.get('profit_target_usd')}",
            f"• INVALIDATION: {plan.get('invalidation_level')}",
            f"• REDUCE: {plan.get('reduce_trigger')}",
            f"• CLOSE: {plan.get('grid_close_trigger')}",
        ])
    else:
        lines.extend([
            f"• MODE: DIRECTIONAL",
            f"• ENTRY TYPE: {plan.get('entry_type')}",
            f"• ENTRY ZONE: {plan.get('entry_zone_low')} – {plan.get('entry_zone_high')}",
            f"• TP1: {plan.get('tp1_price')}",
            f"• TP2: {plan.get('tp2_price')}",
            f"• SL: {plan.get('sl_price')}",
            f"• BE: {plan.get('be_trigger_r') if plan.get('be_trigger_r') is not None else 'NONE'}R",
            f"• INVALIDATION: {plan.get('invalidation_type')}",
        ])

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
