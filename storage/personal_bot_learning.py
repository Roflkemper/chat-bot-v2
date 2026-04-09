from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any, Dict, List

from utils.safe_io import atomic_write_json, safe_read_json

PERSONAL_BOT_LEARNING_FILE = "state/personal_bot_learning.json"
POSITIVE_ACTIONS = {"ACTIVE", "SMALL", "AGGRESSIVE", "ADD", "PARTIAL"}
NEGATIVE_ACTIONS = {"CANCEL", "EXIT"}


CLOSED_TRADE_POSITIVE_REASONS = {"TARGET_COMPLETED", "PROTECTED_MANAGEMENT_EXIT"}
CLOSED_TRADE_NEGATIVE_REASONS = {"STOP_OR_INVALIDATION", "STRUCTURE_BREAK"}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _bucket_avg(current_avg: Any, count: int, new_value: float) -> float:
    count = max(0, int(count))
    if count <= 0:
        return round(float(new_value), 4)
    current = _safe_float(current_avg, 0.0)
    return round(((current * count) + float(new_value)) / float(count + 1), 4)


def _ensure_closed_trade_fields(bot: Dict[str, Any]) -> Dict[str, Any]:
    bot.setdefault("closed_trades", 0)
    bot.setdefault("wins", 0)
    bot.setdefault("losses", 0)
    bot.setdefault("breakeven", 0)
    bot.setdefault("avg_result_pct", 0.0)
    bot.setdefault("avg_rr", 0.0)
    bot.setdefault("setup_qualities", {})
    bot.setdefault("exit_reasons", {})
    bot.setdefault("timeframes", {})
    bot.setdefault("scenarios", {})
    bot.setdefault("learned_trade_ids", [])
    bot.setdefault("last_trade_id", None)
    return bot


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _default_bot_learning() -> Dict[str, Any]:
    return {
        "samples": 0,
        "auto_observations": 0,
        "manual_positive": 0,
        "manual_negative": 0,
        "activations": 0,
        "regimes": {},
        "positions": {},
        "trade_styles": {},
        "breakout_risks": {},
        "updated_at": None,
        "closed_trades": 0,
        "wins": 0,
        "losses": 0,
        "breakeven": 0,
        "avg_result_pct": 0.0,
        "avg_rr": 0.0,
        "setup_qualities": {},
        "exit_reasons": {},
        "timeframes": {},
        "scenarios": {},
        "learned_trade_ids": [],
        "last_trade_id": None,
    }


def _default_state() -> Dict[str, Any]:
    return {
        "version": 1,
        "updated_at": None,
        "bots": {
            "ct_long": _default_bot_learning(),
            "ct_short": _default_bot_learning(),
            "range_long": _default_bot_learning(),
            "range_short": _default_bot_learning(),
        },
    }


def _merge(bot: Dict[str, Any] | None) -> Dict[str, Any]:
    base = _default_bot_learning()
    if isinstance(bot, dict):
        for k, v in bot.items():
            if isinstance(base.get(k), dict) and isinstance(v, dict):
                merged = dict(base[k])
                merged.update(v)
                base[k] = merged
            else:
                base[k] = v
    return base


def load_personal_bot_learning() -> Dict[str, Any]:
    state = safe_read_json(PERSONAL_BOT_LEARNING_FILE, _default_state())
    bots = state.get('bots') if isinstance(state.get('bots'), dict) else {}
    merged = {}
    for key in _default_state()['bots'].keys():
        merged[key] = _merge(bots.get(key))
    state['bots'] = merged
    return state


def save_personal_bot_learning(state: Dict[str, Any]) -> None:
    payload = _default_state()
    if isinstance(state, dict):
        payload.update({k: v for k, v in state.items() if k != 'bots'})
        incoming = state.get('bots') if isinstance(state.get('bots'), dict) else {}
        payload['bots'] = {k: _merge(incoming.get(k)) for k in payload['bots'].keys()}
    payload['updated_at'] = _now()
    atomic_write_json(PERSONAL_BOT_LEARNING_FILE, payload)


def _inc_bucket(d: Dict[str, int], key: str) -> None:
    key = str(key or 'unknown').strip() or 'unknown'
    d[key] = int(d.get(key, 0)) + 1


def _top_bucket(d: Dict[str, int]) -> str:
    if not isinstance(d, dict) or not d:
        return 'нет данных'
    return max(d.items(), key=lambda kv: kv[1])[0]


def _success_ratio(bot: Dict[str, Any]) -> float:
    pos = float(bot.get('manual_positive') or 0)
    neg = float(bot.get('manual_negative') or 0)
    total = pos + neg
    if total <= 0:
        return 0.5
    return pos / total


def update_personal_bot_learning(bot_cards: List[Dict[str, Any]], context: Dict[str, Any]) -> Dict[str, Any]:
    state = load_personal_bot_learning()
    bots = state.get('bots') or {}
    regime = str(context.get('market_regime') or context.get('regime') or 'unknown')
    position = str(context.get('range_position') or context.get('position') or 'unknown')
    trade_style = str(context.get('trade_style') or 'unknown')
    breakout_risk = str(context.get('breakout_risk') or 'unknown')

    for card in bot_cards:
        key = str(card.get('bot_key') or '').strip()
        if not key or key not in bots:
            continue
        bot = _merge(bots.get(key))
        bot['samples'] = int(bot.get('samples') or 0) + 1
        bot['auto_observations'] = int(bot.get('auto_observations') or 0) + 1
        _inc_bucket(bot['regimes'], regime)
        _inc_bucket(bot['positions'], position)
        _inc_bucket(bot['trade_styles'], trade_style)
        _inc_bucket(bot['breakout_risks'], breakout_risk)

        manager = card.get('manager_state') or {}
        manual = manager.get('manual') or {}
        manual_action = str(manual.get('action') or '').strip().upper()
        if manual_action in POSITIVE_ACTIONS:
            bot['manual_positive'] = int(bot.get('manual_positive') or 0) + 1
        elif manual_action in NEGATIVE_ACTIONS:
            bot['manual_negative'] = int(bot.get('manual_negative') or 0) + 1

        if bool(card.get('position_open')) or str(manager.get('phase') or '').upper() in {'ACTIVE', 'ADD_READY'}:
            bot['activations'] = int(bot.get('activations') or 0) + 1

        bot['updated_at'] = _now()
        bots[key] = bot

    state['bots'] = bots
    save_personal_bot_learning(state)
    return state


def _extract_closed_trade_context(journal: Dict[str, Any]) -> Dict[str, Any]:
    decision = journal.get("decision_snapshot") if isinstance(journal.get("decision_snapshot"), dict) else {}
    analysis = journal.get("analysis_snapshot") if isinstance(journal.get("analysis_snapshot"), dict) else {}
    close_ctx = journal.get("close_context_snapshot") if isinstance(journal.get("close_context_snapshot"), dict) else {}
    close_analysis = close_ctx.get("analysis") if isinstance(close_ctx.get("analysis"), dict) else {}
    close_decision = close_ctx.get("decision") if isinstance(close_ctx.get("decision"), dict) else {}

    bot_key = str(
        decision.get("active_bot")
        or close_decision.get("active_bot")
        or analysis.get("best_bot")
        or close_analysis.get("best_bot")
        or ""
    ).strip().lower()
    if bot_key not in {"ct_long", "ct_short", "range_long", "range_short"}:
        bot_key = ""

    scenario = str(
        analysis.get("trade_style")
        or close_analysis.get("trade_style")
        or analysis.get("market_regime")
        or close_analysis.get("market_regime")
        or decision.get("mode")
        or close_decision.get("mode")
        or "unknown"
    )
    setup_quality = str(
        analysis.get("setup_quality_label")
        or (analysis.get("setup_quality") or {}).get("quality") if isinstance(analysis.get("setup_quality"), dict) else None
        or decision.get("location_quality")
        or close_decision.get("location_quality")
        or "unknown"
    )
    timeframe = str(journal.get("timeframe") or analysis.get("timeframe") or close_analysis.get("timeframe") or "unknown")
    exit_reason = str(journal.get("exit_reason_classifier") or "UNKNOWN")
    return {
        "bot_key": bot_key,
        "scenario": scenario,
        "setup_quality": setup_quality,
        "timeframe": timeframe,
        "exit_reason": exit_reason,
    }


def update_learning_from_closed_trade(journal: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(journal, dict) or not journal.get("closed"):
        return {"updated": False, "reason": "journal_not_closed"}

    context = _extract_closed_trade_context(journal)
    bot_key = context.get("bot_key") or ""
    if not bot_key:
        return {"updated": False, "reason": "bot_key_missing"}

    state = load_personal_bot_learning()
    bots = state.get("bots") or {}
    bot = _ensure_closed_trade_fields(_merge(bots.get(bot_key)))
    trade_id = str(journal.get("trade_id") or "").strip()
    learned_ids = [str(x) for x in (bot.get("learned_trade_ids") or []) if str(x).strip()]
    if trade_id and trade_id in learned_ids:
        return {"updated": False, "reason": "already_learned", "bot_key": bot_key, "trade_id": trade_id}

    result_pct = _safe_float(journal.get("result_pct"), 0.0)
    result_rr = _safe_float(journal.get("result_rr"), 0.0)
    exit_reason = str(context.get("exit_reason") or "UNKNOWN")

    bot["closed_trades"] = int(bot.get("closed_trades") or 0) + 1
    prev_closed = int(bot["closed_trades"]) - 1
    bot["avg_result_pct"] = _bucket_avg(bot.get("avg_result_pct"), prev_closed, result_pct)
    bot["avg_rr"] = _bucket_avg(bot.get("avg_rr"), prev_closed, result_rr)

    if result_pct > 0.15 or exit_reason in CLOSED_TRADE_POSITIVE_REASONS:
        bot["wins"] = int(bot.get("wins") or 0) + 1
    elif result_pct < -0.15 or exit_reason in CLOSED_TRADE_NEGATIVE_REASONS:
        bot["losses"] = int(bot.get("losses") or 0) + 1
    else:
        bot["breakeven"] = int(bot.get("breakeven") or 0) + 1

    _inc_bucket(bot["setup_qualities"], str(context.get("setup_quality") or "unknown"))
    _inc_bucket(bot["exit_reasons"], exit_reason)
    _inc_bucket(bot["timeframes"], str(context.get("timeframe") or "unknown"))
    _inc_bucket(bot["scenarios"], str(context.get("scenario") or "unknown"))

    if trade_id:
        learned_ids.append(trade_id)
        bot["learned_trade_ids"] = learned_ids[-50:]
        bot["last_trade_id"] = trade_id

    bot["updated_at"] = _now()
    bots[bot_key] = bot
    state["bots"] = bots
    save_personal_bot_learning(state)

    total = int(bot.get("closed_trades") or 0)
    wins = int(bot.get("wins") or 0)
    losses = int(bot.get("losses") or 0)
    breakeven = int(bot.get("breakeven") or 0)
    winrate = (wins / total) if total > 0 else 0.0
    return {
        "updated": True,
        "bot_key": bot_key,
        "trade_id": trade_id,
        "closed_trades": total,
        "wins": wins,
        "losses": losses,
        "breakeven": breakeven,
        "winrate": round(winrate, 3),
        "avg_result_pct": round(_safe_float(bot.get("avg_result_pct"), 0.0), 4),
        "avg_rr": round(_safe_float(bot.get("avg_rr"), 0.0), 4),
        "scenario": str(context.get("scenario") or "unknown"),
        "setup_quality": str(context.get("setup_quality") or "unknown"),
        "timeframe": str(context.get("timeframe") or "unknown"),
        "exit_reason": exit_reason,
    }


def build_closed_trade_learning_text(update: Dict[str, Any]) -> str:
    if not isinstance(update, dict) or not update.get("updated"):
        return ""
    bot_label_map = {
        "ct_long": "CT LONG бот",
        "ct_short": "CT SHORT бот",
        "range_long": "RANGE LONG бот",
        "range_short": "RANGE SHORT бот",
    }
    bot_key = str(update.get("bot_key") or "")
    label = bot_label_map.get(bot_key, bot_key or "бот")
    return "\n".join([
        "🧠 LEARNING UPDATE — CLOSED TRADE",
        "",
        f"Бот: {label}",
        f"Таймфрейм: {update.get('timeframe') or 'unknown'}",
        f"Сценарий: {update.get('scenario') or 'unknown'}",
        f"Setup quality: {update.get('setup_quality') or 'unknown'}",
        f"Exit reason: {update.get('exit_reason') or 'UNKNOWN'}",
        "",
        f"Closed trades: {int(update.get('closed_trades') or 0)}",
        f"Wins / Losses / BE: {int(update.get('wins') or 0)} / {int(update.get('losses') or 0)} / {int(update.get('breakeven') or 0)}",
        f"Winrate: {float(update.get('winrate') or 0.0) * 100:.1f}%",
        f"Avg result: {float(update.get('avg_result_pct') or 0.0):.2f}%",
        f"Avg RR: {float(update.get('avg_rr') or 0.0):.2f}",
        "",
        "Что изменилось:",
        "• закрытая сделка записана в personal bot learning",
        "• статистика теперь учитывает bot type / scenario / quality / exit reason",
        "• следующий bot weighting будет опираться уже на обновлённую историю",
    ])


def summarize_personal_bot_learning(learning_state: Dict[str, Any], bot_cards: List[Dict[str, Any]]) -> Dict[str, Any]:
    bots = learning_state.get('bots') if isinstance(learning_state.get('bots'), dict) else {}
    summary_cards: List[Dict[str, Any]] = []
    overview: List[str] = []
    best_historic = None
    best_ratio = -1.0

    for card in bot_cards:
        key = str(card.get('bot_key') or '')
        label = str(card.get('bot_label') or key)
        bot = _merge(bots.get(key))
        samples = int(bot.get('samples') or 0)
        ratio = _success_ratio(bot)
        top_regime = _top_bucket(bot.get('regimes') or {})
        top_position = _top_bucket(bot.get('positions') or {})
        activations = int(bot.get('activations') or 0)
        pos = int(bot.get('manual_positive') or 0)
        neg = int(bot.get('manual_negative') or 0)
        closed_trades = int(bot.get('closed_trades') or 0)
        wins = int(bot.get('wins') or 0)
        losses = int(bot.get('losses') or 0)
        be = int(bot.get('breakeven') or 0)
        avg_result_pct = _safe_float(bot.get('avg_result_pct'), 0.0)
        avg_rr = _safe_float(bot.get('avg_rr'), 0.0)
        confidence = 0.0
        if samples >= 3:
            confidence = min(0.9, 0.35 + min(samples, 25) / 40.0)
        learned_mode = 'NEUTRAL'
        if samples >= 3 and ratio >= 0.60:
            learned_mode = 'FAVORED'
        elif samples >= 3 and ratio <= 0.40:
            learned_mode = 'CAUTIOUS'
        learned_summary = f"чаще встречался в режиме {top_regime}, позиция {top_position}"
        if samples < 3:
            learned_summary = 'пока мало личной статистики по этому боту'
        summary_cards.append({
            'bot_key': key,
            'bot_label': label,
            'samples': samples,
            'success_ratio': round(ratio, 3),
            'learned_confidence': round(confidence, 3),
            'learned_mode': learned_mode,
            'top_regime': top_regime,
            'top_position': top_position,
            'activations': activations,
            'manual_positive': pos,
            'manual_negative': neg,
            'closed_trades': closed_trades,
            'wins': wins,
            'losses': losses,
            'breakeven': be,
            'avg_result_pct': round(avg_result_pct, 3),
            'avg_rr': round(avg_rr, 3),
            'learned_summary': learned_summary,
        })
        if samples >= 3:
            overview.append(f"{label}: {learned_mode.lower()} | samples {samples} | positive {pos} / negative {neg} | closed {closed_trades} | win {wins} / loss {losses} / be {be}")
        if ratio > best_ratio and samples >= 3:
            best_ratio = ratio
            best_historic = label

    if not overview:
        overview.append('личная статистика только начинает накапливаться')

    return {
        'learning_cards': summary_cards,
        'learning_overview': overview[:4],
        'best_historic_bot': best_historic,
        'learning_ready': any(int((c.get('samples') or 0)) >= 3 for c in summary_cards),
    }


def build_learning_adjustments(learning_summary: Dict[str, Any], regime: str, position: str) -> Dict[str, Dict[str, Any]]:
    adjustments: Dict[str, Dict[str, Any]] = {}
    regime = str(regime or 'unknown')
    position = str(position or 'unknown')
    for card in (learning_summary.get('learning_cards') or []):
        key = str(card.get('bot_key') or '').strip()
        if not key:
            continue
        mode = str(card.get('learned_mode') or 'NEUTRAL').upper()
        learned_conf = float(card.get('learned_confidence') or 0.0)
        ratio = float(card.get('success_ratio') or 0.5)
        top_regime = str(card.get('top_regime') or 'нет данных')
        top_position = str(card.get('top_position') or 'нет данных')
        samples = int(card.get('samples') or 0)
        manual_positive = int(card.get('manual_positive') or 0)
        manual_negative = int(card.get('manual_negative') or 0)

        delta = 0.0
        reasons: List[str] = []
        if samples >= 3:
            if mode == 'FAVORED':
                add = 0.02 + 0.04 * min(1.0, learned_conf)
                delta += add
                reasons.append('личная статистика поддерживает этот бот')
            elif mode == 'CAUTIOUS':
                sub = 0.02 + 0.04 * min(1.0, learned_conf)
                delta -= sub
                reasons.append('личная статистика просит осторожность по этому боту')
            if top_regime == regime and top_regime != 'нет данных':
                delta += 0.02
                reasons.append('текущий режим совпадает с его лучшим контекстом')
            if top_position == position and top_position != 'нет данных':
                delta += 0.02
                reasons.append('позиция в диапазоне совпадает с его лучшей зоной')
        if manual_negative >= manual_positive + 2 and samples >= 3:
            delta -= 0.02
            reasons.append('по ручным действиям у него больше отмен, чем сильных подтверждений')
        elif manual_positive >= manual_negative + 2 and samples >= 3:
            delta += 0.015
            reasons.append('по ручным действиям бот у тебя подтверждался чаще')

        if manual_positive == 0 and manual_negative == 0:
            delta = max(-0.01, min(0.01, delta))
            if reasons:
                reasons = reasons[:2]
            reasons.append('личная статистика ещё без подтверждённых ручных исходов, поэтому буст ограничен')

        delta = max(-0.08, min(0.08, delta))
        adjustments[key] = {
            'delta': round(delta, 4),
            'reasons': reasons[:3],
            'context_match': bool(samples >= 3 and ((top_regime == regime and top_regime != 'нет данных') or (top_position == position and top_position != 'нет данных'))),
            'samples': samples,
            'mode': mode,
            'success_ratio': round(ratio, 3),
            'manual_positive': manual_positive,
            'manual_negative': manual_negative,
        }
    return adjustments




def build_learning_execution_adjustments(learning_summary: Dict[str, Any], bot_cards: List[Dict[str, Any]], regime: str, position: str) -> Dict[str, Dict[str, Any]]:
    """Small, capped execution-hint adjustment from personal learning.

    This layer nudges execution hints for bot cards but never overrides a strong
    market-risk restriction. It is intentionally weaker than the raw market
    logic and only becomes active after a few real observations.
    """
    score_adjustments = build_learning_adjustments(learning_summary, regime, position)
    result: Dict[str, Dict[str, Any]] = {}

    def _plan_up(plan: str) -> str:
        order = ['WAIT', 'SMALL ENTRY', 'CAN ADD', 'AGGRESSIVE ENTRY']
        plan = str(plan or 'WAIT').upper()
        if plan not in order:
            return plan
        return order[min(len(order) - 1, order.index(plan) + 1)]

    def _plan_down(plan: str) -> str:
        order = ['WAIT', 'SMALL ENTRY', 'CAN ADD', 'AGGRESSIVE ENTRY']
        plan = str(plan or 'WAIT').upper()
        if plan not in order:
            return plan
        return order[max(0, order.index(plan) - 1)]

    def _manage_up(action: str) -> str:
        action = str(action or 'WAIT').upper()
        if action in {'WAIT', 'WAIT EDGE'}:
            return 'ENABLE SMALL SIZE'
        if action in {'ENABLE SMALL SIZE', 'SMALL ENTRY'}:
            return 'ENABLE / CAN ADD'
        return action

    def _manage_down(action: str, status: str) -> str:
        action = str(action or 'WAIT').upper()
        status = str(status or 'OFF').upper()
        if status == 'OFF':
            return 'CANCEL SCENARIO'
        if action in {'AGGRESSIVE ENTRY', 'ENABLE / CAN ADD'}:
            return 'ENABLE SMALL SIZE'
        if action in {'ENABLE SMALL SIZE', 'SMALL ENTRY'}:
            return 'WAIT'
        if action == 'WAIT' and status == 'WATCH':
            return 'CAUTIOUS EXIT'
        return action

    for card in bot_cards:
        key = str(card.get('bot_key') or '').strip()
        if not key:
            continue
        learn = score_adjustments.get(key, {})
        delta = float(learn.get('delta') or 0.0)
        samples = int(learn.get('samples') or 0)
        mode = str(learn.get('mode') or 'NEUTRAL').upper()
        status = str(card.get('status') or 'OFF').upper()
        plan_state = str(card.get('plan_state') or 'WAIT').upper()
        management_action = str(card.get('management_action') or 'WAIT').upper()
        entry_instruction = str(card.get('entry_instruction') or '')
        exit_instruction = str(card.get('exit_instruction') or '')
        reasons = list(learn.get('reasons') or [])

        exec_delta = 0.0
        if samples >= 3:
            exec_delta = max(-0.06, min(0.06, delta * 0.85))
            if int(learn.get("manual_positive") or 0) == 0 and int(learn.get("manual_negative") or 0) == 0:
                exec_delta = max(-0.008, min(0.008, exec_delta))

        execution_mode = 'NEUTRAL'
        adjusted_plan = plan_state
        adjusted_management = management_action
        summary = 'обучение пока не меняет execution-подсказку'

        if exec_delta >= 0.03 and status in {'WATCH', 'READY'}:
            execution_mode = 'BOOST'
            adjusted_plan = _plan_up(plan_state)
            adjusted_management = _manage_up(management_action)
            summary = 'личное обучение допускает чуть смелее вход и добор'
            if 'маленькой позицией' in entry_instruction:
                entry_instruction = entry_instruction.replace('маленькой позицией', 'маленькой позицией, с возможностью добора')
            elif entry_instruction:
                entry_instruction = entry_instruction + '; при подтверждении можно аккуратно добавить'
            if exit_instruction:
                exit_instruction = exit_instruction + '; без отмены идеи можно сопровождать чуть свободнее'
        elif exec_delta <= -0.03:
            execution_mode = 'COOL'
            adjusted_plan = _plan_down(plan_state)
            adjusted_management = _manage_down(management_action, status)
            summary = 'личное обучение просит консервативнее входить и быстрее охлаждать сценарий'
            if entry_instruction:
                entry_instruction = entry_instruction + '; размер лучше уменьшить и ждать более чистого подтверждения'
            if exit_instruction:
                exit_instruction = exit_instruction + '; при ухудшении контекста лучше сократить быстрее'
        elif abs(exec_delta) >= 0.01:
            execution_mode = 'LIGHT'
            summary = 'личное обучение слегка корректирует execution-подсказку, но без сильного сдвига'

        result[key] = {
            'execution_delta': round(exec_delta, 4),
            'execution_mode': execution_mode,
            'adjusted_plan_state': adjusted_plan,
            'adjusted_management_action': adjusted_management,
            'adjusted_entry_instruction': entry_instruction,
            'adjusted_exit_instruction': exit_instruction,
            'summary': summary,
            'reasons': reasons[:3],
            'samples': samples,
        }
    return result
def build_learning_forecast_adjustment(learning_summary: Dict[str, Any], analysis: Dict[str, Any]) -> Dict[str, Any]:
    """Small, capped forecast adjustment from personal bot learning.

    This layer should never dominate market logic. It only nudges the top-layer
    forecast when the current best bot and current context strongly match the
    user's accumulated history.
    """
    cards = list(learning_summary.get('learning_cards') or [])
    best_bot_key = str(analysis.get('best_bot') or '').strip()
    best_bot_label = str(analysis.get('best_bot_label') or best_bot_key)
    market_regime = str(analysis.get('market_regime') or analysis.get('trade_style') or 'unknown')
    range_position = str(analysis.get('range_position') or analysis.get('position') or 'unknown')
    direction = str(analysis.get('forecast_direction') or 'НЕЙТРАЛЬНО').upper()
    base_conf = float(analysis.get('forecast_confidence') or 0.0)

    if not cards or not best_bot_key:
        return {
            'delta': 0.0,
            'direction_hint': 'НЕЙТРАЛЬНО',
            'confidence_boost': 0.0,
            'summary': 'личного обучающего влияния на верхний прогноз пока нет',
            'reasons': [],
            'bot_label': best_bot_label or 'нет данных',
        }

    selected = None
    for c in cards:
        if str(c.get('bot_key') or '').strip() == best_bot_key:
            selected = c
            break
    if selected is None:
        selected = cards[0]

    bot_label = str(selected.get('bot_label') or best_bot_label or best_bot_key)
    samples = int(selected.get('samples') or 0)
    ratio = float(selected.get('success_ratio') or 0.5)
    learned_conf = float(selected.get('learned_confidence') or 0.0)
    top_regime = str(selected.get('top_regime') or 'нет данных')
    top_position = str(selected.get('top_position') or 'нет данных')
    mode = str(selected.get('learned_mode') or 'NEUTRAL').upper()

    delta = 0.0
    reasons = []

    if samples >= 3:
        if mode == 'FAVORED':
            delta += 0.015 + 0.03 * min(1.0, learned_conf)
            reasons.append(f'личная статистика поддерживает {bot_label}')
        elif mode == 'CAUTIOUS':
            delta -= 0.015 + 0.03 * min(1.0, learned_conf)
            reasons.append(f'личная статистика просит осторожность по {bot_label}')

        if top_regime == market_regime and top_regime != 'нет данных':
            delta += 0.015
            reasons.append('текущий режим совпадает с сильным историческим режимом')
        if top_position == range_position and top_position != 'нет данных':
            delta += 0.015
            reasons.append('позиция в диапазоне совпадает с сильным историческим контекстом')

    delta = max(-0.06, min(0.06, delta))

    direction_hint = 'НЕЙТРАЛЬНО'
    upper_label = best_bot_label.upper()
    if 'SHORT' in upper_label or 'ШОРТ' in upper_label:
        direction_hint = 'ВНИЗ'
    elif 'LONG' in upper_label or 'ЛОНГ' in upper_label:
        direction_hint = 'ВВЕРХ'

    # If learning disagrees with the current raw direction, reduce the effect.
    if direction not in {'НЕЙТРАЛЬНО', 'NEUTRAL', ''} and direction_hint not in {'НЕЙТРАЛЬНО', direction}:
        delta *= 0.35
        reasons.append('обучение не совпадает с текущим сырым прогнозом, влияние ограничено')

    confidence_boost = delta
    new_conf = max(0.0, min(0.95, base_conf + confidence_boost))

    if abs(delta) < 0.005:
        summary = 'личное обучение пока почти не меняет верхний прогноз'
    elif delta > 0:
        summary = f'личное обучение слегка усиливает верхний прогноз через {bot_label}'
    else:
        summary = f'личное обучение слегка охлаждает верхний прогноз через {bot_label}'

    return {
        'delta': round(delta, 4),
        'direction_hint': direction_hint,
        'confidence_boost': round(confidence_boost, 4),
        'suggested_confidence': round(new_conf, 4),
        'summary': summary,
        'reasons': reasons[:3],
        'bot_label': bot_label,
        'samples': samples,
        'success_ratio': round(ratio, 3),
        'mode': mode,
    }
