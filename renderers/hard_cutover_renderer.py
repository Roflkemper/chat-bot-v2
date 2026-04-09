from __future__ import annotations

from typing import Dict, Optional


def _fmt_money(v: Optional[float]) -> str:
    if v is None:
        return 'n/a'
    return f'{v:,.2f}'.replace(',', ' ')


def _fmt_pct(v: Optional[float]) -> str:
    if v is None:
        return 'n/a'
    return f'{v:.0f}%'


def render_hard_cutover(snapshot: Dict) -> str:
    symbol = snapshot.get('symbol', 'BTC')
    timeframe = snapshot.get('timeframe', '1h')
    state = snapshot.get('state', 'MID_RANGE')
    side = snapshot.get('side', 'NONE')
    active_block = snapshot.get('active_block', 'NONE')
    action = {
        'SEARCH_TRIGGER': f'ГОТОВИТЬ {side}'.strip(),
        'OVERRUN': 'НЕ ВХОДИТЬ / ЖДАТЬ RESET',
        'MID_RANGE': 'ЖДАТЬ КРАЙ',
    }.get(state, 'ЖДАТЬ')
    lines = [
        f'⚡ {symbol} [{timeframe}]',
        '',
        f'СТАТУС: {state}',
        f'ДЕЙСТВИЕ: {action}',
        f'ЗОНА: {active_block}',
        f'ГЛУБИНА В БЛОКЕ: {_fmt_pct(snapshot.get("block_depth_pct"))}',
        f'ДО АКТИВНОГО КРАЯ: {_fmt_money(snapshot.get("distance_to_active_edge"))}$',
        f'ДО ВЕРХНЕГО КРАЯ: {_fmt_money(snapshot.get("distance_to_upper_edge"))}$',
        f'ДО НИЖНЕГО КРАЯ: {_fmt_money(snapshot.get("distance_to_lower_edge"))}$',
        f'КОНСЕНСУС: {snapshot.get("consensus_direction", "NONE")} | {snapshot.get("consensus_confidence", "NONE")}',
    ]
    if snapshot.get('pattern_visible'):
        lines.append(
            f'ПАТТЕРН: {snapshot.get("pattern_label", "NONE")} | avg {snapshot.get("pattern_avg_move_pct", 0):.2f}%'
        )
    lines.extend([
        f'ТРИГГЕР: {snapshot.get("trigger", "n/a")}',
        f'ОТМЕНА: {snapshot.get("invalidation", "n/a")}',
    ])
    if snapshot.get('hedge_arm_up') is not None or snapshot.get('hedge_arm_down') is not None:
        lines.append(
            f'HEDGE ARM: UP {_fmt_money(snapshot.get("hedge_arm_up"))} | DOWN {_fmt_money(snapshot.get("hedge_arm_down"))}'
        )
    return '
'.join(lines)
