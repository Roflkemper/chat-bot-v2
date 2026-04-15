from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, Optional

from utils.safe_io import atomic_write_json, safe_read_json
from storage.personal_bot_learning import update_learning_from_closed_trade

TRADE_JOURNAL_FILE = "trade_journal_state.json"
TRADE_JOURNAL_JSONL_FILE = "state/trade_journal.jsonl"


def _now() -> datetime:
    return datetime.now()


def _now_str() -> str:
    return _now().strftime("%Y-%m-%d %H:%M:%S")


def _parse_dt(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    formats = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"]
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt)
        except Exception:
            continue
    return None


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        if hasattr(value, "item") and callable(value.item):
            value = value.item()
    except Exception:
        pass
    try:
        return float(value)
    except Exception:
        return None


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, set):
        return [_json_safe(v) for v in sorted(list(value), key=lambda x: str(x))]
    try:
        if hasattr(value, "item") and callable(value.item):
            return _json_safe(value.item())
    except Exception:
        pass
    try:
        json.dumps(value)
        return value
    except Exception:
        return str(value)


def _compute_result_pct(side: Any, entry_price: Any, exit_price: Any) -> Optional[float]:
    side_u = str(side or "").upper()
    entry = _to_float(entry_price)
    exit_ = _to_float(exit_price)
    if entry is None or exit_ is None or entry == 0:
        return None
    if side_u == "LONG":
        result = ((exit_ - entry) / entry) * 100.0
    elif side_u == "SHORT":
        result = ((entry - exit_) / entry) * 100.0
    else:
        return None
    return round(result, 4)


def _compute_result_rr(result_pct: Any, risk_pct: Any = None) -> Optional[float]:
    result_pct_f = _to_float(result_pct)
    risk_pct_f = _to_float(risk_pct)
    if result_pct_f is None:
        return None
    if risk_pct_f is None or risk_pct_f == 0:
        return None
    return round(result_pct_f / risk_pct_f, 4)


def _compute_holding_time_minutes(opened_at: Any, closed_at: Any) -> Optional[int]:
    opened_dt = _parse_dt(opened_at)
    closed_dt = _parse_dt(closed_at)
    if opened_dt is None or closed_dt is None:
        return None
    diff_sec = (closed_dt - opened_dt).total_seconds()
    if diff_sec < 0:
        return None
    return int(round(diff_sec / 60.0))


def _default_journal() -> Dict[str, Any]:
    return {
        "has_active_trade": False,
        "trade_id": None,
        "symbol": "BTCUSDT",
        "side": None,
        "timeframe": "1h",
        "entry_price": None,
        "opened_at": None,
        "status": "NO_TRADE",
        "tp1_hit": False,
        "tp1_hit_at": None,
        "tp2_hit": False,
        "tp2_hit_at": None,
        "be_moved": False,
        "be_moved_at": None,
        "partial_exit_done": False,
        "partial_exit_at": None,
        "closed": False,
        "closed_at": None,
        "close_reason": None,
        "notes": None,
        "decision_snapshot": None,
        "analysis_snapshot": None,
        "exit_price": None,
        "result_pct": None,
        "result_rr": None,
        "holding_time_minutes": None,
        "close_context_snapshot": None,
        "exit_quality": None,
        "exit_reason_classifier": None,
        "post_trade_summary": None,
        "lifecycle_state": "NO_TRADE",
        "runner_active": False,
        "lifecycle_history": [],
        "last_lifecycle_event_at": None,
    }


def _append_lifecycle_event(state: Dict[str, Any], state_name: str, note: Optional[str] = None) -> Dict[str, Any]:
    history = state.get("lifecycle_history") or []
    event = {"state": str(state_name or "NO_TRADE").upper(), "at": _now_str()}
    if note:
        event["note"] = str(note)
    history.append(event)
    state["lifecycle_history"] = history[-30:]
    state["last_lifecycle_event_at"] = event["at"]
    return state


def _sync_lifecycle_state(state: Dict[str, Any], requested_state: Optional[str] = None, note: Optional[str] = None) -> Dict[str, Any]:
    prev = str(state.get("lifecycle_state") or "NO_TRADE").upper()
    next_state = str(requested_state or prev or "NO_TRADE").upper()

    if requested_state is None:
        if bool(state.get("closed")):
            next_state = "EXIT"
        elif not bool(state.get("has_active_trade")) and not bool(state.get("trade_id")):
            next_state = "NO_TRADE"
        elif bool(state.get("tp2_hit")):
            next_state = "HOLD_RUNNER"
        elif bool(state.get("partial_exit_done")) and bool(state.get("be_moved")):
            next_state = "HOLD_RUNNER"
        elif bool(state.get("be_moved")):
            next_state = "BE_MOVED"
        elif bool(state.get("partial_exit_done")):
            next_state = "PARTIAL_DONE"
        elif bool(state.get("tp1_hit")):
            next_state = "TP1"
        elif bool(state.get("has_active_trade")):
            next_state = "ENTRY"
        else:
            next_state = "NO_TRADE"

    state["runner_active"] = next_state == "HOLD_RUNNER"
    if prev != next_state:
        state["lifecycle_state"] = next_state
        _append_lifecycle_event(state, next_state, note=note)
    else:
        state["lifecycle_state"] = next_state
        if state.get("last_lifecycle_event_at") is None and next_state != "NO_TRADE":
            _append_lifecycle_event(state, next_state, note=note)
    return state


def load_trade_journal() -> Dict[str, Any]:
    return safe_read_json(TRADE_JOURNAL_FILE, _default_journal())


def save_trade_journal(state: Dict[str, Any]) -> None:
    safe_state = _default_journal()
    if isinstance(state, dict):
        safe_state.update(_json_safe(state))
    atomic_write_json(TRADE_JOURNAL_FILE, safe_state)


def open_trade_journal(side: str, symbol: str = "BTCUSDT", timeframe: str = "1h", entry_price: Any = None, notes: Optional[str] = None, decision_snapshot: Optional[Dict[str, Any]] = None, analysis_snapshot: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    state = _default_journal()
    state.update({
        "has_active_trade": True,
        "trade_id": f"{symbol}_{side.upper()}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "symbol": symbol,
        "side": side.upper(),
        "timeframe": timeframe,
        "entry_price": _json_safe(entry_price),
        "opened_at": _now_str(),
        "status": "OPEN",
        "notes": notes,
        "decision_snapshot": _json_safe(decision_snapshot),
        "analysis_snapshot": _json_safe(analysis_snapshot),
        "exit_price": None,
        "result_pct": None,
        "result_rr": None,
        "holding_time_minutes": None,
        "close_context_snapshot": None,
        "exit_quality": None,
        "exit_reason_classifier": None,
        "post_trade_summary": None,
        "lifecycle_state": "ENTRY",
        "runner_active": False,
        "lifecycle_history": [],
        "last_lifecycle_event_at": None,
    })
    _sync_lifecycle_state(state, "ENTRY", note="trade opened")
    save_trade_journal(state)
    return state


def mark_tp1() -> Dict[str, Any]:
    state = load_trade_journal()
    if state.get("trade_id"):
        state["tp1_hit"] = True
        state["tp1_hit_at"] = _now_str()
        if state.get("status") in ("OPEN", "BE_MOVED"):
            state["status"] = "TP1_HIT"
        _sync_lifecycle_state(state, "TP1", note="tp1 marked")
        save_trade_journal(state)
    return state


def mark_tp2() -> Dict[str, Any]:
    state = load_trade_journal()
    if state.get("trade_id"):
        state["tp2_hit"] = True
        state["tp2_hit_at"] = _now_str()
        state["status"] = "TP2_HIT"
        _sync_lifecycle_state(state, "HOLD_RUNNER", note="tp2 marked / runner mode")
        save_trade_journal(state)
    return state


def mark_be_moved() -> Dict[str, Any]:
    state = load_trade_journal()
    if state.get("trade_id"):
        state["be_moved"] = True
        state["be_moved_at"] = _now_str()
        if state.get("status") == "OPEN":
            state["status"] = "BE_MOVED"
        target = "HOLD_RUNNER" if state.get("partial_exit_done") else "BE_MOVED"
        _sync_lifecycle_state(state, target, note="be moved")
        save_trade_journal(state)
    return state


def mark_partial_exit() -> Dict[str, Any]:
    state = load_trade_journal()
    if state.get("trade_id"):
        state["partial_exit_done"] = True
        state["partial_exit_at"] = _now_str()
        if state.get("status") in ("OPEN", "BE_MOVED", "TP1_HIT"):
            state["status"] = "PARTIAL_EXIT"
        target = "HOLD_RUNNER" if state.get("be_moved") else "PARTIAL_DONE"
        _sync_lifecycle_state(state, target, note="partial exit done")
        save_trade_journal(state)
    return state


def update_close_metrics(exit_price: Any = None, result_pct: Any = None, result_rr: Any = None, close_context_snapshot: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    state = load_trade_journal()
    if not state.get("trade_id"):
        return state
    state["exit_price"] = _json_safe(exit_price)
    computed_result_pct = _to_float(result_pct)
    if computed_result_pct is None:
        computed_result_pct = _compute_result_pct(side=state.get("side"), entry_price=state.get("entry_price"), exit_price=exit_price)
    state["result_pct"] = _json_safe(computed_result_pct)
    computed_result_rr = _to_float(result_rr)
    if computed_result_rr is None:
        computed_result_rr = _compute_result_rr(computed_result_pct)
    state["result_rr"] = _json_safe(computed_result_rr)
    if close_context_snapshot is not None:
        state["close_context_snapshot"] = _json_safe(close_context_snapshot)
    state["exit_quality"] = _classify_exit_quality(state)
    state["exit_reason_classifier"] = _classify_exit_reason(state)
    state["post_trade_summary"] = _build_post_trade_summary(state)
    _sync_lifecycle_state(state)
    save_trade_journal(state)
    return state


def _append_closed_trade_jsonl(state: Dict[str, Any]) -> None:
    from pathlib import Path
    out = Path(TRADE_JOURNAL_JSONL_FILE)
    out.parent.mkdir(parents=True, exist_ok=True)
    trade_id = str(state.get("trade_id") or "").strip()
    existing_ids = set()
    if out.exists():
        try:
            with out.open('r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except Exception:
                        continue
                    existing_ids.add(str(row.get('trade_id') or '').strip())
        except Exception:
            existing_ids = set()
    if trade_id and trade_id in existing_ids:
        return
    decision = state.get('decision_snapshot') if isinstance(state.get('decision_snapshot'), dict) else {}
    analysis = state.get('analysis_snapshot') if isinstance(state.get('analysis_snapshot'), dict) else {}
    row = _json_safe(dict(state))
    row['active_bot'] = decision.get('active_bot') or analysis.get('best_bot')
    row['setup_quality'] = analysis.get('setup_quality_label') or ((analysis.get('setup_quality') or {}).get('quality') if isinstance(analysis.get('setup_quality'), dict) else None)
    with out.open('a', encoding='utf-8') as f:
        f.write(json.dumps(row, ensure_ascii=False) + '\n')


def final_close_trade(reason: Optional[str] = None, exit_price: Any = None, result_pct: Any = None, result_rr: Any = None, close_context_snapshot: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    state = load_trade_journal()
    if state.get("trade_id") and not bool(state.get('closed')):
        closed_at = _now_str()
        state["closed"] = True
        state["closed_at"] = closed_at
        state["close_reason"] = reason or "manual_close"
        state["status"] = "CLOSED"
        state["has_active_trade"] = False
        state["exit_price"] = _json_safe(exit_price)
        computed_result_pct = _to_float(result_pct)
        if computed_result_pct is None:
            computed_result_pct = _compute_result_pct(side=state.get("side"), entry_price=state.get("entry_price"), exit_price=exit_price)
        state["result_pct"] = _json_safe(computed_result_pct)
        computed_result_rr = _to_float(result_rr)
        if computed_result_rr is None:
            computed_result_rr = _compute_result_rr(computed_result_pct)
        state["result_rr"] = _json_safe(computed_result_rr)
        state["holding_time_minutes"] = _compute_holding_time_minutes(opened_at=state.get("opened_at"), closed_at=closed_at)
        if close_context_snapshot is not None:
            state["close_context_snapshot"] = _json_safe(close_context_snapshot)
        state["exit_quality"] = _classify_exit_quality(state)
        state["exit_reason_classifier"] = _classify_exit_reason(state)
        state["post_trade_summary"] = _build_post_trade_summary(state)
        _sync_lifecycle_state(state, "EXIT", note=f"trade closed: {state.get('close_reason') or 'manual_close'}")
        save_trade_journal(state)
        _append_closed_trade_jsonl(state)
        update_learning_from_closed_trade(state)
    return state

def _classify_exit_quality(state: Dict[str, Any]) -> str:
    result_pct = _to_float(state.get("result_pct"))
    if result_pct is None:
        return "UNKNOWN"
    if result_pct >= 2.0 or bool(state.get("tp2_hit")):
        return "STRONG"
    if result_pct >= 0.5 or bool(state.get("partial_exit_done")) or bool(state.get("be_moved")):
        return "GOOD"
    if result_pct >= -0.2:
        return "OK"
    if result_pct >= -1.0:
        return "WEAK"
    return "BAD"


def _classify_exit_reason(state: Dict[str, Any]) -> str:
    reason = str(state.get("close_reason") or "").lower()
    close_ctx = state.get("close_context_snapshot") or {}
    decision = close_ctx.get("decision") or {}
    decision_action = str(decision.get("action") or decision.get("action_text") or "").upper()
    decision_direction = str(decision.get("direction") or "").upper()
    side = str(state.get("side") or "").upper()

    if state.get("tp2_hit"):
        return "TARGET_COMPLETED"
    if decision_action in ("CLOSE", "EXIT"):
        return "DECISION_EXIT"
    if decision_direction and side and decision_direction not in (side, "NONE"):
        return "STRUCTURE_BREAK"
    if bool(state.get("partial_exit_done")) or bool(state.get("be_moved")):
        return "PROTECTED_MANAGEMENT_EXIT"
    result_pct = _to_float(state.get("result_pct"))
    if result_pct is not None and result_pct < 0:
        return "STOP_OR_INVALIDATION"
    if "manual" in reason or "button" in reason:
        return "MANUAL_EXIT"
    return "UNKNOWN"


def _build_post_trade_summary(state: Dict[str, Any]) -> str:
    side = str(state.get("side") or "?").upper()
    quality = state.get("exit_quality") or "UNKNOWN"
    classifier = state.get("exit_reason_classifier") or "UNKNOWN"
    entry_price = state.get("entry_price")
    exit_price = state.get("exit_price")
    result_pct = state.get("result_pct")
    rr = state.get("result_rr")
    hold = state.get("holding_time_minutes")

    parts = [f"Сделка {side} закрыта."]
    if entry_price is not None:
        parts.append(f"Вход: {entry_price}.")
    if exit_price is not None:
        parts.append(f"Выход: {exit_price}.")
    if result_pct is not None:
        parts.append(f"Результат: {result_pct}%.")
    if rr is not None:
        parts.append(f"RR: {rr}.")
    if hold is not None:
        parts.append(f"Удержание: {hold} мин.")
    parts.append(f"Качество выхода: {quality}.")
    parts.append(f"Тип выхода: {classifier}.")
    if state.get("tp2_hit"):
        parts.append("TP2 был отмечен.")
    elif state.get("tp1_hit"):
        parts.append("TP1 был отмечен.")
    if state.get("be_moved"):
        parts.append("BE был перенесён.")
    if state.get("partial_exit_done"):
        parts.append("Частичная фиксация была сделана.")
    return " ".join(parts)



def append_closed_trade(path: str, *, symbol: str, timeframe: str, side: str, bot_id: str, setup_type: str, regime_label: str, deviation_tier: str, play_id: str, best_play_snapshot: Optional[Dict[str, Any]] = None, liquidity_state: str = 'NEUTRAL', price_oi_regime: str = 'NEUTRAL', result_rr: float = 0.0, mfe: float = 0.0, mae: float = 0.0, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    from pathlib import Path
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    row = {
        'closed_at': _now_str(),
        'symbol': symbol,
        'timeframe': timeframe,
        'side': side,
        'bot_id': bot_id,
        'setup_type': setup_type,
        'regime_label': regime_label,
        'deviation_tier': deviation_tier,
        'play_id': play_id,
        'best_play_snapshot': _json_safe(best_play_snapshot or {}),
        'liquidity_state': liquidity_state,
        'price_oi_regime': price_oi_regime,
        'result_rr': _to_float(result_rr),
        'mfe': _to_float(mfe),
        'mae': _to_float(mae),
    }
    if extra:
        row.update(_json_safe(extra))
    with out.open('a', encoding='utf-8') as f:
        f.write(json.dumps(row, ensure_ascii=False) + '\n')
    return row
