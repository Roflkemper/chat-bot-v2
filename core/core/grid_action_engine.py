from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Literal, List, Dict, Any

Side = Literal['LONG', 'SHORT', 'NEUTRAL']
Strength = Literal['LOW', 'MID', 'HIGH']
StructuralStrength = Literal['WEAK', 'MID', 'STRONG']
GridRegime = Literal['SAFE', 'CAUTION', 'DANGER']
GridActionName = Literal['BOOST', 'ENABLE', 'HOLD', 'REDUCE', 'PAUSE']
HedgeState = Literal['OFF', 'ARM', 'ACTIVE', 'TRIGGER', 'PRE-TRIGGER']
MarketRegime = Literal['RANGE', 'TREND', 'CHOP', 'UNKNOWN']
RangeQuality = Literal['GOOD', 'OK', 'WEAK']


@dataclass
class GridActionInput:
    price: float
    range_low: float
    range_high: float
    range_mid: float
    range_position_pct: float
    range_width_pct: float
    scalp_side: Side
    scalp_strength: Strength
    session_side: Side
    session_strength: Strength
    midterm_side: Side
    midterm_strength: Strength
    consensus_side: Side
    consensus_strength: Strength
    down_impulse_pct: float
    up_impulse_pct: float
    down_target: float
    up_target: float
    down_layers: int
    up_layers: int
    hedge_arm_down: float
    hedge_arm_up: float
    hedge_state: HedgeState
    repeated_upper_rejection: bool
    repeated_lower_rejection: bool
    upper_sweep: bool
    lower_sweep: bool
    distribution: bool
    accumulation: bool
    equal_highs: bool
    equal_lows: bool
    volume_rejection_up: bool
    volume_rejection_down: bool
    market_regime: MarketRegime
    range_quality: RangeQuality
    trend_pressure_side: Side
    trend_pressure_strength: Strength
    forecast_conflict: bool = False
    priority_side: Side = 'NEUTRAL'
    bias_score: int = 0
    edge_distance_pct: float = 50.0
    absorption_active: bool = False
    bars_at_edge: int = 0


@dataclass
class GridActionOutput:
    grid_regime: GridRegime
    bias_side: Side
    bias_note: str
    structural_side: Side
    structural_strength: StructuralStrength
    structural_note: str
    priority_side: Side
    long_action: GridActionName
    short_action: GridActionName
    down_impulse_pct: float
    up_impulse_pct: float
    down_target: float
    up_target: float
    down_layers: int
    up_layers: int
    safe_low: float
    safe_high: float
    review_level_up: float
    review_level_down: float
    action_lines: List[str]
    risk_lines: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _clamp_layers(value: int) -> int:
    return max(0, min(3, int(value)))


def _is_mid_range(range_position_pct: float) -> bool:
    return 40.0 <= range_position_pct <= 60.0


def _layers_word(n: int) -> str:
    if n == 1:
        return '1 слой'
    if n in (2, 3, 4):
        return f'{n} слоя'
    return f'{n} слоёв'


def _compute_bias_side(inp: GridActionInput) -> tuple[Side, str]:
    side = inp.midterm_side
    note_parts: List[str] = ['среднесрочный вектор']
    if inp.midterm_strength == 'HIGH':
        note_parts.append('сильный')
    elif inp.midterm_strength == 'MID':
        note_parts.append('умеренный')
    else:
        note_parts.append('слабый')
    if inp.consensus_side != 'NEUTRAL' and inp.consensus_side == inp.midterm_side:
        note_parts.append('подтверждён консенсусом')
    if inp.forecast_conflict:
        note_parts.append('локально есть конфликт')
    return side, ', '.join(note_parts)


def _compute_structural_side(inp: GridActionInput) -> tuple[Side, StructuralStrength, str]:
    short_hits = []
    if inp.repeated_upper_rejection:
        short_hits.append('repeated upper rejection')
    if inp.upper_sweep:
        short_hits.append('upper sweep')
    if inp.distribution:
        short_hits.append('distribution')
    if inp.equal_highs:
        short_hits.append('equal highs')
    if inp.volume_rejection_up:
        short_hits.append('volume rejection up')

    long_hits = []
    if inp.repeated_lower_rejection:
        long_hits.append('repeated lower rejection')
    if inp.lower_sweep:
        long_hits.append('lower sweep')
    if inp.accumulation:
        long_hits.append('accumulation')
    if inp.equal_lows:
        long_hits.append('equal lows')
    if inp.volume_rejection_down:
        long_hits.append('volume rejection down')

    if len(short_hits) >= 3 and len(short_hits) > len(long_hits):
        return 'SHORT', 'STRONG', ' / '.join(short_hits[:3])
    if len(long_hits) >= 3 and len(long_hits) > len(short_hits):
        return 'LONG', 'STRONG', ' / '.join(long_hits[:3])
    if len(short_hits) >= 2 and len(short_hits) > len(long_hits):
        return 'SHORT', 'MID', ' / '.join(short_hits[:3])
    if len(long_hits) >= 2 and len(long_hits) > len(short_hits):
        return 'LONG', 'MID', ' / '.join(long_hits[:3])
    if short_hits and long_hits:
        return 'NEUTRAL', 'WEAK', 'mixed structure'
    return 'NEUTRAL', 'WEAK', 'явного структурного перевеса нет'


def _compute_grid_regime(inp: GridActionInput, structural_strength: StructuralStrength) -> GridRegime:
    if inp.trend_pressure_strength == 'HIGH':
        return 'DANGER'
    if inp.market_regime == 'TREND' and inp.trend_pressure_strength in ('MID', 'HIGH'):
        return 'DANGER'
    if structural_strength == 'STRONG':
        return 'CAUTION'
    if inp.market_regime == 'RANGE' and inp.range_quality != 'WEAK':
        return 'SAFE'
    if inp.market_regime == 'CHOP' and inp.range_quality == 'GOOD':
        return 'SAFE'
    return 'CAUTION'


def _compute_priority_side(inp: GridActionInput, bias_side: Side, structural_side: Side, structural_strength: StructuralStrength) -> Side:
    forced_priority = str(getattr(inp, 'priority_side', 'NEUTRAL') or 'NEUTRAL').upper()
    if forced_priority in {'LONG', 'SHORT', 'NEUTRAL'} and forced_priority != 'NEUTRAL':
        return forced_priority
    if structural_strength == 'STRONG' and structural_side != 'NEUTRAL':
        return structural_side
    if (_is_mid_range(inp.range_position_pct) and bias_side == 'NEUTRAL' and structural_side == 'NEUTRAL'
            and inp.down_layers == inp.up_layers and abs(inp.down_impulse_pct - inp.up_impulse_pct) <= 0.25):
        return 'NEUTRAL'
    if inp.down_layers > inp.up_layers:
        return 'SHORT'
    if inp.up_layers > inp.down_layers:
        return 'LONG'
    if inp.down_impulse_pct > inp.up_impulse_pct:
        return 'SHORT'
    if inp.up_impulse_pct > inp.down_impulse_pct:
        return 'LONG'
    if structural_side != 'NEUTRAL':
        return structural_side
    if bias_side != 'NEUTRAL':
        return bias_side
    return 'NEUTRAL'


def _compute_long_action(inp: GridActionInput, regime: GridRegime, priority: Side, structural_side: Side, structural_strength: StructuralStrength) -> GridActionName:
    session_short_guard = (
        inp.session_side == 'SHORT'
        and inp.session_strength == 'HIGH'
        and inp.bias_score <= -3
        and inp.edge_distance_pct <= 10.0
    )
    edge_pressure_high = int(getattr(inp, 'bars_at_edge', 0) or 0) >= 4 and not bool(getattr(inp, 'absorption_active', False))
    if regime == 'DANGER' and inp.trend_pressure_side == 'SHORT':
        return 'PAUSE'
    if session_short_guard:
        if priority == 'SHORT' or (structural_side == 'SHORT' and structural_strength in ('MID', 'STRONG')):
            return 'REDUCE'
        return 'HOLD'
    if priority == 'LONG' and regime != 'DANGER':
        if edge_pressure_high:
            return 'HOLD'
        if inp.up_layers >= 2 and not (structural_side == 'SHORT' and structural_strength == 'STRONG'):
            return 'BOOST'
        return 'ENABLE'
    if priority == 'SHORT':
        if structural_side == 'SHORT' and structural_strength in ('MID', 'STRONG'):
            return 'REDUCE'
        return 'HOLD'
    return 'HOLD' if regime == 'SAFE' else 'ENABLE'


def _compute_short_action(inp: GridActionInput, regime: GridRegime, priority: Side, structural_side: Side, structural_strength: StructuralStrength) -> GridActionName:
    session_long_guard = (
        inp.session_side == 'LONG'
        and inp.session_strength == 'HIGH'
        and inp.bias_score >= 3
        and inp.edge_distance_pct <= 10.0
    )
    if regime == 'DANGER' and inp.trend_pressure_side == 'LONG':
        return 'PAUSE'
    if session_long_guard:
        if priority == 'LONG' or (structural_side == 'LONG' and structural_strength in ('MID', 'STRONG')):
            return 'REDUCE'
        return 'HOLD'
    if priority == 'SHORT' and regime != 'DANGER':
        if inp.down_layers >= 2 and not (structural_side == 'LONG' and structural_strength == 'STRONG'):
            return 'BOOST'
        return 'ENABLE'
    if priority == 'LONG':
        if structural_side == 'LONG' and structural_strength in ('MID', 'STRONG'):
            return 'REDUCE'
        return 'HOLD'
    return 'HOLD' if regime == 'SAFE' else 'ENABLE'


def _build_action_lines(inp: GridActionInput, bias_side: Side, structural_side: Side, priority: Side) -> List[str]:
    lines = [f'вниз {_layers_word(inp.down_layers)}, вверх {_layers_word(inp.up_layers)}']
    if structural_side == 'SHORT':
        lines.append('локальная 1h-структура давит вниз')
    elif structural_side == 'LONG':
        lines.append('локальная 1h-структура поддерживает движение вверх')
    if bias_side != 'NEUTRAL' and structural_side != 'NEUTRAL' and bias_side != structural_side:
        lines.append(f'среднесрок {bias_side}, но локально давление {structural_side.lower()}')
    if priority == 'SHORT':
        lines.append('практический приоритет у short-сеток')
    elif priority == 'LONG':
        lines.append('практический приоритет у long-сеток')
    else:
        lines.append('явного приоритета по сеткам нет')
    return lines[:4]


def _build_risk_lines(inp: GridActionInput, regime: GridRegime, priority: Side, bias_side: Side) -> List[str]:
    lines: List[str] = []
    if int(getattr(inp, 'bars_at_edge', 0) or 0) >= 4 and not bool(getattr(inp, 'absorption_active', False)):
        lines.append(f"{int(getattr(inp, 'bars_at_edge', 0))}+ баров у края без absorption")
    if regime == 'DANGER':
        lines.append('рынок перестаёт быть grid-friendly')
    elif regime == 'CAUTION':
        lines.append('одна сторона сеток под давлением')
    if bias_side != 'NEUTRAL' and priority != 'NEUTRAL' and bias_side != priority:
        lines.append(f'среднесрок {bias_side}, но практический приоритет {priority}')
    if priority == 'SHORT':
        lines.append(f'пробой {inp.hedge_arm_up:.2f} вверх ломает short-сценарий')
    elif priority == 'LONG':
        lines.append(f'пробой {inp.hedge_arm_down:.2f} вниз ломает long-сценарий')
    else:
        lines.append('до выхода из safe range обе стороны остаются допустимыми')
    return lines[:4]


def build_grid_action(inp: GridActionInput) -> Dict[str, Any]:
    inp.down_layers = _clamp_layers(inp.down_layers)
    inp.up_layers = _clamp_layers(inp.up_layers)
    bias_side, bias_note = _compute_bias_side(inp)
    structural_side, structural_strength, structural_note = _compute_structural_side(inp)
    regime = _compute_grid_regime(inp, structural_strength)
    priority = _compute_priority_side(inp, bias_side, structural_side, structural_strength)
    long_action = _compute_long_action(inp, regime, priority, structural_side, structural_strength)
    short_action = _compute_short_action(inp, regime, priority, structural_side, structural_strength)
    output = GridActionOutput(
        grid_regime=regime,
        bias_side=bias_side,
        bias_note=bias_note,
        structural_side=structural_side,
        structural_strength=structural_strength,
        structural_note=structural_note,
        priority_side=priority,
        long_action=long_action,
        short_action=short_action,
        down_impulse_pct=inp.down_impulse_pct,
        up_impulse_pct=inp.up_impulse_pct,
        down_target=inp.down_target,
        up_target=inp.up_target,
        down_layers=inp.down_layers,
        up_layers=inp.up_layers,
        safe_low=inp.hedge_arm_down,
        safe_high=inp.hedge_arm_up,
        review_level_up=inp.hedge_arm_up,
        review_level_down=inp.hedge_arm_down,
        action_lines=_build_action_lines(inp, bias_side, structural_side, priority),
        risk_lines=_build_risk_lines(inp, regime, priority, bias_side),
    )
    return output.to_dict()
