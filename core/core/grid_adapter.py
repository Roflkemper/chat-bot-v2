from __future__ import annotations

from core.grid_action_engine import GridActionInput


def _side(value: str) -> str:
    return value if value in {'LONG', 'SHORT', 'NEUTRAL'} else 'NEUTRAL'


def _strength(value: str) -> str:
    return value if value in {'LOW', 'MID', 'HIGH'} else 'LOW'


def snapshot_to_grid_input(snapshot: dict) -> GridActionInput:
    fc = snapshot.get('forecast', {})
    short_fc = fc.get('short', {})
    session_fc = fc.get('session', {})
    medium_fc = fc.get('medium', {})
    return GridActionInput(
        price=float(snapshot.get('price', 0.0)),
        range_low=float(snapshot.get('range_low', 0.0)),
        range_high=float(snapshot.get('range_high', 0.0)),
        range_mid=float(snapshot.get('range_mid', 0.0)),
        range_position_pct=float(snapshot.get('range_position_pct', 50.0)),
        range_width_pct=float(snapshot.get('range_width_pct', 0.0)),
        scalp_side=_side(short_fc.get('direction', 'NEUTRAL')),
        scalp_strength=_strength(short_fc.get('strength', 'LOW')),
        session_side=_side(session_fc.get('direction', 'NEUTRAL')),
        session_strength=_strength(session_fc.get('strength', 'LOW')),
        midterm_side=_side(medium_fc.get('direction', 'NEUTRAL')),
        midterm_strength=_strength(medium_fc.get('strength', 'LOW')),
        consensus_side=_side(snapshot.get('consensus_direction', 'NEUTRAL')),
        consensus_strength=_strength(snapshot.get('consensus_confidence', 'LOW')),
        down_impulse_pct=float(snapshot.get('down_impulse_pct', 0.0)),
        up_impulse_pct=float(snapshot.get('up_impulse_pct', 0.0)),
        down_target=float(snapshot.get('down_target', 0.0)),
        up_target=float(snapshot.get('up_target', 0.0)),
        down_layers=int(snapshot.get('down_layers', 0)),
        up_layers=int(snapshot.get('up_layers', 0)),
        hedge_arm_down=float(snapshot.get('hedge_arm_down', 0.0)),
        hedge_arm_up=float(snapshot.get('hedge_arm_up', 0.0)),
        hedge_state=snapshot.get('hedge_state', 'OFF'),
        repeated_upper_rejection=bool(snapshot.get('repeated_upper_rejection', False)),
        repeated_lower_rejection=bool(snapshot.get('repeated_lower_rejection', False)),
        upper_sweep=bool(snapshot.get('upper_sweep', False)),
        lower_sweep=bool(snapshot.get('lower_sweep', False)),
        distribution=bool(snapshot.get('distribution', False)),
        accumulation=bool(snapshot.get('accumulation', False)),
        equal_highs=bool(snapshot.get('equal_highs', False)),
        equal_lows=bool(snapshot.get('equal_lows', False)),
        volume_rejection_up=bool(snapshot.get('volume_rejection_up', False)),
        volume_rejection_down=bool(snapshot.get('volume_rejection_down', False)),
        market_regime=snapshot.get('market_regime', 'UNKNOWN'),
        range_quality=snapshot.get('range_quality', 'WEAK'),
        trend_pressure_side=_side(snapshot.get('trend_pressure_side', 'NEUTRAL')),
        trend_pressure_strength=_strength(snapshot.get('trend_pressure_strength', 'LOW')),
        forecast_conflict=bool(snapshot.get('forecast_conflict', False)),
        bias_score=int(snapshot.get('bias_score', 0) or 0),
        edge_distance_pct=float(snapshot.get('edge_distance_pct', 50.0) or 50.0),
        absorption_active=bool((snapshot.get('absorption') or {}).get('is_active', False)),
        bars_at_edge=int((snapshot.get('absorption') or {}).get('bars_at_edge', 0) or 0),
    )
