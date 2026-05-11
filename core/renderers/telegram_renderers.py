from __future__ import annotations

from typing import Any, Dict, Union

from core.btc_plan import fmt_pct, fmt_price
from core.grid_regime_manager_v1689 import derive_v1689_context
from core.telegram_formatter import _derive_v16_view, _range_quality_ru, _divergence_ru, _execution_block_lines, _hedge_block_lines
from core.ux_mode import build_ultra_wait_block, is_no_trade_context
from models.snapshots import AnalysisSnapshot, JournalSnapshot, PositionSnapshot
from storage.position_store import load_position_state
from storage.trade_journal import load_trade_journal


def build_help_text() -> str:
    return "\n".join([
        "🤖 ЧАТ БОТ ВЕРСИЯ 2 — ФИНАЛЬНЫЙ РЕЛИЗ",
        "",
        "ОСНОВНЫЕ КНОПКИ:",
        "• BTC 15M / BTC 1H — быстрый анализ",
        "• ФИНАЛЬНОЕ РЕШЕНИЕ — главный итог",
        "• СВОДКА BTC / ПРОГНОЗ BTC / BTC GINAREA (V14 без V13 overlay)",
        "• ⚡ ЧТО ДЕЛАТЬ / ЛУЧШАЯ СДЕЛКА / МЕНЕДЖЕР BTC",
        "• СТАТУС БОТОВ / СТАТУС СИСТЕМЫ",
        "",
        "КОГДА НУЖНО УГЛУБИТЬСЯ:",
        "• ПОЧЕМУ НЕТ СДЕЛКИ — почему лучше ждать",
        "• BTC INVALIDATION — где ломается идея",
        "• BTC TRADE MANAGER — ведение уже открытого сценария",
        "",
        "ПОЗИЦИЯ:",
        "• ОТКРЫТЬ ЛОНГ / ОТКРЫТЬ ШОРТ",
        "• МОЯ ПОЗИЦИЯ / ВЕСТИ BTC / ЗАКРЫТЬ BTC",
        "• ВЕСТИ ЛОНГ / ВЕСТИ ШОРТ",
        "",
        "СЛЭШ-КОМАНДЫ (текстом, on-demand):",
        "• /status — heartbeat, pid процессов, открытые P-15 leg, последний сетап + GC",
        "• /p15 — детальный per-leg отчёт P-15 (avg/extreme/dd + последние 5 событий)",
        "• /ginarea (alias /bots) — снимок всех GinArea ботов: позиции, unrz PnL, дистанция до liq",
        "• /changelog (alias /log24) — что произошло за 24ч: коммиты, pipeline, P-15 PnL",
        "• /pipeline — детектор funnel: fired/blocked/emit yield% по каждому детектору",
        "• /disable <token> — runtime kill detector (substring match)",
        "• /enable <token> — снять runtime disable (env-level disable не трогает)",
        "• /audit — текущая аудит-сводка (advisor)",
        "• /report_today / /report_week — итог дня / недели",
        "• /setups setup_stats — статистика по детекторам за 7д",
        "• /restart — рестарт компонента (после деплоя)",
        "",
        "СЛЭШ-КОМАНДЫ (быстрые):",
        "• /watch / /watchlist — алерты по правилам оператора",
        "• /confirm <id> / /reject <id> — подтверждение proposal",
        "• /proposals — активные предложения",
        "• /momentum — momentum check сейчас",
    ])


def _coerce_analysis_snapshot(data: Union[AnalysisSnapshot, Dict[str, Any]], default_tf: str = "1h") -> AnalysisSnapshot:
    if isinstance(data, AnalysisSnapshot):
        return data
    return AnalysisSnapshot.from_dict(data, timeframe=default_tf)


def _safe_get(obj: Any, name: str, default: Any = None) -> Any:
    try:
        return getattr(obj, name, default)
    except Exception:
        return default




def _safe_float(value: Any, default: Any = 0.0) -> Any:
    try:
        return float(value)
    except Exception:
        return default


def safe_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if float(value) == 0.0:
            return None
        return value
    text = str(value).strip()
    if not text:
        return None
    if text.upper() in {'NONE', '-', '0', '0.0', 'NO_REVERSAL'}:
        return None
    return value


def _runtime_icon(state: str) -> str:
    return {
        'RUN': '🟢',
        'REDUCE': '🟡',
        'PAUSE': '⏸',
        'EXIT': '🔴',
        'ARM': '🔵',
    }.get(str(state or '').upper(), '•')


def _runtime_ru(state: str) -> str:
    return {
        'RUN': 'держать рабочим',
        'REDUCE': 'сокращать / не добавлять',
        'PAUSE': 'пауза / не включать',
        'EXIT': 'выход / закрыть',
        'ARM': 'готовить только у края',
    }.get(str(state or '').upper(), str(state or ''))


def _runtime_state_ru(state: str) -> str:
    return {
        'RUN': 'РАБОТАТЬ',
        'REDUCE': 'СОКРАТИТЬ',
        'PAUSE': 'ПАУЗА',
        'EXIT': 'ВЫХОД',
        'ARM': 'ГОТОВИТЬ',
    }.get(str(state or '').upper(), str(state or ''))


def _zone_from_bounds(a: Any, b: Any, suffix: str = '') -> str:
    a_val = _safe_float(a, None)
    b_val = _safe_float(b, None)
    if a_val is None and b_val is None:
        return 'нет данных'
    if a_val is None:
        return f"{fmt_price(b_val)}{suffix}".strip() or 'нет данных'
    if b_val is None:
        return f"{fmt_price(a_val)}{suffix}".strip() or 'нет данных'
    lo = min(a_val, b_val)
    hi = max(a_val, b_val)
    zone = f"{fmt_price(lo)}–{fmt_price(hi)}"
    return f"{zone}{suffix}".strip() or 'нет данных'


def _action_output_lines(decision: dict) -> list[str]:
    action_output = decision.get('action_output') if isinstance(decision.get('action_output'), dict) else {}
    if not action_output:
        return []
    lines = [action_output.get('title', '⚡ ЧТО ДЕЛАТЬ')]
    for line in action_output.get('summary_lines', []):
        lines.append(f'• {line}')
    launch_lines = action_output.get('launch_lines', [])
    if launch_lines:
        lines.append('')
        lines.append('Условия / план:')
        for line in launch_lines:
            lines.append(f'• {line}')
    invalidation_lines = action_output.get('invalidation_lines', [])
    if invalidation_lines:
        lines.append('')
        lines.append('Отмена:')
        for line in invalidation_lines:
            lines.append(f'• {line}')
    return lines


def _move_type_lines(decision: dict) -> list[str]:
    ctx = decision.get('move_type_context') if isinstance(decision.get('move_type_context'), dict) else {}
    if not ctx:
        return []
    return ['MOVE TYPE:', f"• type: {ctx.get('type', 'NO_CLEAR_MOVE')}", f"• bias: {ctx.get('bias', 'NEUTRAL')}", f"• summary: {ctx.get('summary', 'нет данных')}", f"• implication: {ctx.get('implication', 'нет данных')}"]


def _range_bot_permission_lines(decision: dict) -> list[str]:
    permission = decision.get('range_bot_permission') if isinstance(decision.get('range_bot_permission'), dict) else {}
    if not permission:
        return []
    borders = permission.get('working_borders') if isinstance(permission.get('working_borders'), dict) else {}
    long_zone = permission.get('long_zone') if isinstance(permission.get('long_zone'), list) else []
    short_zone = permission.get('short_zone') if isinstance(permission.get('short_zone'), list) else []
    def _fmt_zone(z):
        if isinstance(z, list) and len(z) == 2:
            return f"{z[0]}–{z[1]}"
        return 'нет данных'
    lines = ['RANGE BOT PERMISSION:']
    lines.append(f"• status: {permission.get('status', 'OFF')}")
    lines.append(f"• can run now: {'YES' if permission.get('can_run_now') else 'NO'}")
    lines.append(f"• size mode: {permission.get('size_mode', 'x0.00')}")
    lines.append(f"• adds allowed: {'YES' if permission.get('adds_allowed') else 'NO'}")
    if borders.get('low') and borders.get('high'):
        lines.append(f"• working borders: {borders.get('low')}–{borders.get('high')}")
    lines.append(f"• long-zone: {_fmt_zone(long_zone)}")
    lines.append(f"• short-zone: {_fmt_zone(short_zone)}")
    return lines

def _decision_dict(snapshot: AnalysisSnapshot) -> Dict[str, Any]:
    obj = _safe_get(snapshot, "decision", None)
    if obj is None or obj is snapshot:
        return {}
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "to_dict"):
        try:
            data = obj.to_dict()
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    out: Dict[str, Any] = {}
    for key in (
        "direction", "direction_text",
        "action", "action_text",
        "manager_action", "manager_action_text",
        "mode", "regime",
        "confidence", "confidence_pct",
        "risk", "risk_level",
        "summary",
        "scenario_text", "trigger_text", "impulse_state", "impulse_comment",
        "impulse_strength", "impulse_freshness", "impulse_exhaustion", "impulse_confirmation",
        "forecast_strength", "long_score", "short_score",
        "pressure_reason", "entry_reason", "invalidation",
        "active_bot",
        "range_position", "range_position_zone",
        "expectation", "expectation_text",
        "reasons", "mode_reasons",
        "market_state", "market_state_text",
        "setup_status", "setup_status_text",
        "late_entry_risk", "location_quality",
        "entry_type", "execution_mode",
        "no_trade_reason", "trap_risk",
    ):
        try:
            out[key] = getattr(obj, key)
        except Exception:
            continue
    return out


def _normalize_pct(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        v = float(value)
        if 0.0 <= v <= 1.0:
            v *= 100.0
        return v
    except Exception:
        return default




def _clean_prefixed_text(value: Any, prefix: str) -> str:
    text = str(value or '').strip()
    if not text:
        return 'нет данных'
    pfx = str(prefix or '').strip().lower().rstrip(':')
    cur = text
    while cur.lower().startswith(pfx):
        cur = cur[len(pfx):].strip(' :')
    return cur or 'нет данных'




def _effective_trade_confidence_renderer(decision: Dict[str, Any]) -> float:
    def _pct(value: Any) -> float:
        num = _normalize_pct(value, 0.0)
        return max(0.0, min(num, 100.0))

    final_conf = decision.get('final_confidence')
    if final_conf is not None:
        return _pct(final_conf)

    bias_conf = _pct(decision.get('bias_confidence') or decision.get('confidence_pct') or decision.get('confidence'))
    exec_conf = _pct(decision.get('execution_confidence'))
    setup_conf = _pct(decision.get('setup_readiness'))
    edge = _pct(decision.get('edge_score'))
    edge_label = str(decision.get('edge_label') or '').upper()
    action = str(decision.get('action') or decision.get('action_text') or '').upper()
    trade_authorized = bool(decision.get('trade_authorized'))

    candidates = [x for x in (bias_conf, exec_conf, setup_conf, edge) if x > 0.0]
    effective = min(candidates) if candidates else bias_conf
    if (not trade_authorized) or edge_label == 'NO_EDGE' or edge <= 0.0 or action in {'WAIT', 'WAIT_CONFIRMATION', 'ЖДАТЬ', 'ЖДАТЬ ПОДТВЕРЖДЕНИЕ'}:
        effective = min(effective if effective > 0.0 else bias_conf, 39.0)
    return max(0.0, min(effective, 100.0))


def _manager_action_display(decision: Dict[str, Any]) -> str:
    if bool(decision.get('close_now')):
        return 'ЛУЧШЕ ЗАКРЫТЬ'
    if bool(decision.get('partial_reduce_now')):
        return 'ЧАСТИЧНО ФИКСИРОВАТЬ'

    lifecycle = str(decision.get('lifecycle_state') or decision.get('lifecycle') or '').upper()
    if lifecycle == 'EXIT':
        return 'ЛУЧШЕ ЗАКРЫТЬ'
    if lifecycle == 'REDUCE':
        return 'ЧАСТИЧНО ФИКСИРОВАТЬ'

    manager_text = str(decision.get('manager_action_text') or decision.get('manager_action') or '').strip()
    trade_authorized = bool(decision.get('trade_authorized'))
    exec_conf = _normalize_pct(decision.get('execution_confidence'), 0.0)
    setup_conf = _normalize_pct(decision.get('setup_readiness'), 0.0)
    edge_score = _normalize_pct(decision.get('edge_score'), 0.0)
    if manager_text:
        upper = manager_text.upper()
        if (not trade_authorized) and exec_conf <= 0.0 and setup_conf <= 0.0 and edge_score <= 0.0 and upper in {'ВХОДИТЬ', 'ENTER', 'BUY', 'SELL', 'OPEN'}:
            return 'ЖДАТЬ'
        return manager_text
    return 'ЖДАТЬ'
def _safe_conf_pct(value: Any) -> float:
    pct = _normalize_pct(value, 0.0)
    return max(0.0, min(pct, 100.0))

def _fmt_percent_points(value: Any, digits: int = 2) -> str:
    try:
        if value is None:
            return f"{0.0:.{digits}f}%"
        return f"{float(value):.{digits}f}%"
    except Exception:
        return f"{0.0:.{digits}f}%"


def _plan_side(snapshot: AnalysisSnapshot, decision: Dict[str, Any]) -> str:
    side = _normalize_direction_text(decision.get('direction_text') or decision.get('direction'))
    if side in {'ЛОНГ', 'ШОРТ'}:
        return side
    side = _normalize_direction_text(_safe_get(snapshot, 'forecast_direction', None))
    if side in {'ЛОНГ', 'ШОРТ'}:
        return side
    return 'НЕЙТРАЛЬНО'


def _trade_plan_core(snapshot: AnalysisSnapshot, decision: Dict[str, Any]) -> Dict[str, Any]:
    side = _plan_side(snapshot, decision)
    price = _safe_get(snapshot, 'price', None)
    low = _safe_get(snapshot, 'range_low', None)
    mid = _safe_get(snapshot, 'range_mid', None)
    high = _safe_get(snapshot, 'range_high', None)
    trade_authorized = bool(decision.get('trade_authorized'))

    def _n(x):
        try:
            return float(x) if x is not None else None
        except Exception:
            return None

    price = _n(price)
    low = _n(low)
    mid = _n(mid)
    high = _n(high)
    long_zone = f"{fmt_price(low)}–{fmt_price(mid)}" if low is not None and mid is not None else fmt_price(low)
    short_zone = f"{fmt_price(mid)}–{fmt_price(high)}" if mid is not None and high is not None else fmt_price(high)

    if side not in {'ЛОНГ', 'ШОРТ'}:
        return {
            'side': side, 'entry_zone': 'нет данных', 'trigger': 'ждать край диапазона / подтверждение',
            'stop': None, 'tp1': None, 'tp2': None, 'be': None, 'rr': None,
            'long_zone': long_zone, 'short_zone': short_zone,
        }

    if not trade_authorized:
        entry_zone = long_zone if side == 'ЛОНГ' else short_zone
        return {
            'side': side,
            'entry_zone': entry_zone or 'нет данных',
            'trigger': 'ждать подтверждение у края диапазона: execution ещё не разрешён edge-фильтром',
            'stop': None, 'tp1': None, 'tp2': None, 'be': None, 'rr': None,
            'long_zone': long_zone, 'short_zone': short_zone,
        }

    if side == 'ЛОНГ':
        entry_a = low if low is not None else (price * 0.997 if price is not None else None)
        entry_b = mid if mid is not None else price
        stop = (low * 0.995) if low is not None else (price * 0.992 if price is not None else None)
        tp1 = mid if mid is not None else (price * 1.005 if price is not None else None)
        tp2 = high if high is not None else (price * 1.01 if price is not None else None)
        trigger = 'удержание поддержки + bullish confirm'
    else:
        entry_a = mid if mid is not None else price
        entry_b = high if high is not None else (price * 1.003 if price is not None else None)
        stop = (high * 1.005) if high is not None else (price * 1.008 if price is not None else None)
        tp1 = mid if mid is not None else (price * 0.995 if price is not None else None)
        tp2 = low if low is not None else (price * 0.99 if price is not None else None)
        trigger = 'rejection от сопротивления + bearish confirm'

    rr = None
    try:
        if None not in (entry_a, entry_b, stop, tp2):
            entry_mid = (entry_a + entry_b) / 2.0
            risk = abs(entry_mid - stop)
            reward = abs(tp2 - entry_mid)
            if risk > 0:
                rr = reward / risk
    except Exception:
        rr = None

    lo = min(entry_a, entry_b) if entry_a is not None and entry_b is not None else entry_a
    hi = max(entry_a, entry_b) if entry_a is not None and entry_b is not None else entry_b
    if lo is not None and hi is not None and abs(hi - lo) < 1e-9 and price is not None:
        pad = max(abs(float(price)) * 0.0015, 25.0)
        lo -= pad
        hi += pad
    entry_zone = f"{fmt_price(lo)}–{fmt_price(hi)}" if lo is not None and hi is not None else fmt_price(entry_a)
    return {
        'side': side,
        'entry_zone': entry_zone,
        'trigger': trigger,
        'stop': stop,
        'tp1': tp1,
        'tp2': tp2,
        'be': tp1,
        'rr': rr,
        'long_zone': long_zone,
        'short_zone': short_zone,
    }




def _setup_requirements(snapshot: AnalysisSnapshot, decision: Dict[str, Any]) -> Dict[str, Any]:
    range_state = str(_safe_get(snapshot, 'range_state', '') or '').lower()
    position = str(_safe_get(snapshot, 'range_position', '') or decision.get('range_position') or '').lower()
    low = _safe_get(snapshot, 'range_low', None)
    mid = _safe_get(snapshot, 'range_mid', None)
    high = _safe_get(snapshot, 'range_high', None)
    side = _normalize_direction_text(decision.get('direction_text') or decision.get('direction'))
    impulse_state = str(decision.get('impulse_state') or '').upper()
    edge = _normalize_pct(decision.get('edge_score'), 0.0)
    items = []
    if side == 'ЛОНГ':
        zone = _zone_from_bounds(low, mid, '')
        items.append(f"локация: подход к нижней части диапазона{(' ' + zone) if zone else ''}")
        items.append("нужен false break down / reclaim / bullish confirm")
        items.append("не брать лонг из середины диапазона")
    elif side == 'ШОРТ':
        zone = _zone_from_bounds(mid, high, '')
        items.append(f"локация: подход к верхней части диапазона{(' ' + zone) if zone else ''}")
        items.append("нужен false break up / rejection / bearish confirm")
        items.append("не шортить середину диапазона без возврата под high")
    else:
        items.append("сначала нужен подход к краю диапазона")
        items.append("нужен retest / reclaim / confirm вместо входа из середины шума")
    if 'серед' in position or 'mid' in position:
        items.append("цена в середине диапазона: сначала нужен край диапазона")
    if impulse_state == 'NO_CLEAR_IMPULSE':
        items.append("чистый импульс не собран: ждать подтверждение")
    if edge <= 0.0:
        items.append("edge отсутствует: execution не разрешён")
    return {'items': items[:5]}


def _arming_logic(snapshot: AnalysisSnapshot, decision: Dict[str, Any]) -> Dict[str, Any]:
    position = str(_safe_get(snapshot, 'range_position', '') or decision.get('range_position') or '').lower()
    range_state = str(_safe_get(snapshot, 'range_state', '') or '').lower()
    confirmation = _normalize_pct(decision.get('impulse_confirmation'), 0.0)
    freshness = _normalize_pct(decision.get('impulse_freshness'), 0.0)
    edge = _normalize_pct(decision.get('edge_score'), 0.0)
    reversal_patterns = _safe_get(snapshot, 'reversal_patterns', None) or []
    location_ready = 100 if any(x in position for x in ('high', 'low', 'верх', 'ниж')) else 35 if ('mid' in position or 'серед' in position) else 20
    regime_ready = 100 if ('range' in range_state or 'диапаз' in range_state) else 55
    reversal_ready = 80 if reversal_patterns else 20
    confirm_ready = min(100, int(max(confirmation, freshness * 0.5)))
    edge_ready = min(100, int(edge))
    total = int(round(location_ready*0.30 + regime_ready*0.20 + reversal_ready*0.20 + confirm_ready*0.20 + edge_ready*0.10))
    if total >= 85 and edge >= 55:
        status = 'READY'
    elif total >= 60:
        status = 'ARMING'
    elif total >= 35:
        status = 'WATCH'
    else:
        status = 'OFF'
    blockers = []
    if 'mid' in position or 'серед' in position:
        blockers.append('цена не у края диапазона')
    if str(decision.get('impulse_state') or '').upper() == 'NO_CLEAR_IMPULSE':
        blockers.append('нет чистого импульса / reclaim')
    if edge < 25:
        blockers.append('edge слишком слабый')
    if not reversal_patterns:
        blockers.append('нет reversal-паттерна')
    return {'status': status, 'total': total, 'location_ready': location_ready, 'regime_ready': regime_ready, 'reversal_ready': reversal_ready, 'confirm_ready': confirm_ready, 'blockers': blockers[:4]}


def _volume_range_bot_conditions(snapshot: AnalysisSnapshot, decision: Dict[str, Any]) -> Dict[str, Any]:
    position = str(_safe_get(snapshot, 'range_position', '') or decision.get('range_position') or '').lower()
    range_state = str(_safe_get(snapshot, 'range_state', '') or '').lower()
    grid = _safe_get(snapshot, 'grid_strategy', None) or {}
    if not isinstance(grid, dict):
        grid = {}
    deviation = float(grid.get('deviation_abs_pct') or 0.0)
    trap_risk = str(decision.get('trap_risk') or 'MEDIUM').upper()
    impulse_state = str(decision.get('impulse_state') or '').upper()
    range_detected = ('range' in range_state or 'диапаз' in range_state or 'mid' in position or 'серед' in position or 'high' in position or 'low' in position)
    impulse_faded = impulse_state == 'NO_CLEAR_IMPULSE'
    near_edge = any(x in position for x in ('high', 'low', 'верх', 'ниж'))
    reaccepted = near_edge or (('mid' in position or 'серед' in position) and deviation <= 0.35)
    low_breakout_risk = trap_risk in {'LOW', 'MEDIUM'}
    breakout_penalty_mode = trap_risk == 'HIGH'
    location_state = 'EDGE' if near_edge else 'MID' if ('mid' in position or 'серед' in position) else 'UNKNOWN'
    post_impulse_fade = 'YES' if impulse_faded and deviation >= 0.8 else 'PARTIAL' if impulse_faded else 'NO'
    rotation_quality = 'GOOD' if impulse_faded and reaccepted else 'OK' if impulse_faded or reaccepted else 'BAD'
    if range_detected and near_edge and impulse_faded and low_breakout_risk:
        status = 'READY_SMALL'
    elif range_detected and near_edge and low_breakout_risk:
        status = 'ARMING'
    elif range_detected and ('mid' in position or 'серед' in position) and impulse_faded and rotation_quality in {'GOOD', 'OK'} and deviation <= 0.8:
        status = 'READY_SMALL'
    elif range_detected and impulse_faded and reaccepted and (low_breakout_risk or breakout_penalty_mode):
        status = 'WATCH'
    else:
        status = 'OFF'
    if breakout_penalty_mode and status == 'READY_SMALL':
        status = 'READY_SMALL_REDUCED'
    add_status = 'READY_ADD' if status in {'READY_SMALL', 'READY_SMALL_REDUCED'} and rotation_quality == 'GOOD' and reaccepted and trap_risk != 'HIGH' else 'WAIT_ADD'
    verdict = decision.get('execution_verdict') if isinstance(decision.get('execution_verdict'), dict) else {}
    size_multiplier = 0.3 if trap_risk == 'HIGH' else 0.5 if location_state == 'MID' else 1.0
    if verdict:
        vstatus = str(verdict.get('status') or '').upper()
        if vstatus == 'SOFT_RANGE_REDUCED':
            status = 'READY_SMALL_REDUCED'
        elif vstatus == 'SOFT_RANGE_ALLOWED':
            status = 'READY_SMALL'
        size_multiplier = float(verdict.get('size_multiplier') or size_multiplier)
        add_status = 'READY_ADD' if bool(verdict.get('adds_allowed')) else add_status
    conditions=[
        'режим: range или возврат обратно в диапазон после импульса',
        'локация: лучше у края диапазона, не в середине шума',
        'после сильного импульса ждать затухание и спокойную проторговку',
        'при HIGH breakout risk не выключать всё, а уменьшать размер и запрещать adds',
        'READY_SMALL = старт малым размером, READY_ADD = добавление только после повторного удержания зоны',
    ]
    blockers=[]
    if not near_edge and deviation < 0.5:
        blockers.append('цена в середине диапазона без выноса')
    if deviation >= 0.8 and not impulse_faded:
        blockers.append('импульс ещё не погас')
    if trap_risk == 'HIGH':
        blockers.append('высокий breakout risk: только reduced size, без adds')
    return {'status': status, 'add_status': add_status, 'deviation': deviation, 'range_detected': 'YES' if range_detected else 'NO', 'location_state': location_state, 'post_impulse_fade': post_impulse_fade, 'breakout_risk': trap_risk, 'rotation_quality': rotation_quality, 'size_multiplier': round(size_multiplier, 2), 'conditions': conditions, 'blockers': blockers[:3]}

def _build_action_first_block(snapshot: AnalysisSnapshot, decision: Dict[str, Any]) -> Dict[str, str]:
    plan = _trade_plan_core(snapshot, decision)
    direction = _normalize_direction_text(decision.get('direction_text') or decision.get('direction'))
    action = str(decision.get('action_text') or decision.get('action') or 'ЖДАТЬ')
    mode = str(decision.get('mode') or decision.get('regime') or 'MIXED')
    trap_risk = str(decision.get('trap_risk') or 'MEDIUM').upper()
    late_risk = str(decision.get('late_entry_risk') or 'MEDIUM').upper()
    range_position = str(decision.get('range_position') or _safe_get(snapshot, 'range_position', '') or '').upper()
    invalidation = str(decision.get('invalidation') or decision.get('scenario_invalidation') or '').strip()
    no_trade_reason = str(decision.get('no_trade_reason') or '').strip()

    if trap_risk == 'HIGH' or late_risk == 'HIGH' or range_position == 'MID':
        what_now = 'ЖДАТЬ ПОДТВЕРЖДЕНИЕ'
    elif action in {'ВХОДИТЬ', 'ENTER', 'WATCH', 'СМОТРЕТЬ СЕТАП'} and direction in {'ЛОНГ', 'ШОРТ'}:
        what_now = f'СМОТРЕТЬ {direction}'
    else:
        what_now = action

    if range_position == 'MID':
        not_now = 'не входить из середины диапазона'
    elif late_risk == 'HIGH':
        not_now = 'не входить в догонку'
    elif trap_risk == 'HIGH':
        not_now = 'не форсировать без подтверждения'
    else:
        not_now = 'не гнаться за свечой'

    zone = plan['entry_zone'] or ('нет данных' if direction == 'НЕЙТРАЛЬНО' else (plan['long_zone'] if direction == 'ЛОНГ' else plan['short_zone']))
    if (not zone or zone == 'нет данных') and direction in {'ЛОНГ', 'ШОРТ'}:
        low = _safe_get(snapshot, 'range_low', None)
        mid = _safe_get(snapshot, 'range_mid', None)
        high = _safe_get(snapshot, 'range_high', None)
        zone = _zone_from_bounds(low, mid) if direction == 'ЛОНГ' else _zone_from_bounds(mid, high)
        if zone == 'нет данных':
            zone = f"рядом с {'low' if direction == 'ЛОНГ' else 'high'} диапазона {fmt_price(low if direction == 'ЛОНГ' else high)}" if (low if direction == 'ЛОНГ' else high) is not None else 'нет данных'
    zone = zone or 'нет данных'
    trigger = _clean_prefixed_text(plan['trigger'] or 'ждать подтверждение', 'trigger')
    if not invalidation:
        if direction == 'ЛОНГ':
            invalidation = f'уход ниже {fmt_price(plan["stop"])}' if plan.get('stop') is not None else 'срыв реакции от поддержки'
        elif direction == 'ШОРТ':
            invalidation = f'уход выше {fmt_price(plan["stop"])}' if plan.get('stop') is not None else 'возврат выше сопротивления'
        else:
            invalidation = 'пока цена в середине диапазона — активного сценария нет'

    invalidation = _clean_prefixed_text(invalidation, 'инвалидация')
    summary = no_trade_reason or str(decision.get('summary') or '').strip() or 'ждать более чистый сетап'
    return {
        'what_now': what_now,
        'direction': direction,
        'mode': mode,
        'zone': zone,
        'trigger': trigger,
        'invalidation': invalidation,
        'not_now': not_now,
        'summary': summary,
    }


def _build_quick_action_lines(snapshot: AnalysisSnapshot, decision: Dict[str, Any]) -> list[str]:
    action_block = _build_action_first_block(snapshot, decision)
    grid_strategy = _safe_get(snapshot, 'grid_strategy', None)
    active_bots = []
    if isinstance(grid_strategy, dict):
        active_bots = list(grid_strategy.get('active_bots') or [])
    bots_text = ', '.join(active_bots) if active_bots else 'все OFF'
    return [
        '⚡ ACTION-FIRST',
        '',
        f"Что делать: {action_block['what_now']}",
        f"Рабочая сторона: {action_block['direction']}",
        f"Режим: {action_block['mode']}",
        f"Рабочая зона: {action_block['zone']}",
        f"Триггер: {action_block['trigger']}",
        f"Инвалидация: {action_block['invalidation']}",
        f"Запрет: {action_block['not_now']}",
        f"Боты: {bots_text}",
    ]




def _trade_scenarios_block(snapshot: AnalysisSnapshot, decision: Dict[str, Any]) -> list[str]:
    direction = _normalize_direction_text(decision.get('direction_text') or decision.get('direction'))
    low = _safe_get(snapshot, 'range_low', None)
    mid = _safe_get(snapshot, 'range_mid', None)
    high = _safe_get(snapshot, 'range_high', None)
    fake_move = _safe_get(snapshot, 'fake_move_detector', None) or decision.get('fake_move_detector') or {}
    fake_type = str(fake_move.get('type') or '').upper()
    fake_action = str(fake_move.get('action') or '').strip()
    scenarios: list[str] = ['⚡ ACTION-FIRST:']

    def _band(a: Any, b: Any, upper: bool) -> str:
        try:
            lo = float(min(a, b))
            hi = float(max(a, b))
        except Exception:
            return _zone_from_bounds(a, b) or 'нет данных'
        width = hi - lo
        if width <= 0:
            return _zone_from_bounds(lo, hi) or 'нет данных'
        if upper:
            z1 = hi - width * 0.18
            z2 = hi
        else:
            z1 = lo
            z2 = lo + width * 0.18
        return _zone_from_bounds(z1, z2) or 'нет данных'

    short_trigger = 'ложный пробой high + возврат под уровень + нет follow-through'
    if fake_type in {'FAKE_BREAK', 'FAKE_BREAK_UP', 'UP_TRAP'}:
        short_trigger = f'ложный вынос вверх подтверждён: {fake_action or "можно смотреть short"}'
    elif direction == 'ШОРТ':
        short_trigger = 'подход к high + rejection / bearish confirm + возврат под high'

    long_trigger = 'пролив к low + быстрый reclaim + удержание low'
    if fake_type in {'FAKE_BREAK_DOWN', 'DOWN_TRAP'}:
        long_trigger = f'ложный вынос вниз подтверждён: {fake_action or "можно смотреть long"}'

    if high is not None and low is not None:
        scenarios.extend([
            'SHORT:',
            f"• зона: {_band(mid if mid is not None else low, high, upper=True)}",
            f"• триггер: {short_trigger}",
            '• вход: только после rejection / возврата под high / микрослома структуры',
            f"• отмена: закрепление выше {fmt_price(high)}",
        ])
        scenarios.extend([
            'LONG:',
            f"• зона: {_band(low, mid if mid is not None else high, upper=False)}",
            f"• триггер: {long_trigger}",
            '• вход: только после reclaim / удержания low / подтверждающей свечи',
            f"• отмена: закрепление ниже {fmt_price(low)}",
        ])
    else:
        plan = _trade_plan_core(snapshot, decision)
        trigger = plan.get('trigger') or 'ждать подтверждение'
        if high is not None:
            scenarios.extend([
                'SHORT:',
                f"• зона: {_zone_from_bounds(mid, high) if mid is not None else _zone_from_bounds(high, high)}",
                f"• триггер: {trigger if direction == 'ШОРТ' else short_trigger}",
                '• вход: после rejection / возврата под high',
                f"• отмена: закрепление выше {fmt_price(high)}",
            ])
        if low is not None:
            scenarios.extend([
                'LONG:',
                f"• зона: {_zone_from_bounds(low, mid) if mid is not None else _zone_from_bounds(low, low)}",
                f"• триггер: {long_trigger}",
                '• вход: после подтверждённого возврата',
                f"• отмена: закрепление ниже {fmt_price(low)}",
            ])
    return scenarios if len(scenarios) > 1 else []


def _manual_actions_block(snapshot: AnalysisSnapshot, decision: Dict[str, Any]) -> list[str]:
    actions: list[str] = []
    edge = _normalize_pct(decision.get('edge_score') or 0.0)
    authority = bool(decision.get('trade_authorized'))
    if edge <= 0.0 or not authority:
        actions.append('не входить без подтверждения')
    if bool(decision.get('partial_reduce_now')):
        actions.append('частично фиксировать позицию')
    elif bool(decision.get('close_now')):
        actions.append('закрыть позицию')
    elif str(_manager_action_display(decision)).upper() not in {'ЖДАТЬ', 'WAIT'}:
        actions.append(_manager_action_display(decision).lower())
    actions.append('ждать край диапазона / retest')
    actions.append('не гнаться за движением из середины диапазона')
    dedup=[]
    for a in actions:
        if a and a not in dedup:
            dedup.append(a)
    return ['⚡ СЕЙЧАС ДЕЛАТЬ:'] + [f'• {a}' for a in dedup[:4]]


def _entry_score_block(snapshot: AnalysisSnapshot, decision: Dict[str, Any]) -> list[str]:
    arming = _arming_logic(snapshot, decision)
    location_ready = float(arming.get('location_ready') or 0.0)
    regime_ready = float(arming.get('regime_ready') or 0.0)
    reversal_ready = float(arming.get('reversal_ready') or 0.0)
    confirm_ready = float(arming.get('confirm_ready') or 0.0)
    edge = _normalize_pct(decision.get('edge_score') or 0.0)
    trap = _normalize_pct(decision.get('trap_risk_score') or 0.0)
    late = _normalize_pct(decision.get('late_entry_risk') or decision.get('late_entry_risk_score') or 0.0)
    score = location_ready * 0.22 + regime_ready * 0.18 + reversal_ready * 0.22 + confirm_ready * 0.28 + min(edge, 100.0) * 0.10
    score -= trap * 0.18
    score -= late * 0.10
    score = max(0.0, min(100.0, score))
    if score >= 72.0 and bool(decision.get('trade_authorized')):
        verdict = 'можно входить только по trigger'
    elif score >= 55.0:
        verdict = 'ещё рано, но сценарий можно готовить'
    else:
        verdict = 'вход не готов / ждать подтверждение'
    return [
        'ENTRY SCORE:',
        f'• score: {score:.1f}/100',
        f'• location: {location_ready:.0f}%',
        f'• reversal: {reversal_ready:.0f}%',
        f'• confirmation: {confirm_ready:.0f}%',
        f'• verdict: {verdict}',
    ]


def _tp_probability_block(tp1: Any, tp2: Any, rr: Any, continuation_prob: Any = None, exhaustion_prob: Any = None) -> list[str]:
    cont = _normalize_pct(continuation_prob, 0.0)
    ex = _normalize_pct(exhaustion_prob, 0.0)
    try:
        rr_val = float(rr) if rr is not None else None
    except Exception:
        rr_val = None
    tp1_prob = max(0.0, min(92.0, cont * 0.85 + 12.0)) if tp1 is not None else 0.0
    tp2_prob = 0.0
    if tp2 is not None:
        base = cont * 0.62 - ex * 0.20 + (8.0 if rr_val is not None and rr_val <= 2.2 else 0.0)
        tp2_prob = max(0.0, min(78.0, base))
    lines = ['TP MAP:']
    lines.append(f"• вероятность TP1: {tp1_prob:.1f}%" if tp1 is not None else '• вероятность TP1: нет данных')
    lines.append(f"• вероятность TP2: {tp2_prob:.1f}%" if tp2 is not None else '• вероятность TP2: нет данных')
    lines.append(f"• RR to TP2: {rr_val:.2f}" if rr_val is not None else '• RR to TP2: нет данных')
    return lines


def _manual_exit_map(tp1: Any, tp2: Any, be: Any, invalidation: Any, decision: Dict[str, Any]) -> list[str]:
    lines = ['РУЧНАЯ ФИКСАЦИЯ:']
    if tp1 is not None:
        lines.append(f"• TP1 зона: {fmt_price(tp1)} → снять 25-35%")
    else:
        lines.append('• TP1 зона: нет данных')
    if be is not None:
        lines.append(f"• после TP1: защитить остаток через BE {fmt_price(be)}")
    else:
        lines.append('• после TP1: перенести риск в BE при первом чистом импульсе')
    if tp2 is not None:
        lines.append(f"• TP2 зона: {fmt_price(tp2)} → основная фиксация / оценка продолжения")
    else:
        lines.append('• TP2 зона: нет данных')
    if invalidation is not None:
        lines.append(f"• отмена сценария: {fmt_price(invalidation)}")
    else:
        lines.append(f"• отмена сценария: {decision.get('invalidation') or 'нет данных'}")
    return lines
def _normalize_direction_text(value: Any) -> str:
    raw = str(value or '').strip().upper()
    if raw in {'LONG', 'ЛОНГ', 'UP', 'ВВЕРХ'}:
        return 'ЛОНГ'
    if raw in {'SHORT', 'ШОРТ', 'DOWN', 'ВНИЗ'}:
        return 'ШОРТ'
    return 'НЕЙТРАЛЬНО'


def _sync_forecast_strength(direction: Any, confidence: Any, current: Any = None) -> str:
    current_text = str(current or '').strip().upper()
    if current_text and current_text != 'NEUTRAL':
        return current_text
    direction_text = _normalize_direction_text(direction)
    conf = _normalize_pct(confidence, 0.0)
    if direction_text == 'НЕЙТРАЛЬНО' or conf < 52.0:
        return 'NEUTRAL'
    if conf >= 70.0:
        return 'STRONG'
    if conf >= 58.0:
        return 'MODERATE'
    return 'WEAK'


def _append_v52_overlay_blocks(lines: list[str], snapshot: AnalysisSnapshot, decision: Dict[str, Any]) -> None:
    soft_signal = _safe_get(snapshot, 'soft_signal', None) or decision.get('soft_signal') or {}
    if isinstance(soft_signal, dict) and soft_signal.get('active'):
        lines.extend([
            '',
            'SOFT SIGNAL LAYER:',
            f"• status: {soft_signal.get('status') or 'SOFT_SIGNAL'}",
            f"• side: {soft_signal.get('side') or 'NEUTRAL'}",
            f"• score: {fmt_pct(soft_signal.get('score') or 0.0)}",
            f"• summary: {soft_signal.get('summary') or 'нет данных'}",
            f"• trigger: {soft_signal.get('trigger') or 'ждать подтверждение'}",
        ])

    fake_move = _safe_get(snapshot, 'fake_move_detector', None) or decision.get('fake_move_detector') or {}
    if isinstance(fake_move, dict):
        lines.extend([
            '',
            'FAKE MOVE DETECTOR:',
            f"• type: {fake_move.get('type') or 'UNCONFIRMED'}",
            f"• confidence: {fmt_pct(fake_move.get('confidence') or 0.0)}",
            f"• bias: {fake_move.get('side_hint') or 'NEUTRAL'}",
            f"• summary: {fake_move.get('summary') or 'нет данных'}",
            f"• action: {fake_move.get('action') or 'ждать'}",
        ])

    move_projection = _safe_get(snapshot, 'move_projection', None) or decision.get('move_projection') or {}
    if isinstance(move_projection, dict):
        target_price = move_projection.get('target_price')
        invalidation = move_projection.get('invalidation')
        lines.extend([
            '',
            'MOVE PROJECTION:',
            f"• mode: {move_projection.get('mode') or 'NO_EDGE'}",
            f"• side: {move_projection.get('side') or 'NEUTRAL'}",
            f"• expected move: {fmt_pct(move_projection.get('expected_move_pct') or 0.0)}",
            f"• target zone: {move_projection.get('target_zone') or 'нет данных'}",
            f"• target price: {fmt_price(target_price) if target_price is not None else 'нет данных'}",
            f"• invalidation: {fmt_price(invalidation) if invalidation is not None else 'нет данных'}",
            f"• summary: {move_projection.get('summary') or 'нет данных'}",
        ])


def _fallback_impulse_block(snapshot: Any, decision: Dict[str, Any]) -> Dict[str, Any]:
    state = str(decision.get('impulse_state') or '').strip().upper()
    comment = str(decision.get('impulse_comment') or '').strip()
    strength = decision.get('impulse_strength')
    freshness = decision.get('impulse_freshness')
    exhaustion = decision.get('impulse_exhaustion')
    confirmation = decision.get('impulse_confirmation')
    direction = _normalize_direction_text(decision.get('direction_text') or decision.get('direction') or _safe_get(snapshot, 'forecast_direction', None))
    conf = _normalize_pct(decision.get('confidence_pct') or decision.get('confidence') or _safe_get(snapshot, 'forecast_confidence', None), 0.0)
    range_state = str(_safe_get(snapshot, 'range_state', '') or '').lower()
    if not state or state == 'UNKNOWN':
        if direction in {'ЛОНГ', 'ШОРТ'} and conf >= 52.0:
            state = 'PENDING_CONFIRMATION'
        else:
            state = 'NO_CLEAR_IMPULSE'
    if not comment:
        if state == 'PENDING_CONFIRMATION':
            comment = 'есть локальное давление, но без чистого триггера'
        elif 'серед' in range_state:
            comment = 'чистый импульс не собран, рынок ближе к range-логике'
        else:
            comment = 'чистый импульс не собран'
    if strength is None:
        strength = 0.35 if state == 'PENDING_CONFIRMATION' else 0.18
    if freshness is None:
        freshness = 0.52 if state == 'PENDING_CONFIRMATION' else 0.25
    if exhaustion is None:
        exhaustion = 0.20 if state == 'PENDING_CONFIRMATION' else 0.10
    if confirmation is None:
        confirmation = 0.0
    return {
        'state': state,
        'comment': comment,
        'strength': strength,
        'freshness': freshness,
        'exhaustion': exhaustion,
        'confirmation': confirmation,
    }


def _ru_market_state(value: Any) -> str:
    v = str(value or "UNKNOWN").upper()
    return {
        "UNKNOWN": "НЕДОСТАТОЧНО ДАННЫХ",
        "NEUTRAL": "БЕЗ ПЕРЕВЕСА",
        "CONFLICTED": "КОНФЛИКТ ФАКТОРОВ",
        "BIASED": "ЕСТЬ ПЕРЕВЕС",
    }.get(v, str(value or "UNKNOWN"))


def _ru_setup_status(value: Any) -> str:
    v = str(value or "WAIT").upper()
    return {
        "VALID": "СЕТАП ВАЛИДЕН",
        "EARLY": "РАНО / НУЖНО ПОДТВЕРЖДЕНИЕ",
        "LATE": "ПОЗДНИЙ ВХОД",
        "INVALID": "НЕ ЛЕЗТЬ / КОНФЛИКТ",
        "WAIT": "ЖДАТЬ",
    }.get(v, str(value or "WAIT"))


def _ru_risk(value: Any) -> str:
    v = str(value or "MEDIUM").upper()
    return {"LOW": "LOW", "MEDIUM": "MEDIUM", "HIGH": "HIGH"}.get(v, v)


def _ru_entry_type(value: Any) -> str:
    v = str(value or "no_trade").lower()
    return {
        "breakout": "пробой / продолжение",
        "pullback": "откат / добор от уровня",
        "reversal": "разворотный вход",
        "no_trade": "без входа",
    }.get(v, v)


def _ru_execution_mode(value: Any) -> str:
    v = str(value or "conservative").lower()
    return {
        "aggressive": "агрессивный",
        "balanced": "сбалансированный",
        "conservative": "консервативный",
    }.get(v, v)


def _what_to_wait_for(decision: Dict[str, Any]) -> list[str]:
    items: list[str] = []
    setup = str(decision.get("setup_status") or "").upper()
    market_state = str(decision.get("market_state") or "").upper()
    entry_type = str(decision.get("entry_type") or "no_trade").lower()
    late_risk = str(decision.get("late_entry_risk") or "MEDIUM").upper()
    trap_risk = str(decision.get("trap_risk") or "MEDIUM").upper()
    location_quality = str(decision.get("location_quality") or "C").upper()

    if market_state == "UNKNOWN":
        items.append("сначала нужен более понятный directional-перевес")
    if market_state == "CONFLICTED":
        items.append("нужно исчезновение конфликта между trend / reversal / location")
    if setup == "EARLY":
        items.append("нужна подтверждающая свеча или удержание уровня")
    if setup == "LATE":
        items.append("лучше ждать откат, а не входить в догонку")
    if location_quality in {"C", "D"}:
        items.append("желательно смещение цены ближе к краю диапазона или к зоне реакции")
    if entry_type == "breakout":
        items.append("вход только после удержания пробоя, не на первой эмоции")
    elif entry_type == "pullback":
        items.append("лучше входить после отката и реакции от уровня")
    elif entry_type == "reversal":
        items.append("нужен подтверждённый разворот, не просто одна встречная свеча")
    if trap_risk == "HIGH":
        items.append("есть риск ловушки, поэтому без подтверждения лучше не входить")
    if late_risk == "HIGH":
        items.append("вход в текущей точке запоздалый")

    deduped: list[str] = []
    for item in items:
        if item and item not in deduped:
            deduped.append(item)
    return deduped[:5]


def _edge_lines(decision: Dict[str, Any]) -> list[str]:
    edge_score = _normalize_pct(decision.get("edge_score"))
    edge_label = str(decision.get("edge_label") or "NO_EDGE").upper()
    edge_action = str(decision.get("edge_action") or "WAIT").upper()
    edge_side = str(decision.get("edge_side") or decision.get("direction_text") or decision.get("direction") or "NEUTRAL").upper()
    label_map = {
        "NO_EDGE": "нет edge",
        "WEAK": "слабый edge",
        "WORKABLE": "рабочий edge",
        "STRONG": "сильный edge",
    }
    action_map = {
        "WAIT": "ждать",
        "WAIT_CONFIRMATION": "ждать подтверждение",
        "WAIT_RANGE_EDGE": "ждать край диапазона",
        "ALLOW_ENTRY": "можно искать вход",
        "READY": "готово к исполнению",
    }
    side_map = {"LONG": "ЛОНГ", "SHORT": "ШОРТ", "NEUTRAL": "НЕЙТРАЛЬНО", "NONE": "НЕЙТРАЛЬНО"}
    lines = [
        "",
        "EDGE SCORE:",
        f"• score: {edge_score:.1f}%",
        f"• label: {edge_label} / {label_map.get(edge_label, edge_label.lower())}",
        f"• side: {side_map.get(edge_side, edge_side)}",
        f"• action: {action_map.get(edge_action, edge_action)}",
    ]
    components = decision.get("edge_components") or {}
    if isinstance(components, dict):
        mapped = [
            ("delta_score", "delta"),
            ("confidence", "confidence"),
            ("location", "location"),
            ("impulse", "impulse"),
            ("alignment", "alignment"),
            ("penalty", "penalty"),
        ]
        for key, label in mapped:
            if key in components and components.get(key) is not None:
                try:
                    value = float(components.get(key) or 0.0)
                    sign = "+" if value > 0 else ""
                    lines.append(f"• {label}: {sign}{value:.1f}")
                except Exception:
                    continue
    return lines


def _append_decision_detail_blocks(lines: list[str], decision: Dict[str, Any]) -> None:
    market_state_text = decision.get("market_state_text") or _ru_market_state(decision.get("market_state"))
    setup_status_text = decision.get("setup_status_text") or _ru_setup_status(decision.get("setup_status"))
    impulse_block = _fallback_impulse_block({}, decision)
    lines.extend([
        "",
        "MARKET STATE:",
        f"• состояние рынка: {market_state_text}",
        f"• перевес: {decision.get('direction_text') or decision.get('direction') or 'НЕЙТРАЛЬНО'}",
        f"• confidence: {_effective_trade_confidence_renderer(decision):.1f}%",
        f"• risk: {_ru_risk(decision.get('risk_level') or decision.get('risk') or 'HIGH')}",
        "",
        "SETUP STATUS:",
        f"• статус: {setup_status_text}",
        f"• quality: {decision.get('location_quality') or 'C'}",
        f"• late entry risk: {_ru_risk(decision.get('late_entry_risk') or 'MEDIUM')}",
        f"• trap risk: {_ru_risk(decision.get('trap_risk') or 'MEDIUM')}",
        "",
        "IMPULSE STATE:",
        f"• состояние: {impulse_block.get('state') or 'NO_CLEAR_IMPULSE'}",
        f"• комментарий: {impulse_block.get('comment') or 'чистый импульс не собран'}",
        f"• сила: {_normalize_pct(impulse_block.get('strength')):.1f}%",
        f"• свежесть: {_normalize_pct(impulse_block.get('freshness')):.1f}%",
        f"• затухание: {_normalize_pct(impulse_block.get('exhaustion')):.1f}%",
        f"• подтверждение: {_normalize_pct(impulse_block.get('confirmation')):.1f}%",
        "",
        "EXECUTION PROFILE:",
        f"• тип входа: {_ru_entry_type(decision.get('entry_type'))}",
        f"• режим исполнения: {_ru_execution_mode(decision.get('execution_mode'))}",
        "",
        "MARKET REGIME ENGINE:",
        f"• режим: {decision.get('market_regime_text') or 'ПЕРЕХОДНЫЙ РЕЖИМ'}",
        f"• bias режима: {decision.get('market_regime_bias') or 'НЕЙТРАЛЬНО'}",
        f"• confidence режима: {_normalize_pct(decision.get('market_regime_confidence')):.1f}%" if decision.get('market_regime_confidence') is not None else "• confidence режима: нет данных",
        f"• комментарий: {decision.get('market_regime_summary') or 'нет комментария'}",
    ])

    no_trade_reason = str(decision.get("no_trade_reason") or "").strip()
    should_wait = _what_to_wait_for(decision)
    if no_trade_reason or should_wait:
        lines.extend(["", "WHY NO TRADE:"])
        lines.append(f"• причина: {no_trade_reason or 'нужен более чистый сетап'}")
        if str(decision.get('late_entry_risk') or '').upper() == 'HIGH':
            lines.append('• исполнение: вход уже поздний, лучше ждать откат / re-entry')
        if str(decision.get('trap_risk') or '').upper() == 'HIGH':
            lines.append('• исполнение: без подтверждения лучше рассчитывать только на scalp / partial')
        for item in should_wait[:4]:
            lines.append(f"• что должно измениться: {item}")




def _forecast_context_blocks(snapshot: AnalysisSnapshot, decision: Dict[str, Any]) -> Dict[str, list[str]]:
    support: list[str] = []
    oppose: list[str] = []
    invalidation: list[str] = []

    long_score = _normalize_pct(decision.get('long_score'))
    short_score = _normalize_pct(decision.get('short_score'))
    forecast_direction = str(_safe_get(snapshot, 'forecast_direction', '') or decision.get('direction_text') or decision.get('direction') or '').upper()
    range_state = str(_safe_get(snapshot, 'range_state', '') or '')
    ginarea = str(_safe_get(snapshot, 'ginarea_advice', '') or '')
    ct_now = str(_safe_get(snapshot, 'ct_now', '') or '')
    reversal_patterns = [str(x) for x in (_safe_get(snapshot, 'reversal_patterns', None) or [])]
    market_regime = str(decision.get('market_regime') or '')
    market_regime_bias = str(decision.get('market_regime_bias') or '')
    impulse_state = str(decision.get('impulse_state') or '')
    mtf_state = str(decision.get('mtf_state') or '')
    scenario_invalidation = str(decision.get('scenario_invalidation') or decision.get('invalidation') or '').strip()

    if long_score >= short_score + 8:
        support.append(f"long score сильнее: {long_score:.1f}% против {short_score:.1f}%")
    elif short_score >= long_score + 8:
        support.append(f"short score сильнее: {short_score:.1f}% против {long_score:.1f}%")
    else:
        oppose.append('score почти сбалансированы, перевес пока неустойчив')

    if 'верх' in range_state.lower() or 'high' in range_state.lower() or 'сопротив' in range_state.lower():
        oppose.append('цена у верхней части диапазона, продавец может защищать high')
        invalidation.append('закрепление выше high усилит сценарий continuation и ослабит short-идею')
    elif 'низ' in range_state.lower() or 'low' in range_state.lower() or 'поддерж' in range_state.lower():
        support.append('цена ближе к поддержке, покупатель может защищать low')
        invalidation.append('закрепление ниже low ухудшит long-идею и усилит давление вниз')
    elif 'середина диапазона' in range_state.lower() or 'середина' in range_state.lower():
        oppose.append('цена в середине диапазона, edge слабее обычного')

    if reversal_patterns:
        joined = ', '.join(reversal_patterns[:2]).lower()
        if 'bearish' in joined or 'rejection у локального high' in joined:
            oppose.append('локальный bearish shift / rejection мешает лонговому продолжению')
        if 'bullish' in joined or 'rejection у локального low' in joined:
            support.append('локальный bullish shift поддерживает попытку отскока')

    if impulse_state:
        if 'BULLISH' in impulse_state.upper():
            support.append('импульс поддерживает движение вверх')
        elif 'BEARISH' in impulse_state.upper():
            support.append('импульс поддерживает движение вниз')
        elif 'FADING' in impulse_state.upper():
            oppose.append('импульс выдыхается, вход в догонку хуже по качеству')
        elif 'CONFLICTED' in impulse_state.upper() or 'RANGE' in impulse_state.upper():
            oppose.append('по импульсу нет чистой поддержки направления')

    if market_regime_bias and market_regime_bias.upper() not in {'NEUTRAL', 'НЕЙТРАЛЬНО', 'NONE'}:
        support.append(f'режим рынка склоняется в сторону: {market_regime_bias}')
    if market_regime and market_regime.lower() in {'compression', 'range_rotation'}:
        oppose.append(f'режим {market_regime} чаще даёт шум, чем чистое продолжение')

    if mtf_state:
        if mtf_state.upper() == 'ALIGNED':
            support.append('таймфреймы согласованы между собой')
        elif mtf_state.upper() in {'CONFLICTED', 'COUNTERTREND_PRESSURE'}:
            oppose.append('таймфреймы спорят между собой, давление разнонаправленное')

    if ginarea:
        if 'сопротив' in ginarea.lower():
            oppose.append('ginarea указывает на близкое сопротивление')
        elif 'поддерж' in ginarea.lower():
            support.append('ginarea указывает на близкую поддержку')

    if ct_now and 'явного перекоса нет' in ct_now.lower():
        oppose.append('контртренд пока не даёт явного перекоса')

    if scenario_invalidation:
        invalidation.append(scenario_invalidation)

    def _dedupe(items: list[str]) -> list[str]:
        out = []
        for item in items:
            if item and item not in out:
                out.append(item)
        return out[:4]

    return {
        'support': _dedupe(support),
        'oppose': _dedupe(oppose),
        'invalidation': _dedupe(invalidation),
    }


def _infer_soft_bias(snapshot: AnalysisSnapshot, decision: Dict[str, Any]) -> tuple[str, str]:
    long_score = _normalize_pct(decision.get('long_score'))
    short_score = _normalize_pct(decision.get('short_score'))
    diff = long_score - short_score
    if diff >= 8:
        return 'ЛОНГ', f'long score сильнее: {long_score:.1f}% против {short_score:.1f}%'
    if diff <= -8:
        return 'ШОРТ', f'short score сильнее: {short_score:.1f}% против {long_score:.1f}%'

    range_state = str(_safe_get(snapshot, 'range_state', '') or '').lower()
    ct_now = str(_safe_get(snapshot, 'ct_now', '') or '').lower()
    ginarea = str(_safe_get(snapshot, 'ginarea_advice', '') or '').lower()
    reversal_patterns = [str(x).lower() for x in (_safe_get(snapshot, 'reversal_patterns', None) or [])]
    pattern_dir = str(_safe_get(snapshot, 'pattern_forecast_direction', None) or _safe_get(snapshot, 'history_pattern_direction', None) or '').upper()
    market_regime_bias = str(decision.get('market_regime_bias') or '').upper()
    scenario_text = ' '.join([
        str(decision.get('scenario_text') or ''),
        str(decision.get('base_case') or ''),
        str(decision.get('bear_case') or ''),
        str(decision.get('bull_case') or ''),
        str(decision.get('trigger_text') or ''),
        str(decision.get('trigger_down') or ''),
        str(decision.get('trigger_up') or ''),
        ' '.join([str(x) for x in (decision.get('expectation') or [])[:3]]),
    ]).lower()

    short_votes = 0
    long_votes = 0
    reasons_short = []
    reasons_long = []

    if any(x in scenario_text for x in ['вниз', 'down', 'продав', 'short', 'ниже', 'удержание локального high', 'свеча продолжения вниз']):
        short_votes += 2
        reasons_short.append('текстовый сценарий смотрит вниз')
    if any(x in scenario_text for x in ['вверх', 'up', 'покуп', 'long', 'выше', 'удержание локального low', 'свеча продолжения вверх']):
        long_votes += 2
        reasons_long.append('текстовый сценарий смотрит вверх')
    if 'верх' in range_state or 'сопротив' in range_state:
        short_votes += 1
        reasons_short.append('цена ближе к верхней части диапазона')
    elif 'низ' in range_state or 'поддерж' in range_state:
        long_votes += 1
        reasons_long.append('цена ближе к поддержке')
    if 'поддерж' in ginarea:
        long_votes += 1
        reasons_long.append('ginarea указывает на близкую поддержку')
    if 'сопротив' in ginarea:
        short_votes += 1
        reasons_short.append('ginarea указывает на близкое сопротивление')
    if any('bearish' in x or 'rejection у локального high' in x for x in reversal_patterns):
        short_votes += 1
        reasons_short.append('есть bearish shift / rejection у high')
    if any('bullish' in x or 'rejection у локального low' in x for x in reversal_patterns):
        long_votes += 1
        reasons_long.append('есть bullish shift / rejection у low')
    if market_regime_bias in {'SHORT', 'DOWN', 'BEARISH', 'ШОРТ'}:
        short_votes += 1
        reasons_short.append('режим рынка склоняется вниз')
    elif market_regime_bias in {'LONG', 'UP', 'BULLISH', 'ЛОНГ'}:
        long_votes += 1
        reasons_long.append('режим рынка склоняется вверх')
    if pattern_dir in {'SHORT', 'DOWN', 'BEARISH', 'ШОРТ'}:
        short_votes += 1
        reasons_short.append('паттерн-память поддерживает short bias')
    elif pattern_dir in {'LONG', 'UP', 'BULLISH', 'ЛОНГ'}:
        long_votes += 1
        reasons_long.append('паттерн-память поддерживает long bias')
    if 'явного перекоса нет' in ct_now:
        pass

    if short_votes >= long_votes + 1 and short_votes >= 2:
        return 'СЛАБЫЙ ШОРТ', reasons_short[0]
    if long_votes >= short_votes + 1 and long_votes >= 2:
        return 'СЛАБЫЙ ЛОНГ', reasons_long[0]
    return 'НЕЙТРАЛЬНО', 'score почти равны'


def _resolved_forecast_direction(snapshot: AnalysisSnapshot, decision: Dict[str, Any]) -> str:
    raw = _normalize_direction_text(_safe_get(snapshot, 'forecast_direction', '') or decision.get('direction_text') or decision.get('direction') or 'НЕЙТРАЛЬНО')
    if raw != 'НЕЙТРАЛЬНО':
        return raw
    bias, _ = _infer_soft_bias(snapshot, decision)
    return bias


def _bias_block(snapshot: AnalysisSnapshot, decision: Dict[str, Any]) -> tuple[str, str]:
    bias, reason = _infer_soft_bias(snapshot, decision)
    if bias == 'НЕЙТРАЛЬНО':
        return bias, 'score почти равны'
    return bias, reason


def _quality_summary_line(snapshot: AnalysisSnapshot, decision: Dict[str, Any]) -> str:
    direction = _resolved_forecast_direction(snapshot, decision)
    strength = _sync_forecast_strength(direction, _safe_get(snapshot, 'forecast_confidence', None) or decision.get('confidence_pct') or decision.get('confidence'), _safe_get(snapshot, 'forecast_strength', '') or decision.get('forecast_strength') or 'NEUTRAL')
    action = str(decision.get('action_text') or decision.get('action') or 'ЖДАТЬ')
    range_state = str(_safe_get(snapshot, 'range_state', '') or '')
    impulse_state = str(decision.get('impulse_state') or '')
    if action.upper() in {'WAIT', 'ЖДАТЬ'}:
        if 'середина' in range_state.lower():
            return f'Базовый перевес: {direction} / {strength}, но цена в середине диапазона — лучше ждать край или retest.'
        if 'FADING' in impulse_state.upper():
            return f'Базовый перевес: {direction} / {strength}, но импульс затухает — входить в догонку не лучший момент.'
        return f'Базовый перевес: {direction} / {strength}, но сетап ещё не собран.'
    return f'Базовый перевес: {direction} / {strength}, рынок даёт рабочее окно для исполнения.'

def _exec_tactics(decision: Dict[str, Any]) -> Dict[str, str]:
    setup = str(decision.get("setup_status") or "WAIT").upper()
    entry_type = str(decision.get("entry_type") or "no_trade").lower()
    execution_mode = str(decision.get("execution_mode") or "conservative").lower()
    late_risk = str(decision.get("late_entry_risk") or "MEDIUM").upper()
    trap_risk = str(decision.get("trap_risk") or "MEDIUM").upper()
    location_quality = str(decision.get("location_quality") or "C").upper()
    expectation = decision.get("expectation") or []
    first_expectation = str(expectation[0]) if expectation else "ждать более чистую реакцию от уровня"

    scalp = "лучше не форсировать вход"
    hold = "hold не приоритет"
    partial = "partial не нужен, пока нет позиции"
    reentry = first_expectation

    if trap_risk == "HIGH" or late_risk == "HIGH":
        scalp = "если участвовать, то только быстрый scalp после подтверждения"
        hold = "спокойный hold пока слабый сценарий"
        partial = "при первом импульсе разумно быстро сокращать риск"
    elif setup == "VALID" and location_quality in {"A", "B"} and execution_mode in {"aggressive", "balanced"}:
        scalp = "не обязателен: можно держать часть позиции, если уровень удержан"
        hold = "hold допустим, пока структура не ломается"
        partial = "частичную фиксацию делать ближе к первому сильному импульсу"
    elif entry_type == "reversal":
        scalp = "reversal лучше собирать по частям, а не одним входом"
        hold = "hold только после reclaim / подтверждения"
        partial = "первую фиксацию делать быстрее обычного"
    elif entry_type == "pullback":
        scalp = "можно добирать от отката, не в догонку"
        hold = "hold нормален только после реакции от уровня"
        partial = "partial уместен на возврате к range-mid / локальному импульсу"
    elif entry_type == "breakout":
        scalp = "входить только после удержания пробоя, не на первой эмоции"
        hold = "hold возможен, если пробой подтверждён объёмом и удержанием"
        partial = "если пробой вязкий, часть позиции лучше снять раньше"

    return {
        "scalp": scalp,
        "hold": hold,
        "partial": partial,
        "reentry": reentry,
    }


def build_why_no_trade_text(data: Union[AnalysisSnapshot, Dict[str, Any]]) -> str:
    snapshot = _coerce_analysis_snapshot(data)
    decision = _decision_dict(snapshot)
    if not decision:
        return "🛑 WHY NO TRADE\n\nНет decision-блока для разбора."

    reason = str(decision.get("no_trade_reason") or "нужен более чистый сетап")
    wait_items = _what_to_wait_for(decision)
    tactics = _exec_tactics(decision)

    lines = [
        "🛑 WHY NO TRADE",
        "",
        f"Инструмент: {_safe_get(snapshot, 'symbol', 'BTCUSDT')}",
        f"ТФ: {_safe_get(snapshot, 'timeframe', '1h')}",
        f"Сейчас: {decision.get('action_text') or decision.get('action') or 'WAIT'} / {decision.get('setup_status_text') or decision.get('setup_status') or 'WAIT'}",
        "",
        f"Главная причина: {reason}",
        f"Контекст: {decision.get('market_state_text') or _ru_market_state(decision.get('market_state'))}",
        f"Риски: late entry {_ru_risk(decision.get('late_entry_risk') or 'MEDIUM')}, trap {_ru_risk(decision.get('trap_risk') or 'MEDIUM')}",
    ]

    if decision.get("trap_comment"):
        lines.append(f"Ловушка / trap: {decision.get('trap_comment')}")

    if wait_items:
        lines.extend(["", "Что должно измениться:"])
        for item in wait_items[:4]:
            lines.append(f"• {item}")

    lines.extend([
        "",
        "Тактика участия:",
        f"• SCALP: {tactics['scalp']}",
        f"• HOLD: {tactics['hold']}",
        f"• PARTIAL: {tactics['partial']}",
        f"• RE-ENTRY: {tactics['reentry']}",
    ])

    invalidation = str(decision.get("invalidation") or "")
    if invalidation:
        lines.extend(["", f"Инвалидация идеи: {invalidation}"])

    return "\n".join(lines)



def build_exec_plan_brief_text(data: Union[AnalysisSnapshot, Dict[str, Any]]) -> str:
    snapshot = _coerce_analysis_snapshot(data)
    decision = _decision_dict(snapshot)
    if not decision:
        return "⚙️ EXEC PLAN\n\nНет decision-блока для построения execution profile."

    tactics = _exec_tactics(decision)
    lines = [
        "⚙️ EXEC PLAN",
        "",
        f"Инструмент: {_safe_get(snapshot, 'symbol', 'BTCUSDT')} [{_safe_get(snapshot, 'timeframe', '1h')} ]",
        f"Сетап: {decision.get('setup_status_text') or decision.get('setup_status') or 'WAIT'}",
        f"Профиль: {_ru_execution_mode(decision.get('execution_mode'))} / {_ru_entry_type(decision.get('entry_type'))}",
        f"Качество: {decision.get('location_quality') or 'C'} | late {_ru_risk(decision.get('late_entry_risk') or 'MEDIUM')} | trap {_ru_risk(decision.get('trap_risk') or 'MEDIUM')}",
        "",
        f"SCALP: {tactics['scalp']}",
        f"HOLD: {tactics['hold']}",
        f"PARTIAL: {tactics['partial']}",
        f"RE-ENTRY: {tactics['reentry']}",
    ]

    invalidation = str(decision.get('invalidation') or '').strip()
    if invalidation:
        lines.append(f"Инвалидация: {invalidation}")
    summary = str(decision.get('summary') or '').strip()
    if summary:
        lines.extend(["", f"Коротко: {summary}"])
    return "\n".join(lines)


def build_decision_block_text(data: Union[AnalysisSnapshot, Dict[str, Any]]) -> str:
    snapshot = _coerce_analysis_snapshot(data)
    decision = _decision_dict(snapshot)
    data_dict = data.to_dict() if hasattr(data, 'to_dict') and not isinstance(data, dict) else (data if isinstance(data, dict) else {})

    return build_ultra_wait_block("🧠 FINAL DECISION", data_dict, include_price=False)

    if not decision:
        return "\n".join([
            "🧠 FINAL DECISION",
            "",
            "Decision engine пока не вернул отдельный decision-блок.",
        ])

    reasons = decision.get("reasons") or []
    mode_reasons = decision.get("mode_reasons") or []
    expectation = decision.get("expectation") or []

    context_blocks = _forecast_context_blocks(snapshot, decision)
    impulse_block = _fallback_impulse_block(snapshot, decision)
    lines = [
        "🧠 FINAL DECISION",
        "",
        *(_action_output_lines(decision) + [""] if _action_output_lines(decision) else []),
        *_build_quick_action_lines(snapshot, decision),
        "",
        "EXECUTION AUTHORITY:",
        f"• trade status: {decision.get('trade_authority') or ('AUTHORIZED' if decision.get('trade_authorized') else 'NOT AUTHORIZED')}",
        f"• trade reason: {decision.get('trade_authority_reason') or 'нет данных'}",
        f"• bot status: {decision.get('bot_authority') or ('AUTHORIZED' if decision.get('bot_authorized') else 'NOT AUTHORIZED')}",
        f"• bot mode: {(decision.get('execution_verdict') or {}).get('bot_mode', 'WAIT') if isinstance(decision.get('execution_verdict'), dict) else 'WAIT'}",
        "",
        f"Направление: {decision.get('direction_text') or decision.get('direction') or 'НЕЙТРАЛЬНО'}",
        f"Действие: {decision.get('action_text') or decision.get('action') or 'ЖДАТЬ'}",
        f"Manager action: {_manager_action_display(decision)}",
        f"Lifecycle: {decision.get('lifecycle_state') or 'NO_TRADE'} | Runner: {'ON' if decision.get('runner_active') else 'OFF'}",
        f"Runner mode: {decision.get('runner_mode') or '-'}",
        f"Режим: {decision.get('mode') or decision.get('regime') or 'MIXED'}",
        f"Bias confidence: {_safe_conf_pct(decision.get('bias_confidence') or decision.get('confidence_pct') or decision.get('confidence') or 0.0):.1f}%",
        f"Setup readiness: {_safe_conf_pct(decision.get('setup_readiness') or 0.0):.1f}%",
        f"Execution confidence: {_safe_conf_pct(decision.get('execution_confidence') or 0.0):.1f}%",
        f"Trade confidence: {_safe_conf_pct(decision.get('final_confidence') or 0.0):.1f}%",
        f"Risk: {decision.get('risk_level') or decision.get('risk') or 'HIGH'}",
        f"Long score: {_normalize_pct(decision.get('long_score')):.1f}%",
        f"Short score: {_normalize_pct(decision.get('short_score')):.1f}%",
        "",
        f"Коротко: {decision.get('summary') or decision.get('no_trade_reason') or 'нет итогового summary'}",
    ]

    plan = _trade_plan_core(snapshot, decision)
    setup_req = _setup_requirements(snapshot, decision)
    arming = _arming_logic(snapshot, decision)
    volume_range = _volume_range_bot_conditions(snapshot, decision)
    lines.extend([
        '',
        'SCENARIO MAP:',
        f"• рабочая сторона: {plan['side']}",
        f"• entry zone: {plan['entry_zone']}",
        f"• trigger: {plan['trigger']}",
        f"• stop: {fmt_price(plan['stop']) if plan['stop'] is not None else 'нет данных'}",
        f"• TP1: {fmt_price(plan['tp1']) if plan['tp1'] is not None else 'нет данных'}",
        f"• TP2: {fmt_price(plan['tp2']) if plan['tp2'] is not None else 'нет данных'}",
        f"• BE after TP1: {fmt_price(plan['be']) if plan['be'] is not None else 'нет данных'}",
        f"• RR to TP2: {round(float(plan['rr']), 2)}" if plan['rr'] is not None else '• RR to TP2: нет данных',
    ])

    lines.extend([''] + _tp_probability_block(plan['tp1'], plan['tp2'], plan['rr'], decision.get('execution_confidence') or decision.get('confidence_pct'), decision.get('trap_risk_score') or 0.0))
    lines.extend([''] + _entry_score_block(snapshot, decision))
    trade_scenarios = _trade_scenarios_block(snapshot, decision)
    if trade_scenarios:
        lines.extend([''] + trade_scenarios)
    lines.extend([''] + _manual_actions_block(snapshot, decision))

    lines.extend(['', 'SETUP REQUIREMENTS:'])
    for item in setup_req.get('items')[:5]:
        lines.append(f'• {item}')

    lines.extend(['', 'ARMING LOGIC:'])
    lines.append(f"• status: {arming.get('status')}")
    lines.append(f"• total readiness: {arming.get('total')}%")
    lines.append(f"• location ready: {arming.get('location_ready')}%")
    lines.append(f"• regime ready: {arming.get('regime_ready')}%")
    lines.append(f"• reversal ready: {arming.get('reversal_ready')}%")
    lines.append(f"• confirmation ready: {arming.get('confirm_ready')}%")
    if arming.get('blockers'):
        lines.append('• blockers: ' + '; '.join(arming.get('blockers')[:3]))

    bot_cards = data_dict.get('bot_cards') if isinstance(data_dict.get('bot_cards'), list) else []
    best_soft_card = None
    for card in sorted(bot_cards, key=lambda c: float(card.get('ranking_score') or card.get('score') or 0.0), reverse=True):
        action_hint = str(card.get('management_action') or '').upper()
        plan_state = str(card.get('plan_state') or '').upper()
        status_hint = str(card.get('status') or card.get('activation_state') or '').upper()
        score_hint = float(card.get('ranking_score') or card.get('score') or 0.0)
        if action_hint in {'ENABLE SMALL SIZE', 'ENABLE SMALL SIZE REDUCED'} or plan_state in {'SMALL ENTRY', 'READY_SMALL', 'READY_SMALL_REDUCED'}:
            best_soft_card = card
            break
    vr_status = str(volume_range.get('status') or '')
    edge_now = float((data_dict.get('edge_score') or decision.get('edge_score') or 0.0))
    decision_wait = str(decision.get('action') or decision.get('action_text') or '').upper() in {'WAIT', 'ЖДАТЬ'}
    if vr_status == 'READY_SMALL_REDUCED' and edge_now > 0.0 and not decision_wait:
        quick_bot_mode = 'REDUCED_ONLY'
        quick_action = 'можно стартовать range small'
    elif vr_status == 'READY_SMALL' and edge_now > 0.0 and not decision_wait:
        quick_bot_mode = 'SOFT_READY'
        quick_action = 'можно стартовать range small'
    elif best_soft_card is not None and edge_now > 0.0 and not decision_wait:
        action_hint = str(best_soft_card.get('management_action') or '').upper()
        quick_bot_mode = 'SMALL ENTRY' if 'SMALL' in action_hint or str(best_soft_card.get('plan_state') or '').upper() == 'SMALL ENTRY' else 'WATCH_CONFIRM'
        quick_action = 'ждать подтверждение для малого входа'
    else:
        quick_bot_mode = decision.get('execution_verdict', {}).get('bot_mode', 'WAIT') if isinstance(decision.get('execution_verdict'), dict) else 'WAIT'
        quick_action = 'ждать'
    mtf = data_dict.get('multi_tf_context') if isinstance(data_dict.get('multi_tf_context'), dict) else {}
    if mtf:
        lines.extend(['', 'MULTI-TF FUSION V6.6:'])
        lines.append(f"• execution TF: {mtf.get('execution_tf')} | bias TF: {mtf.get('bias_tf')} | HTF: {mtf.get('htf_tf')}")
        lines.append(f"• local: {mtf.get('local_direction')} | forecast: {mtf.get('forecast_direction')} | pattern: {mtf.get('pattern_direction')} | htf: {mtf.get('htf_direction')}")
        lines.append(f"• alignment: {mtf.get('alignment')} | action: {mtf.get('action')} | risk: {mtf.get('risk_modifier')}")
        lines.append(f"• summary: {mtf.get('summary')}")
    lines.extend(['', '⚡ ЧТО ДЕЛАТЬ ПРЯМО СЕЙЧАС:'])
    lines.append(f"• action: {quick_action}")
    lines.append(f"• bot mode: {quick_bot_mode}")
    lines.append(f"• size mode: x{float(volume_range.get('size_multiplier') or 1.0):.2f}")
    lines.append(f"• adds: {'разрешены' if str(volume_range.get('add_status')) == 'READY_ADD' else 'запрещены / ждать'}")
    lines.append(f"• note: {'мягкий запуск внутри диапазона допустим' if str(volume_range.get('status')) in {'READY_SMALL', 'READY_SMALL_REDUCED'} and edge_now > 0.0 and not decision_wait else 'только наблюдение: нужен confirm / reclaim' if best_soft_card is None or decision_wait or edge_now <= 0.0 else 'есть мягкий кандидат, но только после подтверждения и малым размером'}")
    lines.extend(['', 'RANGE VOLUME BOT:'])
    lines.append(f"• status: {volume_range.get('status')}")
    lines.append(f"• add status: {volume_range.get('add_status')}")
    lines.append(f"• deviation from base: {float(volume_range.get('deviation') or 0.0):.2f}%")
    lines.append(f"• range detected: {volume_range.get('range_detected')}")
    lines.append(f"• location state: {volume_range.get('location_state')}")
    lines.append(f"• post-impulse fade: {volume_range.get('post_impulse_fade')}")
    lines.append(f"• breakout risk: {volume_range.get('breakout_risk')}")
    lines.append(f"• size multiplier: x{float(volume_range.get('size_multiplier') or 1.0):.2f}")
    lines.append(f"• rotation quality: {volume_range.get('rotation_quality')}")
    for item in volume_range.get('conditions')[:5]:
        lines.append(f'• {item}')
    if volume_range.get('blockers'):
        lines.append('• blockers: ' + '; '.join(volume_range.get('blockers')[:3]))

    _append_decision_detail_blocks(lines, decision)

    scenario_text = str(decision.get("scenario_text") or decision.get("base_case") or "").strip()
    trigger_text = str(decision.get("trigger_text") or "").strip()
    bull_case = str(decision.get("bull_case") or "").strip()
    bear_case = str(decision.get("bear_case") or "").strip()
    scenario_invalidation = str(decision.get("scenario_invalidation") or decision.get("invalidation") or "").strip()
    if scenario_text or trigger_text or bull_case or bear_case:
        lines.extend(["", "SCENARIO:"])
        if scenario_text:
            lines.append(f"• {scenario_text}")
        if bull_case:
            lines.append(f"• {bull_case}")
        if bear_case:
            lines.append(f"• {bear_case}")
        if trigger_text:
            lines.append(f"• {trigger_text}")
        trigger_up = str(decision.get("trigger_up") or "").strip()
        trigger_down = str(decision.get("trigger_down") or "").strip()
        if trigger_up:
            lines.append(f"• {trigger_up}")
        if trigger_down:
            lines.append(f"• {trigger_down}")
        if scenario_invalidation:
            lines.append(f"• {scenario_invalidation}")

    if context_blocks.get('support') or context_blocks.get('oppose') or context_blocks.get('invalidation'):
        lines.extend(['', 'TEXT QUALITY LAYER:'])
        if context_blocks.get('support'):
            lines.append('• что поддерживает сценарий:')
            for item in context_blocks['support'][:3]:
                lines.append(f'  - {item}')
        if context_blocks.get('oppose'):
            lines.append('• что мешает сценарию:')
            for item in context_blocks['oppose'][:3]:
                lines.append(f'  - {item}')
        if context_blocks.get('invalidation'):
            lines.append('• что ломает сценарий:')
            for item in context_blocks['invalidation'][:3]:
                lines.append(f'  - {item}')

    if reasons:
        lines.extend(["", "Почему:"])
        for item in reasons[:5]:
            lines.append(f"• {item}")

    if mode_reasons:
        lines.extend(["", "Почему такой режим:"])
        for item in mode_reasons[:3]:
            lines.append(f"• {item}")

    if expectation:
        lines.extend(["", "Что ждать дальше:"])
        for item in expectation[:3]:
            lines.append(f"• {item}")

    return "\n".join(lines)




def _action_ru_companion(value: Any) -> str:
    raw = str(value or '').strip().upper()
    mapping = {
        'WAIT': 'ЖДАТЬ ЗОНУ',
        'WATCH': 'СМОТРЕТЬ РЕАКЦИЮ',
        'WATCH_ZONE': 'СМОТРЕТЬ ЗОНУ',
        'WATCH_SHORT': 'СМОТРЕТЬ SHORT-СЕТАП',
        'WATCH_LONG': 'СМОТРЕТЬ LONG-СЕТАП',
        'WAIT_EDGE_SHORT': 'РАБОТАТЬ ОТ ВЕРХНЕГО КРАЯ',
        'WAIT_EDGE_LONG': 'РАБОТАТЬ ОТ НИЖНЕГО КРАЯ',
        'NO_MID_ENTRY': 'НЕ ВХОДИТЬ ИЗ СЕРЕДИНЫ',
        'GRID_EDGE_ONLY': 'СЕТКИ ТОЛЬКО ОТ КРАЯ',
        'ARM_SHORT': 'ГОТОВИТЬ SHORT',
        'ARM_LONG': 'ГОТОВИТЬ LONG',
        'EXECUTE_PROBE_SHORT': 'SHORT PROBE ДОПУСТИМ',
        'EXECUTE_PROBE_LONG': 'LONG PROBE ДОПУСТИМ',
        'EXECUTE_SHORT': 'SHORT РАЗРЕШЁН',
        'EXECUTE_LONG': 'LONG РАЗРЕШЁН',
        'MANAGE': 'ВЕСТИ ПОЗИЦИЮ',
        'MANAGE_SHORT': 'ВЕСТИ SHORT',
        'MANAGE_LONG': 'ВЕСТИ LONG',
        'EXIT': 'ВЫХОДИТЬ',
    }
    return mapping.get(raw, str(value or 'ЖДАТЬ'))


def _reaction_zone_text(low: Any, mid: Any, high: Any, direction: str) -> str:
    if direction == 'ШОРТ':
        return _zone_from_bounds(mid, high)
    if direction == 'ЛОНГ':
        return _zone_from_bounds(low, mid)
    return _zone_from_bounds(low, high)


def _pattern_companion_lines(data_dict: Dict[str, Any]) -> list[str]:
    pattern = data_dict.get('pattern_memory_v2') if isinstance(data_dict.get('pattern_memory_v2'), dict) else {}
    legacy_dir = data_dict.get('history_pattern_direction') or data_dict.get('pattern_forecast_direction') or 'НЕЙТРАЛЬНО'
    legacy_conf = _normalize_pct(data_dict.get('history_pattern_confidence') or data_dict.get('pattern_forecast_confidence'), 0.0)
    legacy_summary = str(data_dict.get('history_pattern_summary') or data_dict.get('pattern_forecast_move') or '').strip()

    price = _safe_float(data_dict.get('price') or data_dict.get('current_price'), 0.0)
    low = data_dict.get('range_low')
    mid = data_dict.get('range_mid')
    high = data_dict.get('range_high')
    if low is not None and high is not None and high != low:
        pos_pct = max(0.0, min(100.0, (price - _safe_float(low, price)) / max(1e-9, _safe_float(high, price) - _safe_float(low, price)) * 100.0))
    else:
        pos_pct = _safe_float(data_dict.get('range_position_pct'), 50.0)
    at_mid = 30.0 <= pos_pct <= 70.0

    decision = data_dict.get('decision') if isinstance(data_dict.get('decision'), dict) else {}
    impulse = data_dict.get('impulse_character') if isinstance(data_dict.get('impulse_character'), dict) else {}
    structure = str(impulse.get('state') or data_dict.get('structure_state') or data_dict.get('market_state') or 'CHOP').upper()
    volume = data_dict.get('volume_confirmation') if isinstance(data_dict.get('volume_confirmation'), dict) else {}
    analysis = data_dict.get('analysis') if isinstance(data_dict.get('analysis'), dict) else {}
    if not volume and isinstance(analysis.get('volume_confirmation'), dict):
        volume = analysis.get('volume_confirmation')
    breakout = str((volume or {}).get('breakout_quality') or (volume or {}).get('breakout_state') or 'UNCONFIRMED').upper()
    action_now = str(((data_dict.get('master_authority') or {}).get('action_now')) or ((data_dict.get('bot_authority_v2') or {}).get('action_now')) or decision.get('action') or '').upper()
    entry_forbidden = 'NO ENTRY' in action_now or 'PAUSE' in action_now or 'WAIT' in action_now
    suppress = at_mid and structure == 'CHOP' and breakout in {'UNCONFIRMED', 'WEAK', 'FAILED', ''} and entry_forbidden

    if suppress:
        summary = legacy_summary or 'локальный перевес меняется, но в середине диапазона не даёт рабочего directional edge'
        return [
            '• pattern-memory: CONTEXT ONLY / BLOCKED BY MID RANGE',
            f'• статус: локальные совпадения есть, но master decision не разрешает вход | {summary}',
        ]

    if not pattern:
        if legacy_summary or legacy_dir != 'НЕЙТРАЛЬНО':
            conf_txt = int(round(legacy_conf or 0.0))
            return [f'• {_normalize_direction_text(legacy_dir)} {conf_txt}% | {legacy_summary or "range rotation"}', f'• подтверждение: {"сильное" if legacy_conf >= 75 else "умеренное" if legacy_conf >= 60 else "слабое"}']
        return ['• NEUTRAL | pattern unclear']

    direction = _normalize_direction_text(pattern.get('direction') or pattern.get('direction_bias') or pattern.get('pattern_bias') or legacy_dir or 'НЕЙТРАЛЬНО')
    conf = _normalize_pct(
        pattern.get('short_prob') or pattern.get('long_prob') or pattern.get('confidence'),
        legacy_conf or 50.0,
    )
    expected = str(pattern.get('expected_path') or legacy_summary or 'RANGE_ROTATION').replace('_', ' ').lower()
    out = [f'• {direction} {int(round(conf))}% | {expected}']
    out.append(f'• подтверждение: {"сильное" if conf >= 75 else "умеренное" if conf >= 60 else "слабое"}')
    invalidation = str(pattern.get('invalidation') or '').strip()
    if invalidation:
        out.append(f'• отмена: {invalidation}')
    return out


def _pinbar_companion_lines(snapshot: AnalysisSnapshot, data_dict: Dict[str, Any]) -> list[str]:
    pin = data_dict.get('pinbar_context') if isinstance(data_dict.get('pinbar_context'), dict) else {}
    if pin:
        if pin.get('pinbar_valid'):
            confirmed = 'подтверждён' if pin.get('pinbar_confirmed') else 'ещё не подтверждён'
            return [f"• пинбар: {pin.get('label')} | {pin.get('pinbar_strength')}, {confirmed}", f"• вывод: {pin.get('summary')}"]
        return [f"• пинбар: {pin.get('label')}", f"• вывод: {pin.get('summary')}"]
    patterns = _safe_get(snapshot, 'reversal_patterns', None) or data_dict.get('reversal_patterns') or []
    patterns = [str(x) for x in patterns if x]
    if patterns:
        return [f"• свечной сигнал: {patterns[0]}"]
    return ['• пинбар: явного подтверждённого пинбара нет']


def _volume_companion_lines(data_dict: Dict[str, Any]) -> list[str]:
    analysis = data_dict.get('analysis') if isinstance(data_dict.get('analysis'), dict) else {}
    volume = data_dict.get('volume_confirmation') if isinstance(data_dict.get('volume_confirmation'), dict) else {}
    if not volume and isinstance(analysis.get('volume_confirmation'), dict):
        volume = analysis.get('volume_confirmation')
    orderflow = data_dict.get('orderflow_context') if isinstance(data_dict.get('orderflow_context'), dict) else {}
    if not orderflow and isinstance(analysis.get('orderflow_context'), dict):
        orderflow = analysis.get('orderflow_context')
    micro = data_dict.get('microstructure') if isinstance(data_dict.get('microstructure'), dict) else {}
    if not micro and isinstance(analysis.get('microstructure'), dict):
        micro = analysis.get('microstructure')
    rel = _safe_float((volume or {}).get('relative_volume') or orderflow.get('relative_volume') or orderflow.get('volume_ratio') or micro.get('volume_ratio'), 1.0)
    q = str((volume or {}).get('volume_quality') or 'MIXED').upper()
    bq = str((volume or {}).get('breakout_quality') or 'UNCONFIRMED').upper()
    if volume:
        return [f"• {q} | breakout {'не подтверждён' if bq == 'UNCONFIRMED' else bq.lower()}"]
    return [f"• MIXED | breakout не подтверждён"]



def _fusion_companion_context(data_dict: Dict[str, Any], direction: str, pos_pct: float, low: Any, mid: Any, high: Any, impulse: Dict[str, Any] | None = None) -> Dict[str, Any]:
    pattern = data_dict.get('pattern_memory_v2') if isinstance(data_dict.get('pattern_memory_v2'), dict) else {}
    if not pattern and isinstance(data_dict.get('pattern_memory'), dict):
        pattern = data_dict.get('pattern_memory')
    volume = data_dict.get('volume_confirmation') if isinstance(data_dict.get('volume_confirmation'), dict) else {}
    analysis = data_dict.get('analysis') if isinstance(data_dict.get('analysis'), dict) else {}
    if not volume and isinstance(analysis.get('volume_confirmation'), dict):
        volume = analysis.get('volume_confirmation')
    impulse = impulse if isinstance(impulse, dict) else {}

    pattern_bias = str(pattern.get('pattern_bias') or pattern.get('direction') or 'NEUTRAL').upper()
    long_prob = _safe_float(pattern.get('long_prob'), 0.0)
    short_prob = _safe_float(pattern.get('short_prob'), 0.0)
    neutral_prob = _safe_float(pattern.get('neutral_prob'), 0.0)
    raw_pattern_conf = _safe_float(pattern.get('confidence'), 0.0)
    pattern_conf = (
        pattern.get('short_prob')
        or pattern.get('long_prob')
        or pattern.get('confidence')
        or 50.0
    )
    expected_path = str(pattern.get('expected_path') or 'UNCLEAR').upper()
    p_quality = str(pattern.get('match_quality') or 'SOFT').upper()

    vol_quality = str(volume.get('volume_quality') or 'MIXED').upper()
    breakout = str(volume.get('breakout_quality') or 'UNCONFIRMED').upper()
    accel = str(volume.get('acceleration_state') or 'NORMAL').upper()
    reaction_quality = str(volume.get('reaction_quality') or 'MIXED').upper()
    vol_conf = _safe_float(volume.get('confidence'), 50.0)
    signal_note = str(volume.get('signal_note') or '').strip()
    impulse_state = str((impulse or {}).get('state') or 'CHOP').upper()

    at_mid = 30.0 <= pos_pct <= 70.0
    near_upper = pos_pct >= 68.0 or (high is not None and mid is not None and _safe_float(high, 0.0) > 0 and _safe_float(mid, 0.0) > 0 and _safe_float(high, 0.0) >= _safe_float(mid, 0.0) and _safe_float(high, 0.0) * 0.995 <= _safe_float(data_dict.get('price') or data_dict.get('current_price'), 0.0))
    near_lower = pos_pct <= 32.0

    scenario = 'CHOP'
    action = 'WATCH'
    title = 'СМОТРЕТЬ РЕАКЦИЮ'
    summary = 'нужна реакция на край диапазона; из середины вход запрещён'
    trigger = 'касание края диапазона + reclaim / failure'
    risk = 'MID_RANGE'
    setup_side = direction
    grid_mode = 'SOFT_ON'

    continuation_bias = pattern_bias in {'LONG','SHORT'} and vol_quality == 'CONFIRMING' and breakout in {'CONFIRMED','STRONG'} and accel == 'ACCELERATION' and vol_conf >= 58 and impulse_state not in {'CHOP','UNKNOWN'}
    fade_bias = pattern_bias in {'LONG','SHORT'} and expected_path in {'RANGE_ROTATION','FADE','MEAN_REVERT'} and vol_quality in {'REJECTION','THIN','MIXED'} and breakout in {'UNCONFIRMED','WEAK','FAILED'}

    if continuation_bias:
        scenario = f'CONTINUATION_{pattern_bias}'
        action = 'WATCH_LONG' if pattern_bias == 'LONG' else 'WATCH_SHORT'
        title = 'СМОТРЕТЬ CONTINUATION'
        summary = f'структура и объём поддерживают продолжение в сторону {"лонга" if pattern_bias == "LONG" else "шорта"}; без догонки, только по откату / удержанию'
        trigger = 'удержание после отката + новый follow-through в сторону движения'
        risk = 'CHASE_RISK'
        grid_mode = 'REDUCE_COUNTER'
        setup_side = 'ЛОНГ' if pattern_bias == 'LONG' else 'ШОРТ'
    elif fade_bias:
        scenario = f'RANGE_ROTATION_{pattern_bias}'
        action = 'WAIT_EDGE_SHORT' if pattern_bias == 'SHORT' else 'WAIT_EDGE_LONG'
        title = 'ЖДАТЬ КРАЙ ДИАПАЗОНА'
        if at_mid:
            action = 'NO_MID_ENTRY'
            title = 'НЕ ВХОДИТЬ ИЗ СЕРЕДИНЫ'
            summary = f'паттерн тяготеет к {"шортовой" if pattern_bias == "SHORT" else "лонговой"} range rotation, но объём не подтверждает немедленный вход; из середины диапазона вход запрещён'
            trigger = 'ждать верхнюю/нижнюю границу и слабый пробой / возврат'
            risk = 'MID_RANGE'
        else:
            summary = f'структура склонна к {"возврату вниз" if pattern_bias == "SHORT" else "возврату вверх"}, объём не подтверждает продолжение против ожидаемой ротации'
            trigger = 'слабый пробой края + возврат обратно в диапазон'
            risk = 'EDGE_ONLY'
        grid_mode = 'PREFER_GRID'
        setup_side = 'ШОРТ' if pattern_bias == 'SHORT' else 'ЛОНГ'
    elif impulse_state == 'CHOP' and vol_quality in {'MIXED','THIN','REJECTION'}:
        scenario = 'CHOP'
        action = 'NO_MID_ENTRY' if at_mid else 'GRID_EDGE_ONLY'
        title = 'GRID / WAIT EDGE'
        summary = 'рынок в chop; паттерн и объём не дают подтверждённого directional входа, предпочтительнее сетки и работа только от края диапазона'
        trigger = 'ждать реакцию на верхнем или нижнем блоке'
        risk = 'MID_RANGE'
        grid_mode = 'PREFER_GRID'
        setup_side = direction

    if at_mid:
        action = 'NO_MID_ENTRY'
        title = 'НЕ ВХОДИТЬ ИЗ СЕРЕДИНЫ'

    elif pattern_bias == 'SHORT' and breakout == 'UNCONFIRMED':
        action = 'WAIT_EDGE_SHORT'

    if pattern_bias == 'SHORT' and near_upper and action in {'WATCH_SHORT','WAIT','WAIT_EDGE_SHORT','NO_MID_ENTRY'}:
        trigger = 'short только у верхнего блока: вынос выше зоны без acceptance + возврат под уровень'
    elif pattern_bias == 'LONG' and near_lower and action in {'WATCH_LONG','WAIT','WAIT_EDGE_LONG','NO_MID_ENTRY'}:
        trigger = 'long только у нижнего блока: пролив ниже зоны без acceptance + возврат выше уровня'
    elif action == 'NO_MID_ENTRY' and pattern_bias == 'SHORT':
        trigger = 'short только после подхода к верхнему блоку и слабого пробоя / возврата'
    elif action == 'NO_MID_ENTRY' and pattern_bias == 'LONG':
        trigger = 'long только после подхода к нижнему блоку и выкупа / возврата'

    path_txt = {
        'RANGE_ROTATION': 'range rotation',
        'FADE': 'fade',
        'MEAN_REVERT': 'mean revert',
        'CONTINUATION': 'continuation',
        'UNCLEAR': 'unclear',
    }.get(expected_path, expected_path.lower())
    mode_txt = 'EDGE ONLY / PREFER_GRID' if grid_mode == 'PREFER_GRID' else action
    integration = {
        'state_line': f'{impulse_state} + {vol_quality}',
        'entry_line': 'directional вход не подтверждён' if grid_mode == 'PREFER_GRID' or at_mid or breakout == 'UNCONFIRMED' else f'допустим вход по сценарию {path_txt}',
        'mode_line': mode_txt,
        'pattern_path': path_txt,
    }

    return {
        'scenario': scenario,
        'action': action,
        'action_override': 'WAIT_EDGE_SHORT' if pattern_bias == 'SHORT' and breakout == 'UNCONFIRMED' else None,
        'title': title,
        'summary': summary,
        'trigger': trigger,
        'risk': risk,
        'grid_mode': grid_mode,
        'setup_side': setup_side,
        'integration': integration,
        'pattern_bias': pattern_bias,
        'at_mid': at_mid,
    }

def _build_companion_analysis_text(snapshot: AnalysisSnapshot, data_dict: Dict[str, Any], timeframe: str) -> str:
    decision = _decision_dict(snapshot)
    v14 = data_dict.get('v14_snapshot') if isinstance(data_dict.get('v14_snapshot'), dict) else {}
    impulse = data_dict.get('impulse_character') if isinstance(data_dict.get('impulse_character'), dict) else {}
    fake = data_dict.get('liquidation_reaction') if isinstance(data_dict.get('liquidation_reaction'), dict) else {}
    reaction = data_dict.get('liquidation_reaction') if isinstance(data_dict.get('liquidation_reaction'), dict) else {}
    blocks = data_dict.get('liquidity_blocks') if isinstance(data_dict.get('liquidity_blocks'), dict) else {}
    bot_auth = data_dict.get('bot_authority_v2') if isinstance(data_dict.get('bot_authority_v2'), dict) else {}
    grid_cmd = data_dict.get('grid_cmd') if isinstance(data_dict.get('grid_cmd'), dict) else {}

    price = _safe_get(snapshot, 'price', None) or data_dict.get('price') or data_dict.get('current_price')
    low = data_dict.get('range_low', _safe_get(snapshot, 'range_low', None))
    mid = data_dict.get('range_mid', _safe_get(snapshot, 'range_mid', None))
    high = data_dict.get('range_high', _safe_get(snapshot, 'range_high', None))
    direction = _normalize_direction_text(v14.get('direction') or decision.get('direction') or decision.get('direction_text'))
    decision_action = v14.get('decision_action') or decision.get('action') or 'WAIT'
    location_state = str(v14.get('location_state') or '').upper()
    pos_pct = _safe_float(v14.get('range_position_pct'), 50.0)
    setup_note = str(v14.get('setup_note') or decision.get('setup_note') or '').strip()
    invalidation = str(v14.get('invalidation') or decision.get('invalidation') or 'нет данных').strip()
    entry_hint = str(v14.get('entry_hint') or decision.get('entry_hint') or '').strip()
    reversal_signal = str(_safe_get(snapshot, 'reversal_signal', None) or data_dict.get('reversal_signal') or ((data_dict.get('reversal_v15') or {}).get('state')) or 'NO_REVERSAL')
    reversal_conf = _normalize_pct(_safe_get(snapshot, 'reversal_confidence', None) or data_dict.get('reversal_confidence') or ((data_dict.get('reversal_v15') or {}).get('confidence')), 0.0)

    state_comment = {
        'UPPER_EDGE': 'UPPER EDGE',
        'LOWER_EDGE': 'LOWER EDGE',
        'MID': 'MID RANGE',
        'UPPER_PART': 'UPPER RANGE',
        'LOWER_PART': 'LOWER RANGE',
    }.get(location_state, 'MID RANGE' if 30.0 <= pos_pct <= 70.0 else 'EDGE')

    fusion = _fusion_companion_context(data_dict, direction, pos_pct, low, mid, high, impulse)
    extra = derive_v1689_context(data_dict)
    authority = _derive_v16_view(data_dict)
    fusion_action = authority.get('action_now') or fusion.get('action_override') or fusion.get('action') or decision_action
    fusion_summary = fusion.get('summary') or ''
    fusion_trigger = fusion.get('trigger') or entry_hint or setup_note

    header = 'RANGE / GRID' if str(fusion.get('grid_mode') or '').upper() == 'PREFER_GRID' else ('FAKE UP' if str(fusion.get('scenario') or '').upper() == 'FAKE_UP' else _action_ru_companion(fusion_action))

    lines = [f'📊 BTC ANALYSIS [{timeframe}]', '']
    if price is not None:
        lines += [header, f'Цена: {fmt_price(price)}', '']

    upper = (blocks.get('upper_block') or {})
    lower = (blocks.get('lower_block') or {})
    lines += [
        f'• структура: {impulse.get("state") or "CHOP"}',
        f"• позиция: {authority.get('ctx', {}).get('range_state') or state_comment}",
    ]

    lines += ['', 'ПАТТЕРНЫ:']
    lines.extend(_pattern_companion_lines(data_dict))

    lines += ['', 'ОБЪЁМ:']
    lines.extend(_volume_companion_lines(data_dict))

    if safe_value(reaction.get('acceptance') or fake.get('state')):
        lines += ['', 'FAKE / ПРОДОЛЖЕНИЕ:']
        lines.append(f"• статус: {reaction.get('acceptance') or fake.get('state')}")
        if safe_value(reaction.get('summary') or fake.get('summary')):
            lines.append(f"• вывод: {reaction.get('summary') or fake.get('summary')}")

    if reversal_conf > 20 and safe_value(reversal_signal):
        lines += ['', 'РАЗВОРОТ:']
        lines.append(f'• статус: {reversal_signal} ({reversal_conf:.1f}%)')

    integration = fusion.get('integration') if isinstance(fusion.get('integration'), dict) else {}
    lines += ['', 'ИНТЕГРАЦИЯ:']
    lines.append(f"• {integration.get('state_line') or 'CHOP + MIXED'}")
    lines.append(f"• {integration.get('entry_line') or 'directional вход не подтверждён'}")
    lines.append(f"• режим: {integration.get('mode_line') or 'WAIT'}")
    lines.append(f"• качество диапазона: {_range_quality_ru(extra['range_quality']['label'])}")

    if extra['divergence']['visible']:
        lines += ['', 'ДИВЕРГЕНЦИЯ:']
        lines.append(f"• {_divergence_ru(extra['divergence']['state'], extra['divergence']['strength'])}")
        if extra['divergence']['note']:
            lines.append(f"• смысл: {extra['divergence']['note']}")

    if extra['reclaim']['visible']:
        lines += ['', 'RECLAIM:']
        lines.append(f"• {extra['reclaim']['state']}")
        if extra['reclaim']['action']:
            lines.append(f"• действие: {extra['reclaim']['action']}")

    lines += ['', '⚡ ЧТО ДЕЛАТЬ:']
    current_action = authority.get('action_now') or _action_ru_companion(fusion_action)
    lines.append(f"• режим действий: {authority.get('authority_title_ru') or current_action} — {authority.get('authority_ru') or ''}")
    lines.append(f"• runtime: {_runtime_icon(authority.get('long_grid') or 'PAUSE')} лонг {_runtime_state_ru(authority.get('long_grid') or 'PAUSE')} | {_runtime_icon(authority.get('short_grid') or 'PAUSE')} шорт {_runtime_state_ru(authority.get('short_grid') or 'PAUSE')}")
    lines.append(f"• прогноз рынка: {authority.get('forecast_text') or '↔️ БАЗА: рынок остаётся в диапазоне; работа только от края'}")
    lines.append(f"• цель движения: {authority.get('target_text') or '🎯 цель: ждать реакцию у края диапазона'}")
    lines.append(f"• импульс: {authority.get('impulse_text') or '↔️ импульс слабый; рынок остаётся в диапазоне'}")
    lines.append(f"• сценарий: {authority.get('scenario_text') or '↔️ ПАУЗА — без явной ведущей стороны'}")
    lines.append(f"• уверенность сценария: {authority.get('scenario_confidence') or 0}% — {authority.get('scenario_confidence_ru') or 'низкая'}")
    lines.append(f"• авто-риск: {authority.get('auto_risk_mode') or '🟡 ЛЁГКИЙ — уменьшенный риск'}")
    lines.append(f"• слом сценария: {authority.get('invalidation_text') or '🚫 ждать подтверждённый выход из диапазона'}")
    if authority.get('master_locked') and authority.get('master_tf'):
        lines.append(f"• синхронизация: мастер-режим из {authority.get('master_tf')}")
    lines.append(f"• short: только у верхнего блока { _zone_from_bounds(upper.get('low', mid), upper.get('high', high)) }")
    lines.append(f"• long: только у нижнего блока { _zone_from_bounds(lower.get('low', low), lower.get('high', mid)) }")
    lines.append('• триггер: касание края + слабый пробой / быстрый возврат')

    lines += ['', '🧩 СЕТКИ:']
    lines.append('• режим: ПРИОРИТЕТ СЕТОК' if str(fusion.get('grid_mode') or '').upper() == 'PREFER_GRID' else f"• режим: {fusion.get('grid_mode') or bot_auth.get('status') or 'GRID'}")
    lines.append(f"• лонг-сетка: {_runtime_icon(authority.get('long_grid') or 'PAUSE')} {_runtime_state_ru(authority.get('long_grid') or 'PAUSE')} — {_runtime_ru(authority.get('long_grid') or 'PAUSE')}")
    lines.append(f"• шорт-сетка: {_runtime_icon(authority.get('short_grid') or 'PAUSE')} {_runtime_state_ru(authority.get('short_grid') or 'PAUSE')} — {_runtime_ru(authority.get('short_grid') or 'PAUSE')}")
    lines.append('• активация: только у края')
    lines.append('• агрессия: низкая')
    lines += _execution_block_lines(data_dict, authority)
    lines += _hedge_block_lines(data_dict, authority)

    return '\n'.join(lines)

def build_base_analysis_text(data: Union[AnalysisSnapshot, Dict[str, Any]], default_tf: str = "1h") -> str:
    snapshot = _coerce_analysis_snapshot(data, default_tf=default_tf)
    decision = _decision_dict(snapshot)
    data_dict = data.to_dict() if hasattr(data, "to_dict") and not isinstance(data, dict) else (data if isinstance(data, dict) else {})

    timeframe = _safe_get(snapshot, "timeframe", default_tf)
    symbol = _safe_get(snapshot, "symbol", "BTCUSDT")
    price = _safe_get(snapshot, "price", 0.0)
    if isinstance(price, (int, float)) and price <= 0:
        price = None

    signal = _safe_get(snapshot, "signal", None) or decision.get("direction_text") or "нет данных"
    final_decision = _safe_get(snapshot, "final_decision", None) or decision.get("direction_text") or "нет данных"
    forecast_direction = _safe_get(snapshot, "forecast_direction", None) or decision.get("direction_text") or "нет данных"
    forecast_confidence = _safe_get(snapshot, "forecast_confidence", None)
    forecast_strength = _sync_forecast_strength(forecast_direction, forecast_confidence if forecast_confidence is not None else decision.get("confidence_pct") or decision.get("confidence"), _safe_get(snapshot, "forecast_strength", None) or decision.get("forecast_strength"))
    reversal_signal = _safe_get(snapshot, "reversal_signal", "NO_REVERSAL")
    reversal_confidence = _safe_get(snapshot, "reversal_confidence", 0.0)

    range_obj = _safe_get(snapshot, "range", None)
    range_low = _safe_get(range_obj, "low", 0.0)
    range_mid = _safe_get(range_obj, "mid", 0.0)
    range_high = _safe_get(range_obj, "high", 0.0)

    range_state = _safe_get(snapshot, "range_state", "нет данных")
    ct_now = _safe_get(snapshot, "ct_now", "нет данных")
    ginarea_advice = _safe_get(snapshot, "ginarea_advice", "нет данных")
    history_pattern_direction = _safe_get(snapshot, "history_pattern_direction", None)
    history_pattern_confidence = _safe_get(snapshot, "history_pattern_confidence", None)
    history_pattern_summary = _safe_get(snapshot, "history_pattern_summary", "")
    pattern_forecast_direction = _safe_get(snapshot, "pattern_forecast_direction", None)
    pattern_forecast_confidence = _safe_get(snapshot, "pattern_forecast_confidence", None)
    pattern_forecast_move = _safe_get(snapshot, "pattern_forecast_move", "")
    pattern_forecast_regime = _safe_get(snapshot, "pattern_forecast_regime", "")
    pattern_forecast_style = _safe_get(snapshot, "pattern_forecast_style", "")
    pattern_years = _safe_get(snapshot, "pattern_years", None)
    pattern_scope = _safe_get(snapshot, "pattern_scope", "recent_multi_cycle")
    decision_summary = _safe_get(snapshot, "decision_summary", "") or decision.get("summary", "")

    if timeframe in {'15m', '1h'}:
        return _build_companion_analysis_text(snapshot, data_dict, timeframe)

    if is_no_trade_context(data_dict):
        return _build_companion_analysis_text(snapshot, data_dict, timeframe)

    direction_text = decision.get("direction_text") or decision.get("direction") or "НЕЙТРАЛЬНО"
    action_text = decision.get("action_text") or decision.get("action") or "ЖДАТЬ"
    mode_text = decision.get("mode") or decision.get("regime") or "MIXED"
    conf_text = _effective_trade_confidence_renderer(decision)
    display_confidence = conf_text
    risk_text = decision.get("risk_level") or decision.get("risk") or "HIGH"
    action_first = _build_action_first_block(snapshot, decision)

    context_blocks = _forecast_context_blocks(snapshot, decision)
    quality_line = _quality_summary_line(snapshot, decision)
    resolved_forecast_direction = _resolved_forecast_direction(snapshot, decision)
    bias_label, bias_reason = _bias_block(snapshot, decision)
    lines = [
        f"📊 BTC ANALYSIS [{timeframe}]",
        "",
        f"Инструмент: {symbol}",
        f"Таймфрейм debug: {timeframe}",
        f"Цена: {fmt_price(price)}",
        "",
        "⚡ ACTION-FIRST:",
        f"• что делать: {action_first['what_now']}",
        f"• рабочая сторона: {action_first['direction']}",
        f"• рабочая зона: {action_first['zone']}",
        f"• триггер: {action_first['trigger']}",
        f"• инвалидация: {action_first['invalidation']}",
        f"• запрет: {action_first['not_now']}",
        "",
        "Главное сейчас:",
        f"• сигнал: {signal}",
        f"• финальное решение: {final_decision}",
        f"• куда вероятнее пойдёт рынок: {resolved_forecast_direction}",
        f"• сила прогноза: {forecast_strength or 'NEUTRAL'}",
        f"• уверенность: {fmt_pct(display_confidence)}",
        f"• reversal: {reversal_signal or 'NO_REVERSAL'}",
        f"• reversal confidence: {fmt_pct(reversal_confidence if reversal_confidence is not None else 0.0)}",
        "",
        "FINAL DECISION:",
        f"• направление: {direction_text}",
        f"• действие: {action_text}",
        f"• режим: {mode_text}",
        f"• confidence: {conf_text:.1f}%",
        f"• risk: {risk_text}",
        "",
        "BIAS:",
        f"• базовый перевес: {bias_label}",
        f"• причина: {bias_reason}",
    ]

    plan = _trade_plan_core(snapshot, decision)
    setup_req = _setup_requirements(snapshot, decision)
    arming = _arming_logic(snapshot, decision)
    volume_range = _volume_range_bot_conditions(snapshot, decision)
    lines.extend([
        '',
        'SCENARIO MAP:',
        f"• entry zone: {plan['entry_zone']}",
        f"• trigger: {plan['trigger']}",
        f"• stop: {fmt_price(plan['stop']) if plan['stop'] is not None else 'нет данных'}",
        f"• TP1: {fmt_price(plan['tp1']) if plan['tp1'] is not None else 'нет данных'}",
        f"• TP2: {fmt_price(plan['tp2']) if plan['tp2'] is not None else 'нет данных'}",
    ])

    if decision:
        lines.extend(_edge_lines(decision))

    if decision:
        _append_decision_detail_blocks(lines, decision)

    _append_v52_overlay_blocks(lines, snapshot, decision)
    lines.extend([''] + _entry_score_block(snapshot, decision))
    trade_scenarios = _trade_scenarios_block(snapshot, decision)
    manual_actions = _manual_actions_block(snapshot, decision)
    if trade_scenarios:
        lines.extend([''] + trade_scenarios)
    if manual_actions:
        lines.extend([''] + manual_actions)
    move_lines = _move_type_lines(decision)
    if move_lines:
        lines.extend([''] + move_lines)
    permission_lines = _range_bot_permission_lines(decision)
    if permission_lines:
        lines.extend([''] + permission_lines)

    if pattern_forecast_direction or history_pattern_direction or history_pattern_summary:
        lines.extend([
            "",
            f"PATTERN FORECAST EXTENDED ({', '.join(str(x) for x in pattern_years) if pattern_years else '2025'}):",
            f"• куда вероятнее по паттернам: {pattern_forecast_direction or history_pattern_direction or 'НЕЙТРАЛЬНО'}",
            f"• confidence: {fmt_pct(pattern_forecast_confidence if pattern_forecast_confidence is not None else history_pattern_confidence if history_pattern_confidence is not None else 0.0)}",
        ])
        lines.append(f"• режим памяти: {pattern_scope}")
        if pattern_forecast_regime:
            lines.append(f"• похожий режим: {pattern_forecast_regime}")
        if pattern_forecast_style:
            lines.append(f"• тип движения: {pattern_forecast_style}")
        if pattern_forecast_move:
            lines.append(f"• ожидаемый ход: {pattern_forecast_move}")
        if history_pattern_summary:
            lines.append(f"• вывод: {history_pattern_summary}")

    ml_v2 = _safe_get(snapshot, "ml_v2", None)
    if isinstance(ml_v2, dict):
        ml_prob = float(ml_v2.get('probability') or 0.5)
        ml_edge = float(ml_v2.get('edge_strength') or 0.0)
        ml_follow = float(ml_v2.get('follow_through_probability') or 0.5)
        ml_reversal = float(ml_v2.get('reversal_probability') or 0.5)
        ml_quality = float(ml_v2.get('setup_quality_probability') or 0.5)
        lines.extend([
            "",
            "ML V6.3:",
            f"• setup type: {ml_v2.get('setup_type') or 'unknown'} | status: {ml_v2.get('model_status') or 'unknown'}",
            f"• direction prob: {ml_prob * 100:.1f}% | edge: {ml_edge * 100:.1f}% | confidence: {float(ml_v2.get('confidence') or 0.5) * 100:.1f}%",
            f"• follow-through: {ml_follow * 100:.1f}% | reversal: {ml_reversal * 100:.1f}% | setup quality: {ml_quality * 100:.1f}%",
        ])
        if ml_v2.get('model_path'):
            lines.append(f"• weights: {ml_v2.get('model_path')}")

    derivatives = _safe_get(snapshot, "derivatives_context", None)
    if isinstance(derivatives, dict):
        lines.extend([
            "",
            "LIQUIDITY / DERIVATIVES V6.4:",
            f"• source: {derivatives.get('source') or 'unknown'} | quality: {derivatives.get('data_quality') or derivatives.get('feed_health') or 'UNKNOWN'}",
            f"• price/OI: {derivatives.get('price_oi_regime') or 'NEUTRAL'} | OI state: {derivatives.get('oi_state') or 'UNKNOWN'} | edge: {derivatives.get('derivative_edge') or 'NEUTRAL'}",
            f"• funding: {derivatives.get('funding_state') or 'NEUTRAL'} ({float(derivatives.get('funding_rate') or 0.0):.5f}) | crowding: {derivatives.get('crowding_risk') or 'LOW'}",
            f"• squeeze risk: {derivatives.get('squeeze_risk') or 'LOW'} | liq magnet: {derivatives.get('liq_magnet_side') or 'NEUTRAL'} | trap: {derivatives.get('trap_bias') or 'NEUTRAL'}",
            f"• OI 1h: {float(derivatives.get('oi_change_1h_pct') or 0.0):.2f}% | OI 4h: {float(derivatives.get('oi_change_4h_pct') or 0.0):.2f}% | events: {int(derivatives.get('recent_liquidation_events') or 0)}",
        ])
        notional = float(derivatives.get('recent_liquidation_notional_usd') or 0.0)
        if notional > 0:
            lines.append(f"• recent liq notional: {notional:,.0f} USD".replace(',', ' '))
        if int(derivatives.get('feed_stale_seconds') or 0) > 0:
            lines.append(f"• feed stale: {int(derivatives.get('feed_stale_seconds') or 0)}s")
        if derivatives.get('summary'):
            lines.append(f"• summary: {derivatives.get('summary')}")

    grid_strategy = _safe_get(snapshot, "grid_strategy", None)
    if isinstance(grid_strategy, dict) and grid_strategy.get("enabled"):
        lines.extend([
            "",
            "3 BOT GRID STRATEGY:",
            f"• summary: {grid_strategy.get('summary') or 'нет данных'}",
            f"• средняя 60: {fmt_price(grid_strategy.get('mean60_price') if grid_strategy.get('mean60_price') not in (None, 0, 0.0, '') else current_price)}",
            f"• отклонение: {_fmt_percent_points(grid_strategy.get('deviation_abs_pct') or 0.0, 2)} ({grid_strategy.get('deviation_side') or 'нет данных'})",
            f"• базовая контртренд сторона: {grid_strategy.get('contrarian_side') or 'НЕЙТРАЛЬНО'}",
            f"• ladder action: {grid_strategy.get('ladder_action') or 'нет данных'}",
            f"• range bias action: {grid_strategy.get('range_bias_action') or 'нет данных'}",
        ])
        active_grid = list(grid_strategy.get('active_bots') or [])
        if active_grid:
            lines.append(f"• активные grid-боты: {', '.join(active_grid)}")
        for bot in (grid_strategy.get('bots') or [])[:3]:
            lines.append(
                f"• {bot.get('label')}: {bot.get('action')} | readiness {bot.get('readiness') or 'LOW'} | side {bot.get('side')} | conf {fmt_pct(bot.get('confidence') or 0.0)} | {bot.get('reason') or ''}"
            )
        hint = str(grid_strategy.get('execution_hint') or '').strip()
        if hint:
            lines.append(f"• логика: {hint}")

    learning_forecast = _safe_get(snapshot, "learning_forecast_adjustment", None)
    if isinstance(learning_forecast, dict) and (learning_forecast.get("summary") or abs(float(learning_forecast.get("delta") or 0.0)) >= 0.005):
        delta = float(learning_forecast.get("delta") or 0.0) * 100.0
        sign = "+" if delta >= 0 else ""
        lines.extend([
            "",
            "LEARNING-AWARE FORECAST:",
            f"• влияние обучения: {sign}{delta:.1f}%",
            f"• бот-контекст: {learning_forecast.get('bot_label') or 'нет данных'}",
            f"• вывод: {learning_forecast.get('summary') or 'нет данных'}",
        ])
        for reason in (learning_forecast.get("reasons") or [])[:2]:
            lines.append(f"• {reason}")

    setup_stats = _safe_get(snapshot, "setup_stats", None)
    setup_adj = _safe_get(snapshot, "setup_stats_adjustment", None)
    learning_exec = _safe_get(snapshot, "learning_execution_plan", None)
    if isinstance(setup_stats, dict) and (setup_stats.get('ready') or setup_stats.get('summary')):
        lines.extend([
            "",
            "LEARNING ENGINE PRO V8.2:",
            f"• summary: {setup_stats.get('summary') or 'нет данных'}",
            f"• favored side: {setup_stats.get('favored_side') or 'NEUTRAL'}",
            f"• current family: {str(setup_stats.get('current_family') or 'UNKNOWN').replace('_', ' ')}",
            f"• recent closed: {int(setup_stats.get('closed_trades_recent') or 0)} | win {float(setup_stats.get('recent_winrate') or 0.0) * 100:.1f}% | avg RR {float(setup_stats.get('recent_avg_rr') or 0.0):.2f}",
        ])
        active_setup = setup_stats.get('active_bot') if isinstance(setup_stats.get('active_bot'), dict) else {}
        if active_setup:
            lines.append(f"• active bot history: {active_setup.get('bot_label') or active_setup.get('bot_key')} | samples {int(active_setup.get('samples') or 0)} | win {float(active_setup.get('winrate') or 0.0) * 100:.1f}% | avg RR {float(active_setup.get('avg_rr') or 0.0):.2f}")
        active_family = setup_stats.get('active_family') if isinstance(setup_stats.get('active_family'), dict) else {}
        if active_family:
            lines.append(f"• active family: {active_family.get('label') or active_family.get('family')} | samples {int(active_family.get('samples') or 0)} | win {float(active_family.get('winrate') or 0.0) * 100:.1f}% | avg RR {float(active_family.get('avg_rr') or 0.0):.2f}")
            lines.append(f"• failure profile: {active_family.get('failure_profile') or 'нет данных'}")
        strongest_family = setup_stats.get('strongest_family') if isinstance(setup_stats.get('strongest_family'), dict) else {}
        if strongest_family:
            lines.append(f"• strongest family: {strongest_family.get('label') or strongest_family.get('family')} | hold quality {float(strongest_family.get('hold_quality') or 0.0):.1f}m | avg RR {float(strongest_family.get('avg_rr') or 0.0):.2f}")
        weakest_family = setup_stats.get('weakest_family') if isinstance(setup_stats.get('weakest_family'), dict) else {}
        if weakest_family:
            lines.append(f"• weakest family: {weakest_family.get('label') or weakest_family.get('family')} | avg RR {float(weakest_family.get('avg_rr') or 0.0):.2f} | win {float(weakest_family.get('winrate') or 0.0) * 100:.1f}%")
        if isinstance(setup_adj, dict) and abs(float(setup_adj.get('delta') or 0.0)) >= 0.005:
            delta = float(setup_adj.get('delta') or 0.0) * 100.0
            sign = '+' if delta >= 0 else ''
            lines.append(f"• adjustment: {sign}{delta:.1f}% | aggression {setup_adj.get('aggressiveness') or 'NEUTRAL'}")
            for reason in (setup_adj.get('reasons') or [])[:3]:
                lines.append(f"• {reason}")
        if isinstance(learning_exec, dict) and learning_exec:
            lines.extend([
                f"• action posture: {learning_exec.get('posture') or 'NEUTRAL'}",
                f"• size mode: {learning_exec.get('size_mode') or 'x1.00'}",
                f"• execution map: {learning_exec.get('execution') or 'STANDARD'}",
                f"• top family: {learning_exec.get('strongest_family_label') or 'нет данных'}",
                f"• avoid family: {learning_exec.get('weakest_family_label') or 'нет данных'}",
                f"• learning summary: {learning_exec.get('summary') or 'нет данных'}",
            ])

    lines.extend([
        "",
        f"Качественный вывод: {quality_line}",
    ])

    if context_blocks.get('support') or context_blocks.get('oppose') or context_blocks.get('invalidation'):
        lines.extend(['', 'TEXT QUALITY LAYER:'])
        if context_blocks.get('support'):
            lines.append('• что поддерживает прогноз:')
            for item in context_blocks['support'][:3]:
                lines.append(f'  - {item}')
        if context_blocks.get('oppose'):
            lines.append('• что мешает прогнозу:')
            for item in context_blocks['oppose'][:3]:
                lines.append(f'  - {item}')
        if context_blocks.get('invalidation'):
            lines.append('• что отменит идею:')
            for item in context_blocks['invalidation'][:3]:
                lines.append(f'  - {item}')



    factor = decision.get('factor_breakdown') if isinstance(decision.get('factor_breakdown'), dict) else {}
    scenario_primary = decision.get('scenario_primary') if isinstance(decision.get('scenario_primary'), dict) else {}
    scenario_alt = decision.get('scenario_alternative') if isinstance(decision.get('scenario_alternative'), dict) else {}
    bot_auth_cards = decision.get('bot_authority_cards') if isinstance(decision.get('bot_authority_cards'), list) else []
    if factor:
        lines.extend([
            "",
            "FACTOR HIERARCHY:",
            f"• dominance: {factor.get('dominance')}",
            f"• edge stage: {factor.get('edge_stage')}",
            f"• long total: {fmt_pct(factor.get('long_total', 0.0))}",
            f"• short total: {fmt_pct(factor.get('short_total', 0.0))}",
        ])
        top_long = (factor.get('long_breakdown') or [])[:3]
        top_short = (factor.get('short_breakdown') or [])[:3]
        if top_long:
            lines.append('• long drivers: ' + '; '.join([f"{x.get('factor')} {fmt_pct(x.get('score', 0.0))}" for x in top_long]))
        if top_short:
            lines.append('• short drivers: ' + '; '.join([f"{x.get('factor')} {fmt_pct(x.get('score', 0.0))}" for x in top_short]))

    if scenario_primary or scenario_alt:
        lines.extend([
            "",
            "SCENARIO RANKING:",
            f"• #1 {scenario_primary.get('side', 'NEUTRAL')} | prob {fmt_pct(scenario_primary.get('probability', 0.0))} | status {scenario_primary.get('status', '-')}",
            f"• zone: {scenario_primary.get('zone', 'нет данных')}",
            f"• trigger: {scenario_primary.get('trigger', 'нет данных')}",
            f"• readiness: {fmt_pct(decision.get('trigger_readiness', scenario_primary.get('readiness', 0.0)))}",
            f"• #2 {scenario_alt.get('side', 'NEUTRAL')} | prob {fmt_pct(scenario_alt.get('probability', 0.0))}",
            f"• alt zone: {scenario_alt.get('zone', 'нет данных')}",
            f"• invalidation: {decision.get('scenario_invalidation', 'нет данных')}",
        ])
        if decision.get('pretrade_signal'):
            lines.extend([
                "",
                "PRE-TRADE SIGNAL:",
                f"• status: {decision.get('pretrade_signal')}",
                f"• action: {decision.get('action_text') or decision.get('action_now') or 'ЖДАТЬ'}",
                f"• trigger readiness: {fmt_pct(decision.get('trigger_readiness', scenario_primary.get('readiness', 0.0)))}",
            ])
    if bot_auth_cards:
        lines.extend(["", "BOT AUTHORITY:", f"• authority: {decision.get('bot_authority', '-')}", f"• master mode: {decision.get('master_mode', '-')}"])
        for card in bot_auth_cards[:4]:
            lines.append(f"• {card.get('bot')}: {card.get('status')} | {fmt_pct(card.get('score', 0.0))} | {card.get('note')}")

    lines.extend([
        "",
        "RANGE NOW:",
        f"• состояние: {range_state}",
        f"• low: {fmt_price(range_low)}",
        f"• mid: {fmt_price(range_mid)}",
        f"• high: {fmt_price(range_high)}",
        "",
        f"CT NOW: {ct_now}",
        f"GINAREA ADVICE: {ginarea_advice}",
    ])

    scenario_text = str(decision.get("scenario_text") or decision.get("base_case") or "").strip()
    trigger_text = str(decision.get("trigger_text") or "").strip()
    bull_case = str(decision.get("bull_case") or "").strip()
    bear_case = str(decision.get("bear_case") or "").strip()
    scenario_invalidation = str(decision.get("scenario_invalidation") or decision.get("invalidation") or "").strip()
    if scenario_text or trigger_text or bull_case or bear_case:
        lines.extend(["", "SCENARIO NOW:"])
        if scenario_text:
            lines.append(f"• {scenario_text}")
        if bull_case:
            lines.append(f"• {bull_case}")
        if bear_case:
            lines.append(f"• {bear_case}")
        if trigger_text:
            lines.append(f"• {trigger_text}")
        trigger_up = str(decision.get("trigger_up") or "").strip()
        trigger_down = str(decision.get("trigger_down") or "").strip()
        if trigger_up:
            lines.append(f"• {trigger_up}")
        if trigger_down:
            lines.append(f"• {trigger_down}")
        if scenario_invalidation:
            lines.append(f"• {scenario_invalidation}")

    expectation = decision.get("expectation") or []
    if expectation:
        lines.extend(["", "Что ждать дальше:"])
        for item in expectation[:3]:
            lines.append(f"• {item}")

    reversal_patterns = _safe_get(snapshot, "reversal_patterns", None) or []
    if reversal_patterns:
        lines.extend(["", "REVERSAL PATTERNS:"])
        for item in reversal_patterns[:3]:
            lines.append(f"• {item}")

    if decision_summary:
        lines.extend(["", f"Итог: {decision_summary}"])

    best_trade_play = decision.get('best_trade_play')
    if best_trade_play:
        action_output = decision.get('action_output') if isinstance(decision.get('action_output'), dict) else {}
        move_type_ctx = decision.get('move_type_context') if isinstance(decision.get('move_type_context'), dict) else {}
        best_trade = decision.get('best_trade') if isinstance(decision.get('best_trade'), dict) else {}
        lines.extend([
            '',
            'NEXTGEN ACTION LAYER:',
            f"• market mode: {action_output.get('market_mode') or move_type_ctx.get('regime') or '-'}",
            f"• market submode: {move_type_ctx.get('type') or '-'}",
            f"• best trade: {best_trade.get('best_play') or best_trade.get('play') or decision.get('best_trade_play') or '-'}",
            f"• best side: {best_trade.get('best_side') or best_trade.get('side') or decision.get('best_trade_side') or '-'}",
            f"• best score: {best_trade.get('best_score') or best_trade.get('score') or decision.get('best_trade_score') or 0.0}%",
            f"• action now: {decision.get('bot_mode_action') or action_output.get('bot_mode_action') or decision.get('action') or '-'}",
        ])
        if decision.get('action_layer_hint'):
            lines.append(f"• tactical hint: {decision.get('action_layer_hint')}")
        if decision.get('action_note'):
            lines.append(f"• note: {decision.get('action_note')}")
        lines.extend([
            '',
            'GRID CONTROL:',
            f"• long grid: {decision.get('long_grid', '-') }",
            f"• short grid: {decision.get('short_grid', '-') }",
        ])
        if decision.get('expectancy_long') is not None:
            lines.extend([
                '',
                'EXPECTANCY:',
                f"• long: {decision.get('expectancy_long', 0.0):.3f}",
                f"• short: {decision.get('expectancy_short', 0.0):.3f}",
            ])
        if decision.get('impulse_strength'):
            lines.extend([
                '',
                'VOLATILITY / IMPULSE:',
                f"• impulse: {decision.get('impulse_strength', '-') }",
                f"• countertrend risk: {decision.get('countertrend_risk', '-') }",
                f"• {decision.get('volatility_summary', '')}",
            ])
        if decision.get('orderflow_bias'):
            lines.extend([
                '',
                'ORDERFLOW:',
                f"• bias: {decision.get('orderflow_bias', '-') }",
                f"• {decision.get('orderflow_summary', '')}",
            ])
        if decision.get('liquidation_magnet'):
            lines.extend([
                '',
                'LIQUIDATIONS:',
                f"• magnet: {decision.get('liquidation_magnet', '-') }",
                f"• state: {decision.get('liquidity_state_live', '-') }",
                f"• cascade risk: {decision.get('liquidation_cascade_risk', '-') }",
                f"• {decision.get('liquidation_summary', '')}",
            ])
        if decision.get('fast_move_classification'):
            lines.extend([
                '',
                'FAST MOVE / LIVE INTERPRETER:',
                f"• type: {decision.get('fast_move_classification', '-') }",
                f"• summary: {decision.get('fast_move_summary', '-') }",
                f"• action: {decision.get('fast_move_action', '-') }",
                f"• longs: {decision.get('fast_move_long_action', '-') }",
                f"• shorts: {decision.get('fast_move_short_action', '-') }",
            ])
            if decision.get('continuation_target'):
                lines.append(f"• continuation target: {decision.get('continuation_target')}")
            if decision.get('fast_move_watch'):
                lines.append(f"• watch: {decision.get('fast_move_watch')}")
            if decision.get('fast_move_alert'):
                lines.append(f"• alert: {decision.get('fast_move_alert')}")
        if decision.get('scenario_base'):
            lines.extend([
                '',
                'SCENARIOS:',
                f"• base: {decision.get('scenario_base', '')}",
                f"• alt: {decision.get('scenario_alt', '')}",
                f"• invalidation: {decision.get('scenario_invalidation', '')}",
                f"• pre-trade: {decision.get('pretrade_signal', 'WAIT')}",
                f"• smart neutral: {decision.get('smart_neutral', '-')}",
            ])
            for reason in (decision.get('scenario_reasons') or [])[:3]:
                lines.append(f"• {reason}")
        if decision.get('is_no_trade'):
            lines.extend(['', 'NO TRADE FILTER:'])
            lines.append(f"• level: {decision.get('no_trade_level', '-') }")
            for reason in (decision.get('no_trade_reasons') or [])[:4]:
                lines.append(f"• {reason}")

    return "\n".join(lines)


def build_my_position_text(state: PositionSnapshot | None = None) -> str:
    state = state or PositionSnapshot.from_dict(load_position_state())
    if not state.has_position:
        return "\n".join([
            "📂 МОЯ ПОЗИЦИЯ",
            "",
            "Сейчас сохранённой позиции нет.",
            "Можно использовать кнопки ОТКРЫТЬ ЛОНГ или ОТКРЫТЬ ШОРТ.",
        ])
    return "\n".join([
        "📂 МОЯ ПОЗИЦИЯ",
        "",
        f"Сторона: {state.side}",
        f"Инструмент: {state.symbol}",
        f"Таймфрейм: {state.timeframe}",
        f"Цена входа: {fmt_price(state.entry_price)}",
        f"Открыта: {state.opened_at or 'не указано'}",
        f"Комментарий: {state.comment or 'нет'}",
    ])


def build_journal_status_text(state: JournalSnapshot | None = None) -> str:
    state = state or JournalSnapshot.from_dict(load_trade_journal())
    if not state.trade_id:
        return "\n".join([
            "📘 JOURNAL STATUS",
            "",
            "Активного журнала сделки нет.",
            "Сначала открой позицию через ОТКРЫТЬ ЛОНГ или ОТКРЫТЬ ШОРТ.",
        ])

    lines = [
        "📘 JOURNAL STATUS",
        "",
        f"trade_id: {state.trade_id}",
        f"Сторона: {state.side}",
        f"Инструмент: {state.symbol}",
        f"Таймфрейм: {state.timeframe}",
        f"Entry: {fmt_price(state.entry_price)}",
        f"SL: {fmt_price(state.sl)}",
        f"TP1: {fmt_price(state.tp1)}",
        f"TP2: {fmt_price(state.tp2)}",
        f"BE moved: {'да' if state.be_moved else 'нет'}",
        f"Partial done: {'да' if state.partial_done else 'нет'}",
        f"TP1 hit: {'да' if state.tp1_hit else 'нет'}",
        f"TP2 hit: {'да' if state.tp2_hit else 'нет'}",
        f"Статус: {state.status or 'OPEN'}",
    ]

    if state.final_result:
        lines.append(f"Результат: {state.final_result}")
    if state.final_rr is not None:
        lines.append(f"Final RR: {state.final_rr}")
    if state.comment:
        lines.append(f"Комментарий: {state.comment}")

    return "\n".join(lines)
