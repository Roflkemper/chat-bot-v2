from __future__ import annotations

from typing import Any, Dict

from core.pipeline import build_full_snapshot
from models.snapshots import AnalysisSnapshot, PositionSnapshot
from renderers.renderer import render_full_report


def _ru_direction(side: str) -> str:
    side = str(side or '').upper()
    return {'LONG': 'ЛОНГ', 'SHORT': 'ШОРТ', 'NEUTRAL': 'НЕЙТРАЛЬНО'}.get(side, side or 'НЕЙТРАЛЬНО')




def _safe_confidence(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        text = str(value or '').upper()
        return {'LOW': 35.0, 'MID': 55.0, 'MEDIUM': 55.0, 'HIGH': 75.0}.get(text, 0.0)

def _ru_action(action: str) -> str:
    action = str(action or '').upper()
    return {
        'WAIT': 'ЖДАТЬ',
        'ENTER': 'ВХОД',
        'PREPARE': 'ГОТОВИТЬ',
        'HOLD': 'ДЕРЖАТЬ',
        'EXIT': 'ВЫХОД',
        'REDUCE': 'СОКРАТИТЬ',
        'WORK': 'РАБОТАТЬ',
        'PAUSE': 'ПАУЗА',
    }.get(action, action or 'ЖДАТЬ')


def build_pipeline_bundle(symbol: str = 'BTCUSDT') -> Dict[str, Any]:
    snapshot = build_full_snapshot(symbol=symbol)
    return snapshot if isinstance(snapshot, dict) else {}


def pipeline_snapshot_to_analysis(snapshot: Dict[str, Any], timeframe: str = '1h') -> AnalysisSnapshot:
    snap = snapshot if isinstance(snapshot, dict) else {}
    forecast = snap.get('forecast') if isinstance(snap.get('forecast'), dict) else {}
    short_fc = forecast.get('short') if isinstance(forecast.get('short'), dict) else {}
    session_fc = forecast.get('session') if isinstance(forecast.get('session'), dict) else {}
    medium_fc = forecast.get('medium') if isinstance(forecast.get('medium'), dict) else {}
    execution_side = str(snap.get('execution_side') or snap.get('consensus_direction') or 'NEUTRAL').upper()
    action = str(snap.get('action') or 'WAIT').upper()
    risk_mode = str(snap.get('risk_mode') or 'NORMAL').upper()
    confidence = _safe_confidence(snap.get('execution_confidence') or 0.0)
    decision = {
        'direction': execution_side,
        'direction_text': _ru_direction(execution_side),
        'action': action,
        'action_text': _ru_action(action),
        'manager_action': action,
        'manager_action_text': _ru_action(action),
        'mode': str(snap.get('market_regime') or 'MIXED').upper(),
        'regime': str(snap.get('market_regime') or 'MIXED').upper(),
        'confidence': confidence,
        'confidence_pct': confidence,
        'risk': risk_mode,
        'risk_level': risk_mode,
        'summary': str(snap.get('top_signal') or ''),
        'pressure_reason': str(snap.get('block_pressure_reason') or ''),
        'entry_reason': str(snap.get('trigger_note') or ''),
        'invalidation': str((snap.get('if_then_plan') or [''])[-1] if snap.get('if_then_plan') else ''),
        'range_position': str(snap.get('depth_label') or snap.get('range_position_pct') or 'UNKNOWN'),
        'range_position_zone': f"{snap.get('range_position_pct', '—')}% диапазона",
        'reasons': [str(x) for x in (snap.get('warnings') or []) if str(x).strip()],
        'market_state': str(snap.get('state') or 'UNKNOWN'),
        'market_state_text': str(snap.get('top_signal') or ''),
        'setup_status': action,
        'setup_status_text': _ru_action(action),
        'entry_type': str(snap.get('entry_type') or 'no_trade').lower(),
        'execution_mode': str(snap.get('execution_profile') or 'conservative').lower(),
        'no_trade_reason': str(snap.get('trigger_block_reason') or ''),
        'late_entry_risk': str(snap.get('entry_quality') or ''),
        'location_quality': str(snap.get('depth_label') or 'C'),
    }
    data = {
        'symbol': snap.get('symbol', 'BTCUSDT'),
        'timeframe': timeframe,
        'price': snap.get('price') or 0.0,
        'signal': _ru_direction(execution_side),
        'final_decision': _ru_action(action),
        'forecast_direction': _ru_direction(str(session_fc.get('direction') or execution_side)),
        'forecast_confidence': confidence / 100.0 if confidence > 1 else confidence,
        'reversal_signal': str(snap.get('trigger_type') or 'NO_REVERSAL'),
        'reversal_confidence': 0.0,
        'reversal_patterns': [str(snap.get('trigger_note') or '')] if snap.get('trigger_note') else [],
        'history_pattern_direction': str(medium_fc.get('direction') or 'NEUTRAL'),
        'history_pattern_confidence': float({'LOW': 0.33, 'MID': 0.55, 'HIGH': 0.75}.get(str(medium_fc.get('strength') or 'LOW').upper(), 0.0)),
        'history_pattern_summary': str(medium_fc.get('note') or ''),
        'range_state': str(snap.get('market_regime') or 'нет данных'),
        'range_position': str(snap.get('depth_label') or 'UNKNOWN'),
        'ct_now': str(snap.get('top_signal') or ''),
        'ginarea_advice': str((snap.get('grid_action_lines') or ['нет данных'])[0]),
        'decision_summary': str(snap.get('top_signal') or ''),
        'range_low': snap.get('range_low'),
        'range_mid': snap.get('range_mid'),
        'range_high': snap.get('range_high'),
        'decision': decision,
        'stats': {
            'pipeline_sync': True,
            'state': snap.get('state'),
            'active_block': snap.get('active_block'),
            'entry_filter_ok': snap.get('entry_filter_ok'),
            'entry_filter_reason': snap.get('entry_filter_reason'),
        },
        'analysis': {
            'pipeline_snapshot': dict(snap),
            'pipeline_sync': True,
            'short_forecast': short_fc,
            'session_forecast': session_fc,
            'medium_forecast': medium_fc,
        },
    }
    return AnalysisSnapshot.from_dict(data, symbol=str(snap.get('symbol') or 'BTCUSDT'), timeframe=timeframe)


def build_pipeline_analysis_text(snapshot: Dict[str, Any]) -> str:
    return render_full_report(snapshot)


def build_pipeline_action_text(snapshot: Dict[str, Any]) -> str:
    snap = snapshot or {}
    lines = [
        f"⚡ ACTION NOW [{snap.get('tf', '1h')}]",
        '',
        str(snap.get('top_signal') or '⏸️ WAIT'),
        f"• действие: {snap.get('action', 'WAIT')}",
        f"• сторона: {snap.get('execution_side', 'NEUTRAL')}",
        f"• trigger: {snap.get('trigger_type') or 'NONE'}",
        f"• причина: {snap.get('trigger_note') or 'нет подтверждения'}",
        f"• качество входа: {snap.get('entry_quality') or 'NO_TRADE'}",
        f"• профиль: {snap.get('execution_profile') or 'NO_ENTRY'}",
        f"• режим риска: {snap.get('risk_mode') or 'NORMAL'}",
    ]
    if snap.get('entry_filter_reason'):
        lines.append(f"• фильтр входа: {snap.get('entry_filter_reason')}")
    if snap.get('trigger_block_reason'):
        lines.append(f"• блокировка: {snap.get('trigger_block_reason')}")
    warnings = [str(x) for x in (snap.get('warnings') or []) if str(x).strip()]
    if warnings:
        lines.append('')
        lines.append('⚠️ ПРЕДУПРЕЖДЕНИЯ:')
        lines.extend(warnings[:5])
    plan = [str(x) for x in (snap.get('if_then_plan') or []) if str(x).strip()]
    if plan:
        lines.append('')
        lines.append('ПЛАН:')
        lines.extend(plan[:8])
    return '\n'.join(lines)


def build_pipeline_exit_text(snapshot: Dict[str, Any], journal_side: str = '') -> str:
    snap = snapshot or {}
    position_control = snap.get('position_control') if isinstance(snap.get('position_control'), dict) else {}
    lines = [
        f"🛑 EXIT / MANAGE [{snap.get('tf', '1h')}]",
        '',
        f"• позиция: {journal_side or position_control.get('status') or 'FLAT'}",
        f"• рекомендация: {position_control.get('recommended_action') or snap.get('action') or 'WAIT'}",
        f"• pnl: {position_control.get('pnl_pct', 0.0)}%",
    ]
    exit_lines = [str(x) for x in (snap.get('exit_strategy_lines') or []) if str(x).strip()]
    if exit_lines:
        lines.append('')
        lines.append('EXIT STRATEGY:')
        lines.extend(exit_lines)
    else:
        lines.append('• exit strategy: нет данных')
    return '\n'.join(lines)


def build_pipeline_position_text(snapshot: Dict[str, Any], position: PositionSnapshot | None = None) -> str:
    snap = snapshot or {}
    pos = position or PositionSnapshot()
    lines = [
        '📌 МОЯ ПОЗИЦИЯ',
        '',
        f"• статус: {'ОТКРЫТА' if pos.has_position else 'НЕТ ПОЗИЦИИ'}",
        f"• сторона: {pos.side or 'FLAT'}",
    ]
    if pos.has_position:
        lines.append(f"• entry: {pos.entry_price}")
        if pos.take_profit:
            lines.append(f"• tp: {pos.take_profit}")
        if pos.stop_loss:
            lines.append(f"• sl: {pos.stop_loss}")
    pc = snap.get('position_control') if isinstance(snap.get('position_control'), dict) else {}
    if pc:
        lines.append(f"• runtime action: {pc.get('recommended_action') or 'WAIT'}")
        lines.append(f"• runtime pnl: {pc.get('pnl_pct', 0.0)}%")
    lines.append('')
    lines.append(str(snap.get('top_signal') or 'нет данных'))
    return '\n'.join(lines)
