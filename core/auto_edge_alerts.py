from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

MASTER_TIMEFRAME = '1h'
SIGNAL_MEMORY_LIMIT = 12
CONFIRM_CYCLES = 2
CONFIRM_SECONDS = 120
EDGE_ENTER_UPPER = 0.72
EDGE_EXIT_UPPER = 0.65
EDGE_ENTER_LOWER = 0.28
EDGE_EXIT_LOWER = 0.35

from services.analysis_service import AnalysisRequestContext

try:
    from core.telegram_formatter import _derive_v16_view  # type: ignore
except Exception:  # pragma: no cover
    _derive_v16_view = None

logger = logging.getLogger(__name__)
STATE_FILE = Path('state/auto_edge_alert_state.json')


# ── TZ-AUTO-EDGE-ALERTS-DEDUP-WIRE-UP ──────────────────────────────────────
#
# DedupLayer wrapping replaces the legacy 180s _should_send cooldown with a
# state-change + cluster-collapse pipeline:
#   - State-change: only emit when scenario_confidence (0..100) differs from
#     the last emitted value by ≥ value_delta_min (5.0 pp default).
#   - Cluster: SETUP_ON bursts within ±0.5% price AND 30 min collapse into one
#     summary message instead of N pings.
#
# Env toggle: DEDUP_LAYER_ENABLED_FOR_AUTO_EDGE_ALERTS=1 (default ON). When
# disabled (=0), the legacy cooldown gate stays the only check — no behavior
# change vs pre-wire.

DEDUP_LAYER_ENABLED_FOR_AUTO_EDGE_ALERTS = bool(
    int(os.environ.get('DEDUP_LAYER_ENABLED_FOR_AUTO_EDGE_ALERTS', '1'))
)

# Lazy-init singleton. None until first dedup evaluation triggers _get_dedup_layer().
_AUTO_EDGE_DEDUP_LAYER: Any = None
_AUTO_EDGE_DEDUP_LOCK = threading.Lock()
_AUTO_EDGE_EMITTER_NAME = 'auto_edge_alerts'


def _get_dedup_layer():
    """Lazy initializer for the module-level DedupLayer.

    Imports inside function to avoid circular-import risk (dedup_layer is a
    leaf module but its config_module sibling imports DedupLayer too).
    """
    global _AUTO_EDGE_DEDUP_LAYER
    if not DEDUP_LAYER_ENABLED_FOR_AUTO_EDGE_ALERTS:
        return None
    if _AUTO_EDGE_DEDUP_LAYER is not None:
        return _AUTO_EDGE_DEDUP_LAYER
    with _AUTO_EDGE_DEDUP_LOCK:
        if _AUTO_EDGE_DEDUP_LAYER is not None:
            return _AUTO_EDGE_DEDUP_LAYER
        try:
            from services.telegram.dedup_layer import DedupLayer
            from services.telegram.dedup_configs import AUTO_EDGE_ALERTS_DEDUP_CONFIG
            _AUTO_EDGE_DEDUP_LAYER = DedupLayer(AUTO_EDGE_ALERTS_DEDUP_CONFIG)
            logger.info(
                'auto_edge_alerts.dedup_layer.initialized cooldown=%ds delta=%.1f cluster=%s window=%ds price_delta=%.2f%%',
                AUTO_EDGE_ALERTS_DEDUP_CONFIG.cooldown_sec,
                AUTO_EDGE_ALERTS_DEDUP_CONFIG.value_delta_min,
                AUTO_EDGE_ALERTS_DEDUP_CONFIG.cluster_enabled,
                AUTO_EDGE_ALERTS_DEDUP_CONFIG.cluster_window_sec,
                AUTO_EDGE_ALERTS_DEDUP_CONFIG.cluster_price_delta_pct,
            )
        except Exception:
            logger.exception('auto_edge_alerts.dedup_layer.init_failed — falling back to legacy cooldown')
            _AUTO_EDGE_DEDUP_LAYER = None
    return _AUTO_EDGE_DEDUP_LAYER


def _reset_dedup_layer_for_tests() -> None:
    """Reset module singleton — tests use this to start with a fresh layer.

    Called by test fixtures to avoid cross-test contamination of the in-memory
    state. Production code never calls this.
    """
    global _AUTO_EDGE_DEDUP_LAYER
    with _AUTO_EDGE_DEDUP_LOCK:
        _AUTO_EDGE_DEDUP_LAYER = None


def _apply_dedup(
    slot_key: str,
    kind: str,
    value: float,
    price: Optional[float],
    now_ts: float,
) -> tuple[bool, str, Optional[List[float]]]:
    """Evaluate dedup for an auto_edge alert candidate.

    Returns:
        (should_send, reason_ru, cluster_levels)
        - should_send=False if the dedup gate suppresses.
        - cluster_levels is non-None and len>1 when a cluster has been
          collapsed into this single emit (caller can include the levels in
          the message body).

    Mechanics:
      1. State-change check (cooldown + value_delta_min) on scenario_confidence.
         If suppressed, return immediately.
      2. For SETUP_ON kind only, when price is known, run cluster_evaluate to
         buffer near-priced bursts. SETUP_OFF and other kinds skip clustering
         (the operator wants every "setup gone" event since they are rare).
    """
    layer = _get_dedup_layer()
    if layer is None:
        return True, 'dedup layer disabled — пропускаем', None

    # Step 1: state-change gate (cooldown + delta) on scenario confidence.
    state_decision = layer.evaluate(
        emitter=_AUTO_EDGE_EMITTER_NAME,
        key=slot_key,
        value=float(value),
        now_ts=now_ts,
    )
    if not state_decision.should_emit:
        return False, state_decision.reason_ru, None

    # Step 2: cluster collapse — only for SETUP_ON, only if we have a price.
    # SETUP_OFF events skip clustering: setup-disappearance is rare and operator
    # values each occurrence individually.
    if kind == 'SETUP_ON' and price is not None and price > 0:
        cluster_decision = layer.evaluate_cluster(
            emitter=_AUTO_EDGE_EMITTER_NAME,
            key=slot_key,
            price=float(price),
            now_ts=now_ts,
        )
        if not cluster_decision.should_emit:
            return False, cluster_decision.reason_ru, None
        # If cluster_levels has >1 entry, the caller can mention the cluster
        # in the message. For a 1-level "cluster" (just this event), behavior
        # is identical to no cluster.
        return True, cluster_decision.reason_ru, cluster_decision.cluster_levels

    return True, state_decision.reason_ru, None


def _record_dedup_emit(slot_key: str, value: float, now_ts: float) -> None:
    """Record a successful emit so the next _apply_dedup() sees it."""
    layer = _get_dedup_layer()
    if layer is None:
        return
    try:
        layer.record_emit(
            emitter=_AUTO_EDGE_EMITTER_NAME,
            key=slot_key,
            value=float(value),
            now_ts=now_ts,
        )
    except Exception:
        logger.exception('auto_edge_alerts.dedup_record_failed slot_key=%s', slot_key)

_ACTIVE_GRID_STATES = {'RUN', 'REDUCE', 'ARM'}
_PAUSE_ACTIONS = {'PAUSE_MID_RANGE', 'PAUSE MID RANGE', 'ПАУЗА В СЕРЕДИНЕ ДИАПАЗОНА'}
_EDGE_ACTIONS = {'ARM_ONLY_AT_EDGE', 'ARM ONLY AT EDGE', 'ГОТОВИТЬ ТОЛЬКО У КРАЯ'}


def _safe_str(value: Any, default: str = '') -> str:
    if value is None:
        return default
    return str(value).strip()


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or value == '':
            return default
        return float(value)
    except Exception:
        return default


def _load_state() -> Dict[str, Any]:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding='utf-8'))
        except Exception:
            return {'slots': {}}
    return {'slots': {}}


def _save_state(state: Dict[str, Any]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(STATE_FILE)


def _normalize_chat_ids(chat_id_raw: Any) -> List[int]:
    raw = _safe_str(chat_id_raw)
    if not raw:
        return []
    out: List[int] = []
    for part in raw.replace(';', ',').split(','):
        token = part.strip()
        if not token:
            continue
        try:
            out.append(int(token))
        except Exception:
            logger.warning('auto_edge_alerts.invalid_chat_id value=%s', token)
    return out


def _snapshot_payload(snapshot: Any) -> Dict[str, Any]:
    if snapshot is None:
        return {}
    if isinstance(snapshot, dict):
        return dict(snapshot)
    if hasattr(snapshot, 'to_dict'):
        try:
            data = snapshot.to_dict()
            if isinstance(data, dict):
                return data
        except Exception:
            return {}
    return {}


def _derive_view(payload: Dict[str, Any]) -> Dict[str, Any]:
    if _derive_v16_view is not None:
        try:
            view = _derive_v16_view(payload) or {}
            if isinstance(view, dict) and view:
                return view
        except Exception:
            logger.exception('auto_edge_alerts.derive_v16_view_failed')
    return {}


def _is_pause_action(action_now: str) -> bool:
    upper = _safe_str(action_now).upper()
    return upper in _PAUSE_ACTIONS or 'ПАУЗА' in upper


def _has_setup(view: Dict[str, Any]) -> bool:
    if not view:
        return False
    action_now = _safe_str(view.get('action_now'))
    if _is_pause_action(action_now):
        return False
    long_grid = _safe_str(view.get('long_grid')).upper()
    short_grid = _safe_str(view.get('short_grid')).upper()
    return long_grid in _ACTIVE_GRID_STATES or short_grid in _ACTIVE_GRID_STATES


def _build_current(snapshot: Any, timeframe: str) -> Dict[str, Any]:
    payload = _snapshot_payload(snapshot)
    view = _derive_view(payload)
    price = view.get('price') or payload.get('price')
    ctx = view.get('ctx') if isinstance(view.get('ctx'), dict) else {}
    return {
        'timeframe': timeframe,
        'price': price,
        'action_now': _safe_str(view.get('action_now') or payload.get('action_now')),
        'action_title': _safe_str(view.get('authority_title_ru') or view.get('action_now') or payload.get('action_now') or 'ПАУЗА'),
        'runtime_line': _safe_str(view.get('runtime_line') or ''),
        'forecast_text': _safe_str(view.get('forecast_text') or ''),
        'target_text': _safe_str(view.get('target_text') or ''),
        'impulse_text': _safe_str(view.get('impulse_text') or ''),
        'scenario_text': _safe_str(view.get('scenario_text') or ''),
        'invalidation_text': _safe_str(view.get('invalidation_text') or ''),
        'scenario_confidence': _safe_int(view.get('scenario_confidence'), 0),
        'auto_risk_mode': _safe_str(view.get('auto_risk_mode') or ''),
        'long_grid': _safe_str(view.get('long_grid') or '').upper(),
        'short_grid': _safe_str(view.get('short_grid') or '').upper(),
        'range_quality_text': _safe_str(view.get('range_quality_text') or ''),
        'range_position': _safe_float(ctx.get('range_position') if ctx else payload.get('range_position')),
        'range_state': _safe_str(ctx.get('range_state') if ctx else payload.get('range_state')),
        'range_low': _safe_float(payload.get('range_low')),
        'range_mid': _safe_float(payload.get('range_mid')),
        'range_high': _safe_float(payload.get('range_high')),
        'master_key': '|'.join([
            _safe_str(view.get('authority_title_ru') or view.get('action_now') or ''),
            _safe_str(view.get('runtime_line') or ''),
            _safe_str(view.get('forecast_text') or ''),
            _safe_str(view.get('target_text') or ''),
            _safe_str(view.get('scenario_text') or ''),
            _safe_str(view.get('auto_risk_mode') or ''),
        ]),
        'has_setup': _has_setup(view),
        'payload_ok': bool(view),
    }


def _fmt_price(value: Any) -> str:
    try:
        if value is None or value == '':
            return 'нет данных'
        return f"{float(value):,.2f}".replace(',', ' ')
    except Exception:
        return str(value or 'нет данных')


def _event_kind(previous: Dict[str, Any], current: Dict[str, Any]) -> str:
    prev_setup = bool(previous.get('has_setup'))
    curr_setup = bool(current.get('has_setup'))
    if not previous:
        return ''
    if (not prev_setup) and curr_setup:
        return 'SETUP_ON'
    if prev_setup and (not curr_setup):
        return 'SETUP_OFF'
    return ''


def _runtime_summary(payload: Dict[str, Any]) -> str:
    parts = []
    action = _safe_str(payload.get('action_title'))
    runtime = _safe_str(payload.get('runtime_line'))
    scenario = _safe_str(payload.get('scenario_text'))
    if action:
        parts.append(action)
    if runtime:
        parts.append(runtime)
    if scenario:
        parts.append(scenario)
    return ' | '.join(parts) if parts else 'нет данных'


def _scenario_delta(previous: Dict[str, Any], current: Dict[str, Any]) -> int:
    return _safe_int(current.get('scenario_confidence')) - _safe_int(previous.get('scenario_confidence'))


def _delta_strength_text(previous: Dict[str, Any], current: Dict[str, Any]) -> str:
    if not previous:
        return 'нет базы для сравнения'
    delta = _scenario_delta(previous, current)
    if delta >= 8:
        return f'🟢 усилился (+{delta} п.п.)'
    if delta >= 3:
        return f'🟡 слегка усилился (+{delta} п.п.)'
    if delta <= -8:
        return f'🔴 ослаб (+{abs(delta)} п.п.)'
    if delta <= -3:
        return f'🟠 слегка ослаб ({delta} п.п.)'
    return '↔️ почти без изменений'


def _action_impact_text(previous: Dict[str, Any], current: Dict[str, Any], note: str = '') -> str:
    prev_action = _safe_str(previous.get('action_title'))
    curr_action = _safe_str(current.get('action_title'))
    prev_runtime = _safe_str(previous.get('runtime_line'))
    curr_runtime = _safe_str(current.get('runtime_line'))
    if note:
        return note
    if not previous:
        return 'первичная фиксация состояния'
    if prev_action == curr_action and prev_runtime == curr_runtime:
        return 'действие не меняется'
    if 'ПАУЗА' in prev_action and 'ПАУЗА' not in curr_action:
        return 'действие усилилось: появился рабочий режим'
    if 'ПАУЗА' not in prev_action and 'ПАУЗА' in curr_action:
        return 'действие ослабло: возврат в паузу'
    return 'действие изменилось'


def _append_memory(slot: Dict[str, Any], entry: Dict[str, Any]) -> None:
    memory = slot.setdefault('memory', [])
    if not isinstance(memory, list):
        memory = []
    memory.append(entry)
    slot['memory'] = memory[-SIGNAL_MEMORY_LIMIT:]


def _last_memory_line(slot: Dict[str, Any]) -> str:
    memory = slot.get('memory') if isinstance(slot.get('memory'), list) else []
    if not memory:
        return ''
    last = memory[-1]
    if not isinstance(last, dict):
        return ''
    return _safe_str(last.get('summary'))


def _is_upper_side(state: Dict[str, Any]) -> bool:
    return _safe_str(state.get('short_grid')).upper() == 'RUN' or 'ШОРТ' in _safe_str(state.get('forecast_text')).upper()


def _is_lower_side(state: Dict[str, Any]) -> bool:
    return _safe_str(state.get('long_grid')).upper() == 'RUN' or 'ЛОНГ' in _safe_str(state.get('forecast_text')).upper()


def _passes_hysteresis(previous: Dict[str, Any], current: Dict[str, Any]) -> bool:
    pos = _safe_float(current.get('range_position'))
    if pos is None:
        return True
    prev_setup = bool(previous.get('has_setup')) if previous else False
    curr_setup = bool(current.get('has_setup'))
    if (not prev_setup) and curr_setup:
        return pos >= EDGE_ENTER_UPPER or pos <= EDGE_ENTER_LOWER
    if prev_setup and (not curr_setup):
        if _is_upper_side(previous):
            return pos <= EDGE_EXIT_UPPER
        if _is_lower_side(previous):
            return pos >= EDGE_EXIT_LOWER
    return True


def _build_alert_text(previous: Dict[str, Any], current: Dict[str, Any], kind: str, note: str = '', slot: Dict[str, Any] | None = None) -> str:
    header_map = {
        'SETUP_ON': '🔔 V17.4 СИГНАЛ — ПОЯВИЛСЯ СЕТАП',
        'SETUP_OFF': '🛑 V17.4 СИГНАЛ — СЕТАП ОТМЕНЁН',
    }
    what_map = {
        'SETUP_ON': 'появилось рабочее состояние для управления сетками',
        'SETUP_OFF': 'рабочее состояние снято, сетки больше не форсировать',
    }
    title = header_map.get(kind, '🔔 V17.4 СИГНАЛ')
    lines = [title, '']
    lines.append(f"• таймфрейм: {current.get('timeframe')}")
    lines.append(f"• цена: {_fmt_price(current.get('price'))}")
    lines.append(f"• что изменилось: {what_map.get(kind, 'состояние обновилось')}")
    if previous:
        lines.append(f"• было: {_runtime_summary(previous)}")
    lines.append(f"• стало: {_runtime_summary(current)}")
    lines.append(f"• сила сценария: {_delta_strength_text(previous, current)}")
    lines.append(f"• влияние на действие: {_action_impact_text(previous, current, note=note)}")
    last_line = _last_memory_line(slot or {})
    if last_line:
        lines.append(f"• память сигнала: {last_line}")
    if current.get('forecast_text'):
        lines.append(f"• прогноз рынка: {current.get('forecast_text')}")
    if current.get('target_text'):
        lines.append(f"• цель движения: {current.get('target_text')}")
    if current.get('impulse_text'):
        lines.append(f"• импульс: {current.get('impulse_text')}")
    if current.get('scenario_confidence'):
        lines.append(f"• уверенность сценария: {current.get('scenario_confidence')}%")
    if current.get('auto_risk_mode'):
        lines.append(f"• авто-риск: {current.get('auto_risk_mode')}")
    if current.get('invalidation_text'):
        lines.append(f"• слом сценария: {current.get('invalidation_text')}")
    return '\n'.join(lines)


def _candidate_matches(slot: Dict[str, Any], kind: str, current: Dict[str, Any]) -> bool:
    candidate = slot.get('candidate') if isinstance(slot.get('candidate'), dict) else {}
    if not candidate:
        return False
    return _safe_str(candidate.get('kind')) == kind and _safe_str(candidate.get('master_key')) == _safe_str(current.get('master_key'))


def _update_candidate(slot: Dict[str, Any], kind: str, current: Dict[str, Any], now_ts: float) -> Dict[str, Any]:
    if _candidate_matches(slot, kind, current):
        candidate = dict(slot.get('candidate') or {})
        candidate['confirm_count'] = int(candidate.get('confirm_count') or 0) + 1
        candidate['last_seen_ts'] = now_ts
        slot['candidate'] = candidate
        return candidate
    candidate = {
        'kind': kind,
        'master_key': _safe_str(current.get('master_key')),
        'confirm_count': 1,
        'first_seen_ts': now_ts,
        'last_seen_ts': now_ts,
    }
    slot['candidate'] = candidate
    return candidate


def _candidate_confirmed(candidate: Dict[str, Any], now_ts: float) -> bool:
    confirm_count = int(candidate.get('confirm_count') or 0)
    first_seen_ts = float(candidate.get('first_seen_ts') or now_ts)
    return confirm_count >= CONFIRM_CYCLES or (now_ts - first_seen_ts) >= CONFIRM_SECONDS


def build_auto_edge_alert(snapshot: Any, timeframe: str, slot_key: str, cooldown_seconds: int = 180) -> str:
    state = _load_state()
    slots = state.setdefault('slots', {})
    slot = slots.setdefault(slot_key, {})
    current = _build_current(snapshot, timeframe)
    previous = slot.get('current') if isinstance(slot.get('current'), dict) else {}
    now_ts = time.time()

    if not current.get('payload_ok'):
        slot['updated_at'] = now_ts
        slot['current'] = current
        _save_state(state)
        return ''

    # Keep non-master timeframes in state for context, but never emit actionable alerts from them.
    if str(timeframe).lower() != MASTER_TIMEFRAME.lower():
        slot['current'] = current
        slot['updated_at'] = now_ts
        _save_state(state)
        return ''

    kind = _event_kind(previous, current)
    alert_key = f"{kind}|{current.get('master_key')}" if kind else ''
    last_key = _safe_str(slot.get('last_alert_key'))
    last_ts = float(slot.get('last_alert_ts') or 0.0)
    text = ''

    if kind and _passes_hysteresis(previous, current):
        candidate = _update_candidate(slot, kind, current, now_ts)
        if _candidate_confirmed(candidate, now_ts):
            if alert_key != last_key and (now_ts - last_ts) >= max(int(cooldown_seconds or 0), 300):
                # DedupLayer gate (TZ-AUTO-EDGE-ALERTS-DEDUP-WIRE-UP). When the
                # env toggle is on, this state-change + cluster-collapse pipe
                # filters bursts that the legacy 300s cooldown alone cannot
                # catch (e.g. confidence flickering ±2 pp every 30 minutes).
                scenario_confidence = _safe_int(current.get('scenario_confidence'), 0)
                price_for_cluster = _safe_float(current.get('price'))
                should_send, dedup_reason, cluster_levels = _apply_dedup(
                    slot_key=slot_key,
                    kind=kind,
                    value=float(scenario_confidence),
                    price=price_for_cluster,
                    now_ts=now_ts,
                )
                if not should_send:
                    logger.info(
                        'auto_edge_alerts.dedup_layer_suppress slot=%s kind=%s reason=%s',
                        slot_key, kind, dedup_reason,
                    )
                    # Still mark candidate as resolved — we do NOT want to
                    # re-evaluate the same candidate forever after dedup
                    # suppression. Record that a confirmed candidate fired
                    # but was dedup-suppressed via last_alert_key/ts so the
                    # next 300s cooldown applies normally.
                    slot['last_alert_key'] = alert_key
                    slot['last_alert_ts'] = now_ts
                    slot.pop('candidate', None)
                else:
                    impact_note = _action_impact_text(previous, current)
                    text = _build_alert_text(previous, current, kind, note=impact_note, slot=slot)
                    # Append cluster footnote if multiple SETUP_ON levels
                    # collapsed into this single emit.
                    if cluster_levels and len(cluster_levels) > 1 and text:
                        levels_str = ', '.join(f"{p:,.0f}".replace(',', ' ') for p in cluster_levels)
                        text = f"{text}\n• кластер уровней (схлопнут): {levels_str}"
                    slot['last_alert_key'] = alert_key
                    slot['last_alert_ts'] = now_ts
                    _append_memory(slot, {
                        'ts': int(now_ts),
                        'kind': kind,
                        'summary': impact_note,
                        'from': _runtime_summary(previous),
                        'to': _runtime_summary(current),
                        'delta_confidence': _scenario_delta(previous, current),
                        'dedup_reason': dedup_reason,
                    })
                    slot.pop('candidate', None)
                    _record_dedup_emit(slot_key, float(scenario_confidence), now_ts)
        # else: hold candidate silently until confirmed
    else:
        slot.pop('candidate', None)

    slot['current'] = current
    slot['updated_at'] = now_ts
    _save_state(state)
    return text


class AutoEdgeAlertService:
    def __init__(self, bot_obj: Any, chat_id_raw: Any, *, timeframes: Iterable[str] = ('15m', '1h'), poll_interval_sec: int = 60, cooldown_sec: int = 180) -> None:
        self.bot = bot_obj
        self.chat_ids = _normalize_chat_ids(chat_id_raw)
        self.timeframes = [str(tf).strip() for tf in timeframes if str(tf).strip()] or ['15m', '1h']
        self.poll_interval_sec = max(int(poll_interval_sec or 60), 30)
        self.cooldown_sec = max(int(cooldown_sec or 180), 60)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    @property
    def enabled(self) -> bool:
        return bool(self.chat_ids)

    def start(self) -> None:
        if not self.enabled:
            logger.info('auto_edge_alerts.disabled reason=no_chat_id')
            return
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, name='auto-edge-alerts', daemon=True)
        self._thread.start()
        logger.info('auto_edge_alerts.started chats=%s tfs=%s interval=%s cooldown=%s', self.chat_ids, self.timeframes, self.poll_interval_sec, self.cooldown_sec)

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            for timeframe in self.timeframes:
                try:
                    ctx = AnalysisRequestContext()
                    snapshot = ctx.get_snapshot(timeframe)
                    for chat_id in self.chat_ids:
                        slot_key = f'{chat_id}:{timeframe}'
                        text = build_auto_edge_alert(snapshot, timeframe, slot_key=slot_key, cooldown_seconds=self.cooldown_sec)
                        if text:
                            self.bot.send_message(chat_id, text)
                except Exception:
                    logger.exception('auto_edge_alerts.scan_failed timeframe=%s', timeframe)
            self._stop.wait(self.poll_interval_sec)
