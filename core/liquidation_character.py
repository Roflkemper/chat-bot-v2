from __future__ import annotations

from typing import Any, Dict


def _f(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def analyze_fast_move(data: Dict[str, Any], analysis_snapshot: Dict[str, Any] | None = None) -> Dict[str, Any]:
    decision = data.get('decision') if isinstance(data.get('decision'), dict) else {}
    cls = str(decision.get('fast_move_classification') or data.get('fast_move_classification') or data.get('move_classification') or '').upper()
    confidence = _f(decision.get('confidence_pct') or data.get('forecast_confidence') or 0.0)
    volatility = _f(data.get('volatility_pct') or data.get('impulse_pct') or data.get('move_pct') or 0.0)
    late_risk = str((data.get('setup_quality') or {}).get('late_entry_risk') if isinstance(data.get('setup_quality'), dict) else '').upper()

    move_type = 'NORMAL'
    if cls in {'LIKELY_FAKE_UP', 'LIKELY_FAKE_DOWN'}:
        move_type = 'FALSE_BREAK'
    elif cls in {'POST_LIQUIDATION_EXHAUSTION', 'SQUEEZE_WITHOUT_CONFIRMATION'}:
        move_type = 'LIQUIDITY_SWEEP'
    elif cls in {'CONTINUATION_UP', 'CONTINUATION_DOWN'} and (volatility >= 1.2 or late_risk == 'HIGH'):
        move_type = 'AGGRESSIVE_PUSH'
    elif volatility >= 1.8:
        move_type = 'AGGRESSIVE_PUSH'

    continuation_probability = min(95.0, max(5.0, confidence + (8 if move_type == 'NORMAL' else -6 if move_type == 'FALSE_BREAK' else -2)))
    exhaustion_probability = min(95.0, max(5.0, 100 - continuation_probability + (8 if move_type in {'LIQUIDITY_SWEEP', 'FALSE_BREAK'} else 0)))

    comment_map = {
        'NORMAL': 'движение выглядит относительно здоровым; контртренд против него пока опасен',
        'AGGRESSIVE_PUSH': 'идет сильный вынос; если ты уже в позиции — можно держать, но вход в догонку плохой',
        'LIQUIDITY_SWEEP': 'похоже на добой ликвидности; у сильной зоны стоит смотреть фиксацию части и реакцию',
        'FALSE_BREAK': 'вынос выглядит слабым по качеству продолжения; контртренд можно искать только после подтверждения',
    }
    return {
        'move_type': move_type,
        'intensity': round(max(volatility, confidence / 50.0), 2),
        'continuation_probability': round(continuation_probability, 1),
        'exhaustion_probability': round(exhaustion_probability, 1),
        'comment': comment_map[move_type],
    }
