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
        "SOFT_BOOST": "soft boost / без агрессии",
        "ENABLE": "держать готовыми",
        "HOLD": "держать",
        "REDUCE": "не усиливать / сократить",
        "PAUSE": "пауза",
        "WORK": "работать",
    }
    return mapping.get(action, action)


def _render_grid_compat(s: dict) -> str:
    g = s.get('grid_context', {})
    lines = [
        f"⚡ {s['symbol']} [{s['tf']} | {s['timestamp']}]",
        "GRID VIEW",
        f"BIAS: {g.get('bias', 'NEUTRAL')} (среднесрочный)" if g.get('priority_side') == 'NEUTRAL' else f"BIAS: {g.get('bias', 'NEUTRAL')}",
        f"PRIORITY SIDE: {g.get('priority_side', 'NEUTRAL')}",
    ]
    if g.get('priority_side') == 'NEUTRAL':
        lines.append('⚠️ локально нейтрально — сетки обе рабочие')
    for side in ('down', 'up'):
        for layer in g.get(f'{side}_layers', []):
            mark = '✅' if layer.get('active') else '❌'
            lines.append(f"→ сетка {layer.get('layer')} ({layer.get('threshold_pct')}%): {mark}")
    return "\n".join(lines)


def _derive_execution_summary(s: dict) -> tuple[list[str], list[str], list[str]]:
    current_lines = list(s.get('current_action_lines') or [])
    manual_lines = list(s.get('manual_action_lines') or [])
    bot_lines = list(s.get('grid_action_lines') or s.get('bot_action_lines') or [])
    risk_lines = list((s.get('risk_authority') or {}).get('lines') or [])

    merged = []
    seen = set()
    for group in (current_lines, manual_lines):
        for line in group:
            normalized = str(line).replace('• действие:', '• руками:').strip()
            if normalized not in seen:
                seen.add(normalized)
                merged.append(normalized)

    bot_title = []
    if bot_lines:
        bot_title = ['• СЕТКИ:'] + bot_lines

    trigger_wait = []

    if risk_lines:
        filtered_risk = []
        for line in risk_lines:
            if line not in filtered_risk:
                filtered_risk.append(line)
    else:
        filtered_risk = []

    return merged, bot_title, trigger_wait + filtered_risk


def render_full_report(s, mode=None):
    if mode == "GRID" and s.get('grid_context'):
        return _render_grid_compat(s)

    fc = s["forecast"]
    ga = s.get("grid_action", {})
    entry_line = s["entry_type"] if s.get("entry_type") else "NONE"
    trigger_text = s.get("trigger_type") if s.get("trigger_type") else "NONE"
    if s.get('trigger_blocked') and trigger_text != 'NONE':
        trigger_text = f"{trigger_text} ⚠️ ЗАБЛОКИРОВАН"

    top_signal = s.get('top_signal') or f"⏸️ {s.get('action', 'WAIT')}"
    exec_lines, bot_control_lines, execution_meta_lines = _derive_execution_summary(s)

    lines = [
        f"⚡ {s['symbol']} [{s['tf']} | {s['timestamp']}]",
        "━━━━━━━━━━━━━━━━━━━━",
        top_signal,
        "━━━━━━━━━━━━━━━━━━━━",
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
    lines.extend(["", f"TRIGGER: {trigger_text}", f"ПРИЧИНА: {s['trigger_note']}"])
    if s.get('trigger_block_reason'):
        lines.append(f"ПРИЧИНА БЛОКИРОВКИ: {s['trigger_block_reason']}")
    lines.extend(["", f"ACTION: {s['action']} | ENTRY: {entry_line}", f"CONTEXT: {s.get('context_label', 'NO CONTEXT')} ({s.get('context_score', 0)}/3)"])
    cdir = s['consensus_direction']
    if cdir in {'LONG', 'SHORT'}:
        lines.append(f"КОНСЕНСУС: {_arrow(cdir)} {cdir} | {s['consensus_confidence']} ({s['consensus_votes']})")
    else:
        lines.append(f"КОНСЕНСУС: CONFLICTED ({s['consensus_votes']})")
    bias_score = s.get('bias_score')
    if bias_score is not None:
        lines.append(f"BIAS SCORE: {bias_score:+d} | {s.get('bias_label', 'конфликтный рынок')}")
    absorption = s.get('absorption', {})
    if absorption:
        lines.append(f"ABSORPTION: {absorption.get('label', 'нет данных')} | {absorption.get('bars_at_edge', 0)} баров у края")
    vol = s.get('volatility') or {}
    if vol:
        lines.append(f"VOLATILITY: {vol.get('state', 'NORMAL')} | ATR x{float(vol.get('atr_ratio', 1.0)):.2f}")

    if s.get("warnings"):
        lines.extend(["", "⚠️ ПРЕДУПРЕЖДЕНИЯ:"] )
        lines.extend(s.get('warnings') or [])

    lines.extend(["", "ПРОГНОЗ:",
        f"• СКАЛЬП: {_arrow(fc['short']['direction'])} {fc['short']['direction']} | {fc['short'].get('strength', fc['short'].get('confidence', 'LOW'))} | {fc['short'].get('note', 'n/a')}",
        f"• СЕССИЯ: {_arrow(fc['session']['direction'])} {fc['session']['direction']} | {fc['session'].get('strength', fc['session'].get('confidence', 'LOW'))} | {fc['session'].get('note', 'n/a')}",
        f"• СРЕДНЕСРОК: {_arrow(fc['medium']['direction'])} {fc['medium']['direction']} | {fc['medium'].get('strength', fc['medium'].get('confidence', 'LOW'))} | {fc['medium'].get('phase', 'RANGE')} | {fc['medium'].get('note', 'n/a')}"])

    if s.get('action') != 'WAIT':
        lines.extend(["", "ENTRY:", f"• QUALITY: {s.get('entry_quality', 'NO_TRADE')}", f"• PROFILE: {s.get('execution_profile', 'NO_ENTRY')}", f"• RISK MODE: {s.get('risk_mode', 'MINIMAL')}"])

    lines.extend(["", "⚡ ИСПОЛНЕНИЕ СЕЙЧАС:"])
    lines.extend(exec_lines)
    if bot_control_lines:
        lines.extend(bot_control_lines)
    if execution_meta_lines:
        lines.extend(execution_meta_lines)

    position_control = s.get('position_control') or {}
    position_status = str(position_control.get('status') or '').upper()
    has_real_position = bool(position_status and position_status != 'FLAT')
    if has_real_position:
        lines.extend(["", "POSITION CONTROL:"])
        lines.append(f"• STATUS: {position_control.get('status')}")
        lines.append(f"• SOURCE: {position_control.get('source', 'state')}")
        if position_control.get('entry_price') is not None:
            lines.append(f"• ENTRY PRICE: {position_control.get('entry_price')}")
        lines.append(f"• PNL: {position_control.get('pnl_pct', 0.0)}%")
        lines.append(f"• ACTION: {position_control.get('recommended_action', 'HOLD')}")

    plan = s.get('if_then_plan') or []
    if plan:
        lines.extend(["", "ПЛАН ДЕЙСТВИЙ:"])
        lines.extend(plan)

    exit_strategy = s.get('exit_strategy_lines') or []
    if exit_strategy:
        lines.extend(["", "EXIT STRATEGY:"])
        lines.extend(exit_strategy)

    lines.extend(["", "TRADE PLAN:"])
    if s.get('trade_plan_active'):
        lines.append(f"• MODE: {s.get('trade_plan_mode', 'GRID')}")
    else:
        note = s.get('trade_plan_activation_note')
        if note:
            lines.append(f"• ⏸️ ОЖИДАНИЕ — {note}")
        else:
            lines.append("• ⏸️ ОЖИДАНИЕ — план не активен")
        lines.append(f"• РЕЖИМ: {s.get('trade_plan_mode', 'GRID MONITORING')}")
    trade_plan = s.get('trade_plan') or {}
    if trade_plan:
        for key in ('entry', 'add', 'tp1', 'tp2', 'invalidation'):
            if key in trade_plan and trade_plan.get(key) is not None:
                lines.append(f"• {key.upper()}: {trade_plan.get(key)}")

    lines.extend(["", "HEDGE:", f"• STATE: {s['hedge_state']}", f"• ARM UP: {s['hedge_arm_up']}", f"• ARM DOWN: {s['hedge_arm_down']}"])


    if s.get('grid_shift_lines'):
        lines.extend(["", "GRID SHIFT / AUTHORITY:"])
        lines.extend(s.get('grid_shift_lines') or [])
    if s.get('liquidity_void_lines'):
        lines.extend(["", "LIQUIDITY VOID / NEXT DESTINATION:"])
        lines.extend(s.get('liquidity_void_lines') or [])

    lines.extend(["", "────────────────────", "", "GRID VIEW", f"РЕЖИМ: {ga.get('grid_regime', 'SAFE')}", f"BIAS: {ga.get('bias_side', 'NEUTRAL')} (среднесрочно)", f"STRUCTURE: {ga.get('structural_side', s.get('structural_context', {}).get('bias', 'NEUTRAL'))}", f"PRIORITY: {ga.get('priority_side', 'NEUTRAL')}", "", "ЛИКВИДНОСТЬ:", f"↓ DOWN TARGET: {ga.get('down_target', 0.0)}", f"↑ UP TARGET:   {ga.get('up_target', 0.0)}", "", "ИМПУЛЬСЫ:", f"DOWN: {ga.get('down_impulse_pct', 0.0):.2f}% → {_layer_marks(int(ga.get('down_layers', 0)))}", f"UP:   {ga.get('up_impulse_pct', 0.0):.2f}% → {_layer_marks(int(ga.get('up_layers', 0)))}", "", "ДЕЙСТВИЕ:", f"LONG  — {_action_label(ga.get('long_action', 'HOLD'))}", f"SHORT — {_action_label(ga.get('short_action', 'HOLD'))}"])
    if ga.get('risk_lines'):
        lines.extend(["", "РИСК:"])
        lines.extend([f"• {x}" for x in ga['risk_lines']])
    if s.get('scenario_alt_probability') is not None:
        lines.extend(["", "SCENARIO ENGINE:", f"• Сценарий A ({s.get('scenario_alt_probability')}%): {s.get('scenario_alt_text', 'n/a')}", f"• Сценарий B ({s.get('scenario_base_probability')}%): {s.get('scenario_base_text', 'n/a')}"])
    if ga.get('review_level_up') is not None and ga.get('review_level_down') is not None:
        lines.extend(["", "ПЕРЕСМОТР:", f"выше {ga['review_level_up']}", f"ниже {ga['review_level_down']}"])
    return "\n".join(lines)
