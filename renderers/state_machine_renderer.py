from __future__ import annotations

from core.state_machine_depth import StateMachineResult, ExecutionState


STATE_LABELS = {
    ExecutionState.MID_RANGE: "MID_RANGE",
    ExecutionState.SEARCH_TRIGGER: "SEARCH_TRIGGER",
    ExecutionState.PRE_ACTIVATION: "PRE_ACTIVATION",
    ExecutionState.CONFIRMED: "CONFIRMED",
    ExecutionState.OVERRUN: "OVERRUN",
}


def render_compact_state_block(symbol: str, timeframe: str, price: float, result: StateMachineResult) -> str:
    edge_mark = "⚠️ БЛИЗКО К КРАЮ" if result.near_edge else ""
    side = result.active_side if result.active_side != "NONE" else "НЕТ"
    action = {
        ExecutionState.MID_RANGE: "ЖДАТЬ",
        ExecutionState.SEARCH_TRIGGER: f"ГОТОВИТЬ {side}",
        ExecutionState.PRE_ACTIVATION: f"ПАЛЕЦ НА КНОПКЕ: {side}",
        ExecutionState.CONFIRMED: f"ПОДТВЕРЖДЁННЫЙ {side}",
        ExecutionState.OVERRUN: "НЕ ВХОДИТЬ / ЖДАТЬ RESET",
    }[result.state]

    risk_text = {
        "EARLY": "только вошли в блок",
        "WORKING_ZONE": "рабочая зона",
        "RISK_OF_THROUGH": "риск прошивки",
        "OVERRUN": "глубокое проникновение / риск пробоя",
        "MID_RANGE": "середина диапазона",
    }.get(result.risk_label, result.risk_label)

    lines = [
        f"⚡ {symbol} [{timeframe}]",
        "",
        f"СТАТУС: {STATE_LABELS[result.state]} {edge_mark}".rstrip(),
        f"ДЕЙСТВИЕ: {action}",
        f"ЦЕНА: {price:,.2f}",
    ]

    if result.active_side != "NONE":
        lines.extend([
            f"ЗОНА: {result.active_side} BLOCK {result.active_block_low:,.2f}–{result.active_block_high:,.2f}",
            f"ГЛУБИНА В БЛОКЕ: {result.depth_pct:.2f}% | {risk_text}",
            f"ДО АКТИВНОГО КРАЯ: {result.distance_to_active_edge:,.2f}$",
        ])
    else:
        lines.append("ЗОНА: вне активного блока")

    lines.extend([
        f"ДО ВЕРХНЕГО КРАЯ: {result.distance_to_upper_edge:,.2f}$",
        f"ДО НИЖНЕГО КРАЯ: {result.distance_to_lower_edge:,.2f}$",
        f"CONFIDENCE PENALTY: -{result.confidence_penalty}" if result.confidence_penalty else "CONFIDENCE PENALTY: 0",
        "ВХОД БЛОКИРОВАН" if result.entry_blocked else "ВХОД НЕ БЛОКИРОВАН",
    ])

    return "\n".join(lines)
