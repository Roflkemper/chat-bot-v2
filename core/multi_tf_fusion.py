from __future__ import annotations

from typing import Any, Dict


def _s(v: Any) -> str:
    return str(v or '').strip()


def _f(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _norm_dir(v: Any) -> str:
    s = _s(v).upper()
    if s in {'LONG', 'ЛОНГ', 'UP', 'ВВЕРХ', 'BULLISH'}:
        return 'ЛОНГ'
    if s in {'SHORT', 'ШОРТ', 'DOWN', 'ВНИЗ', 'BEARISH'}:
        return 'ШОРТ'
    return 'НЕЙТРАЛЬНО'


def _tf_role(tf: str) -> Dict[str, str]:
    tf = _s(tf).lower()
    mapping = {
        '5m': {'execution_tf': '5m', 'bias_tf': '15m', 'context_tf': '1h', 'htf_tf': '4h'},
        '15m': {'execution_tf': '15m', 'bias_tf': '1h', 'context_tf': '4h', 'htf_tf': '1d'},
        '1h': {'execution_tf': '1h', 'bias_tf': '4h', 'context_tf': '1d', 'htf_tf': '1d'},
        '4h': {'execution_tf': '4h', 'bias_tf': '1d', 'context_tf': '1d', 'htf_tf': '1d'},
        '1d': {'execution_tf': '1d', 'bias_tf': '1d', 'context_tf': '1d', 'htf_tf': '1d'},
    }
    return mapping.get(tf, mapping['1h']).copy()


def build_multi_tf_context(data: Dict[str, Any]) -> Dict[str, Any]:
    decision = data.get('decision') if isinstance(data.get('decision'), dict) else {}
    timeframe = _s(data.get('timeframe') or '1h').lower()
    tf_roles = _tf_role(timeframe)

    local_dir = _norm_dir(decision.get('direction_text') or decision.get('direction') or data.get('final_decision'))
    forecast_dir = _norm_dir(data.get('forecast_direction'))
    pattern_dir = _norm_dir(data.get('pattern_forecast_direction') or data.get('history_pattern_direction'))
    htf_dir = _norm_dir(data.get('htf_bias') or data.get('htf_direction') or data.get('higher_tf_bias'))

    local_conf = _f(decision.get('confidence_pct') or decision.get('confidence'))
    if local_conf <= 1.0:
        local_conf *= 100.0
    forecast_conf = _f(data.get('forecast_confidence'))
    if forecast_conf <= 1.0:
        forecast_conf *= 100.0
    pattern_conf = _f(data.get('pattern_forecast_confidence') or data.get('history_pattern_confidence'))
    if pattern_conf <= 1.0:
        pattern_conf *= 100.0

    support = 0
    oppose = 0
    parts = []
    if forecast_dir != 'НЕЙТРАЛЬНО':
        parts.append(f'forecast={forecast_dir}')
        if local_dir == 'НЕЙТРАЛЬНО' or forecast_dir == local_dir:
            support += 1
        else:
            oppose += 1
    if pattern_dir != 'НЕЙТРАЛЬНО':
        parts.append(f'pattern={pattern_dir}')
        if local_dir == 'НЕЙТРАЛЬНО' or pattern_dir == local_dir:
            support += 1
        else:
            oppose += 1
    if htf_dir != 'НЕЙТРАЛЬНО':
        parts.append(f'htf={htf_dir}')
        if local_dir == 'НЕЙТРАЛЬНО' or htf_dir == local_dir:
            support += 1
        else:
            oppose += 1

    if local_dir == 'НЕЙТРАЛЬНО':
        alignment = 'MIXED'
        action = 'WAIT'
        summary = 'локальный сигнал ещё не собран; execution только после выравнивания ТФ'
    elif support >= 2 and oppose == 0:
        alignment = 'FULL ALIGNMENT'
        action = 'FOLLOW THROUGH'
        summary = 'локальный сигнал синхронизирован с forecast/pattern/HTF'
    elif support >= 1 and oppose == 0:
        alignment = 'GOOD ALIGNMENT'
        action = 'CAN EXECUTE'
        summary = 'локальный сценарий поддержан сверху; работать можно аккуратнее'
    elif support >= 1 and oppose >= 1:
        alignment = 'CONFLICT'
        action = 'REDUCE AGGRESSION'
        summary = 'есть конфликт между локальным входом и старшим контекстом'
    else:
        alignment = 'WEAK ALIGNMENT'
        action = 'SCALP / WAIT'
        summary = 'подтверждение сверху слабое; лучше скальп или ожидание'

    risk_modifier = 'NORMAL'
    if alignment == 'FULL ALIGNMENT' and max(local_conf, forecast_conf, pattern_conf) >= 60:
        risk_modifier = 'ALLOW NORMAL RISK'
    elif alignment in {'CONFLICT', 'WEAK ALIGNMENT'}:
        risk_modifier = 'REDUCE SIZE'
    elif local_dir == 'НЕЙТРАЛЬНО':
        risk_modifier = 'NO TRADE'

    return {
        'timeframe': timeframe,
        'execution_tf': tf_roles['execution_tf'],
        'bias_tf': tf_roles['bias_tf'],
        'context_tf': tf_roles['context_tf'],
        'htf_tf': tf_roles['htf_tf'],
        'local_direction': local_dir,
        'forecast_direction': forecast_dir,
        'pattern_direction': pattern_dir,
        'htf_direction': htf_dir,
        'local_confidence_pct': round(local_conf, 1),
        'forecast_confidence_pct': round(forecast_conf, 1),
        'pattern_confidence_pct': round(pattern_conf, 1),
        'alignment': alignment,
        'support_count': support,
        'oppose_count': oppose,
        'action': action,
        'risk_modifier': risk_modifier,
        'summary': summary,
        'evidence': ', '.join(parts) if parts else 'local-only',
    }
