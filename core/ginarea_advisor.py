
from __future__ import annotations

from typing import Any, Dict, List
import csv
import io

import requests

from storage.bot_manager_state import sync_bot_manager
from storage.personal_bot_learning import update_personal_bot_learning, summarize_personal_bot_learning, build_learning_adjustments, build_learning_execution_adjustments

try:
    import config as _config
except Exception:
    _config = None

from core.data_loader import load_klines
from core.indicators import add_indicators
from core.range_detector import analyze_range
from core.reversal_engine import analyze_reversal
from core.pattern_memory import analyze_history_pattern
from core.bot_control_center import build_bot_control_center

_DEFAULT_BOT_LABELS = {
    "ct_long": "CT LONG бот",
    "ct_short": "CT SHORT бот",
    "range_long": "RANGE LONG бот",
    "range_short": "RANGE SHORT бот",
}


def _load_bot_labels() -> Dict[str, str]:
    labels = dict(_DEFAULT_BOT_LABELS)
    custom = getattr(_config, "BOT_LABELS", None) if _config is not None else None
    if isinstance(custom, dict):
        for key, value in custom.items():
            if key in labels and str(value).strip():
                labels[key] = str(value).strip()
    return labels


BOT_LABELS = _load_bot_labels()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _dedupe(items: List[str]) -> List[str]:
    result: List[str] = []
    for item in items:
        item = str(item or "").strip()
        if item and item not in result:
            result.append(item)
    return result


def _bot_status(score: float) -> str:
    if score >= 0.60:
        return "READY"
    if score >= 0.12:
        return "WATCH"
    return "OFF"


def _bot_hold_mode(card: Dict[str, Any]) -> str:
    mode = str(card.get("hold_mode") or "wait").lower()
    if mode in {"intraday", "hold"}:
        return "INTRADAY"
    if mode in {"scalp", "fast"}:
        return "SCALP ONLY"
    return "WAIT"


def _edge_below_trade_threshold(edge_score: float) -> bool:
    try:
        edge_score = float(edge_score)
    except Exception:
        edge_score = 0.0
    if edge_score <= 1.0:
        return edge_score <= 0.12
    return edge_score < 12.0


def _truth_lock_active(edge_score: float, volume_status: str = '', confirmation_ready: float | None = None) -> bool:
    volume_status = str(volume_status or '').upper()
    if confirmation_ready is None:
        confirmation_blocked = False
    else:
        try:
            confirmation_blocked = float(confirmation_ready) <= 0.0
        except Exception:
            confirmation_blocked = False
    return _edge_below_trade_threshold(edge_score) or volume_status in {'BLOCKED'} or confirmation_blocked


def _make_bot_card(key: str, score: float, zone: str, invalidation: str, note: str, hold_mode: str, setup_type: str, execution_hint: str) -> Dict[str, Any]:
    return {
        "bot_key": key,
        "bot_label": BOT_LABELS.get(key, key),
        "score": round(max(0.0, min(1.0, score)), 3),
        "status": _bot_status(score),
        "zone": zone,
        "invalidation": invalidation,
        "note": note,
        "hold_mode": hold_mode,
        "setup_type": setup_type,
        "execution_hint": execution_hint,
    }




def _plan_state_by_score(score: float) -> str:
    if score >= 0.82:
        return "AGGRESSIVE ENTRY"
    if score >= 0.68:
        return "SMALL ENTRY"
    if score >= 0.45:
        return "PREPARE"
    return "WAIT"


def _management_action(card: Dict[str, Any], breakout_risk: str, position: str, trap_comment: str) -> str:
    score = float(card.get("score") or 0.0)
    key = str(card.get("bot_key") or "")
    status = str(card.get("status") or "OFF").upper()
    if status == "OFF":
        return "CANCEL SCENARIO"
    if breakout_risk == "HIGH" and key.startswith("range"):
        return "WAIT_CONFIRM" if score >= 0.45 else "CANCEL SCENARIO"
    if position == "MID" and key.startswith("range"):
        return "WAIT_EDGE" if score >= 0.45 else "WAIT EDGE"
    if trap_comment and key.startswith("range"):
        return "CAUTIOUS EXIT"
    if score >= 0.82:
        return "AGGRESSIVE ENTRY"
    if score >= 0.68:
        return "ENABLE SMALL SIZE"
    if score >= 0.45:
        return "WAIT_CONFIRM"
    return "WAIT"


def _entry_instruction(key: str, score: float, breakout_risk: str, position: str) -> str:
    if key.startswith("ct_"):
        if score >= 0.82:
            return "агрессивный вход допустим только после подтверждённого ложного выноса / reclaim"
        if score >= 0.68:
            return "вход небольшой позицией допустим, при удержании уровня можно добавить"
        if score >= 0.45:
            return "контртренд только маленькой позицией и только после подтверждения"
        return "контртренд пока не включать"
    if breakout_risk == "HIGH":
        return "range-бот только уменьшенным размером, без adds и без большого удержания"
    if position == "MID":
        return "range-бот в середине диапазона допустим только малым размером и без форсирования"
    if score >= 0.82:
        return "range-бот можно включать активнее, допускается добавление по retest"
    if score >= 0.68:
        return "range-бот включать аккуратно, после удержания края можно добавить"
    if score >= 0.45:
        return "range-бот пока только режим наблюдения до confirm / reclaim"
    return "range-бот сейчас лучше не включать"


def _exit_instruction(key: str, score: float, breakout_risk: str, trap_comment: str) -> str:
    if score < 0.45:
        return "отмена сценария / выход при отсутствии подтверждения"
    if key.startswith("range") and breakout_risk == "HIGH":
        return "осторожно выходить при первом признаке пробоя границы"
    if trap_comment and key.startswith("range"):
        return "осторожно сопровождать, так как ловушечный контекст усилился"
    if key.startswith("ct_") and score < 0.68:
        return "фиксировать быстро, не пересиживать контртренд"
    if score >= 0.82:
        return "можно вести активнее, но отмена сразу при потере рабочей зоны"
    return "сопровождать консервативно, частично фиксировать у первой реакции"



def _requires_confirmation_gate(card: Dict[str, Any]) -> bool:
    text = " ".join([
        str(card.get("note") or ""),
        str(card.get("entry_instruction") or ""),
        str(card.get("execution_hint") or ""),
    ]).lower()
    patterns = (
        "только после подтверждения",
        "до confirm / reclaim",
        "ждать подтверждение",
        "нужен ещё триггер",
        "нужен более чистый сигнал",
        "без подтверждения лучше не",
        "новый вход не разрешён",
    )
    return any(p in text for p in patterns)


def _normalize_card_by_context(card: Dict[str, Any], hold_bias: str, position: str, breakout_risk: str) -> Dict[str, Any]:
    key = str(card.get("bot_key") or "")
    note = str(card.get("note") or "")
    hold_bias = str(hold_bias or "none").lower()
    position = str(position or "UNKNOWN").upper()
    breakout_risk = str(breakout_risk or "LOW").upper()

    contra_long = hold_bias == "short" and position in {"HIGH_EDGE", "UPPER_PART"} and key in {"ct_long", "range_long"}
    contra_short = hold_bias == "long" and position in {"LOW_EDGE", "LOWER_PART"} and key in {"ct_short", "range_short"}

    if contra_long or contra_short:
        card["plan_state"] = "WAIT"
        card["management_action"] = "CANCEL SCENARIO" if key.startswith("range") else "WAIT"
        if key.startswith("range"):
            card["entry_instruction"] = "range-бот сейчас лучше не включать"
        else:
            card["entry_instruction"] = "контртренд пока не включать"
        if card.get("status") == "READY":
            card["status"] = "WATCH"
        card["can_add"] = False
        card["small_entry_only"] = False
        card["aggressive_entry_ok"] = False

    if "лучше не включать" in note.lower() or "не включать" in str(card.get("entry_instruction") or "").lower():
        card["plan_state"] = "WAIT"

    if breakout_risk == "HIGH" and key.startswith("range"):
        card["can_add"] = False

    if not bool(card.get("position_open")) and _requires_confirmation_gate(card):
        if str(card.get("status") or "").upper() == "READY":
            card["status"] = "WATCH"
        if str(card.get("plan_state") or "").upper() in {"SMALL ENTRY", "CAN ADD", "AGGRESSIVE ENTRY"}:
            card["plan_state"] = "PREPARE"
        if str(card.get("management_action") or "").upper() in {"ENABLE / CAN ADD", "ENABLE SMALL SIZE", "AGGRESSIVE ENTRY", "CAN ADD", "WAIT_EDGE"}:
            card["management_action"] = "WAIT_CONFIRM"
        card["can_add"] = False
        card["small_entry_only"] = False
        card["aggressive_entry_ok"] = False

    return card





def _fetch_spy_context() -> Dict[str, Any]:
    url = "https://stooq.com/q/d/l/?s=spy.us&i=d"
    try:
        r = requests.get(url, timeout=(4, 8))
        r.raise_for_status()
        rows = list(csv.DictReader(io.StringIO(r.text)))
        closes = []
        for row in rows[-30:]:
            try:
                closes.append(float(row.get("Close") or 0.0))
            except Exception:
                continue
        if len(closes) < 7:
            raise RuntimeError("not enough spy closes")
        last = closes[-1]
        prev = closes[-2]
        ret1 = ((last / prev) - 1.0) * 100.0 if prev else 0.0
        ret5 = ((last / closes[-6]) - 1.0) * 100.0 if closes[-6] else 0.0
        bias = "LONG" if ret5 >= 0.8 or ret1 >= 0.5 else "SHORT" if ret5 <= -0.8 or ret1 <= -0.5 else "NEUTRAL"
        comment = "S&P 500 risk-on поддерживает long risk assets" if bias == "LONG" else "S&P 500 risk-off усиливает осторожность по лонгам" if bias == "SHORT" else "S&P 500 без яркого risk-on/risk-off сигнала"
        return {"available": True, "ret1_pct": round(ret1, 2), "ret5_pct": round(ret5, 2), "bias": bias, "comment": comment}
    except Exception as exc:
        return {"available": False, "bias": "NEUTRAL", "comment": f"macro proxy недоступен: {type(exc).__name__}"}


def _comment_from_status(status: str, aggressive: bool = False) -> str:
    status_u = str(status or "OFF").upper()
    if status_u == "READY":
        return "можно усиливать агрессивнее" if aggressive else "условия собраны"
    if status_u == "WATCH":
        return "готовится, но нужен ещё триггер"
    return "пока рано включать"


def _overlay_multiplier(side: str, hold_bias: str, pattern_dir: str, pattern_conf: float, spy_bias: str, reversal_dir: str, reversal_conf: float) -> tuple[float, list[str]]:
    side = str(side or "").upper()
    m = 1.0
    notes: list[str] = []
    if hold_bias == side.lower():
        m += 0.08
        notes.append("локальная логика ginarea за эту сторону")
    elif hold_bias in {"long", "short"}:
        m -= 0.06
        notes.append("текущая локальная логика не в пользу этой стороны")

    pd = str(pattern_dir or "NEUTRAL").upper()
    if hold_bias not in {"long", "short"}:
        notes.append("pattern-memory учитывается только как overlay, не как главный триггер")
    elif (side == "LONG" and pd == "UP") or (side == "SHORT" and pd == "DOWN"):
        m += min(0.08, max(0.01, pattern_conf * 0.08))
        notes.append("исторические паттерны подтверждают")
    elif pd in {"UP", "DOWN"}:
        m -= min(0.07, max(0.01, pattern_conf * 0.07))
        notes.append("исторические паттерны спорят с идеей")

    sb = str(spy_bias or "NEUTRAL").upper()
    if (side == "LONG" and sb == "LONG") or (side == "SHORT" and sb == "SHORT"):
        m += 0.05
        notes.append("поведение S&P 500 помогает")
    elif sb in {"LONG", "SHORT"}:
        m -= 0.04
        notes.append("поведение S&P 500 мешает")

    rd = str(reversal_dir or "NEUTRAL").upper()
    if rd == side and reversal_conf >= 0.52:
        m += 0.07
        notes.append("reversal-pattern подтверждён")
    elif rd in {"LONG", "SHORT"} and rd != side and reversal_conf >= 0.52:
        m -= 0.08
        notes.append("reversal-pattern против")

    return max(0.75, min(1.30, m)), notes[:3]


def _build_unified_strategy_matrix(bot_cards: List[Dict[str, Any]], deviation_ladder: Dict[str, Any], hold_bias: str, pattern_dir: str, pattern_conf: float, spy_ctx: Dict[str, Any], reversal_dir: str, reversal_conf: float) -> List[Dict[str, Any]]:
    card_map = {str(c.get("bot_key") or ""): c for c in bot_cards}
    matrix: List[Dict[str, Any]] = []
    for item in (deviation_ladder.get("long_ladder") or []):
        mult, notes = _overlay_multiplier("LONG", hold_bias, pattern_dir, pattern_conf, spy_ctx.get("bias"), reversal_dir, reversal_conf)
        base_status = str(item.get("status") or "OFF")
        aggressive = bool(item.get("aggressive"))
        if mult >= 1.12 and base_status == "WATCH":
            final_status = "READY"
        elif mult <= 0.88 and base_status == "READY":
            final_status = "WATCH"
        else:
            final_status = base_status
        matrix.append({
            "key": item.get("key"), "label": item.get("label"), "group": "DEVIATION", "side": "LONG",
            "status": final_status, "action": "УСИЛИВАТЬ" if final_status == "READY" and aggressive else "ВКЛЮЧАТЬ" if final_status == "READY" else "СМОТРЕТЬ" if final_status == "WATCH" else "ОСЛАБИТЬ",
            "comment": "; ".join(notes + [_comment_from_status(final_status, aggressive)]),
        })
    for item in (deviation_ladder.get("short_ladder") or []):
        mult, notes = _overlay_multiplier("SHORT", hold_bias, pattern_dir, pattern_conf, spy_ctx.get("bias"), reversal_dir, reversal_conf)
        base_status = str(item.get("status") or "OFF")
        aggressive = bool(item.get("aggressive"))
        if mult >= 1.12 and base_status == "WATCH":
            final_status = "READY"
        elif mult <= 0.88 and base_status == "READY":
            final_status = "WATCH"
        else:
            final_status = base_status
        matrix.append({
            "key": item.get("key"), "label": item.get("label"), "group": "DEVIATION", "side": "SHORT",
            "status": final_status, "action": "УСИЛИВАТЬ" if final_status == "READY" and aggressive else "ВКЛЮЧАТЬ" if final_status == "READY" else "СМОТРЕТЬ" if final_status == "WATCH" else "ОСЛАБИТЬ",
            "comment": "; ".join(notes + [_comment_from_status(final_status, aggressive)]),
        })
    for key in ("range_long", "range_short"):
        card = card_map.get(key, {})
        side = "LONG" if key.endswith("long") else "SHORT"
        mult, notes = _overlay_multiplier(side, hold_bias, pattern_dir, pattern_conf, spy_ctx.get("bias"), reversal_dir, reversal_conf)
        score = float(card.get("score") or 0.0) * mult
        card_plan_state = str(card.get("plan_state") or "WAIT").upper()
        card_management = str(card.get("management_action") or "WAIT").upper()
        confirm_gated = card_plan_state in {"WAIT", "PREPARE", "WATCH"} or card_management in {"WAIT_CONFIRM", "WAIT EDGE", "WAIT_EDGE"}
        status = "READY" if score >= 0.62 and not confirm_gated else "WATCH" if score >= 0.42 or confirm_gated else "OFF"
        action = "УСИЛИВАТЬ" if status == "READY" and mult >= 1.05 else "ВКЛЮЧАТЬ" if status == "READY" else "СМОТРЕТЬ" if status == "WATCH" else "ОСЛАБИТЬ"
        matrix.append({
            "key": key, "label": str(card.get("bot_label") or key), "group": "RANGE", "side": side,
            "status": status, "action": action,
            "comment": "; ".join(notes + [str(card.get("entry_instruction") or _comment_from_status(status))]),
        })
    return matrix


def _build_overlay_commentary(hold_bias: str, pattern_dir: str, pattern_conf: float, pattern_summary: str, spy_ctx: Dict[str, Any], reversal_patterns: List[str], unified_matrix: List[Dict[str, Any]]) -> List[str]:
    lines: List[str] = []
    if pattern_summary:
        lines.append(f"история/паттерны: {pattern_summary}")
    pd = str(pattern_dir or "NEUTRAL").upper()
    if pd in {"UP", "DOWN"}:
        lines.append(f"паттерн-память сейчас {'за лонг' if pd == 'UP' else 'за шорт'} ({pattern_conf * 100:.1f}%)")
    if spy_ctx.get("available"):
        lines.append(f"S&P 500: 1d {spy_ctx.get('ret1_pct', 0.0):+.2f}% / 5d {spy_ctx.get('ret5_pct', 0.0):+.2f}% — {spy_ctx.get('comment')}")
    else:
        lines.append(str(spy_ctx.get("comment") or "macro proxy недоступен"))
    if reversal_patterns:
        lines.append("паттерны цены сейчас: " + ", ".join(str(x) for x in reversal_patterns[:3]))
    ready = [m for m in unified_matrix if str(m.get("status")) == "READY"]
    if ready:
        top = ready[:2]
        lines.append("по совокупности логики сейчас сильнее: " + ", ".join(f"{x.get('label')} ({x.get('action')})" for x in top))
    elif unified_matrix:
        watch = [m for m in unified_matrix if str(m.get("status")) == "WATCH"][:2]
        if watch:
            lines.append("пока без полного ready; ближе всего к активации: " + ", ".join(f"{x.get('label')}" for x in watch))
    if hold_bias in {"long", "short"}:
        lines.append(f"локальный приоритет ginarea: {hold_bias.upper()} — но он теперь фильтруется паттернами и risk-on/risk-off")
    return lines[:6]

def _extract_deviation_tier(label: str) -> float:
    text = str(label or "")
    for raw in ("1.3", "2.5", "3.5"):
        if raw in text:
            return float(raw)
    return 0.0


def _size_label(size_pct: int) -> str:
    if size_pct >= 100:
        return "100% | aggressive"
    if size_pct >= 75:
        return "75% | add / confident"
    if size_pct >= 50:
        return "50% | small"
    if size_pct >= 25:
        return "25% | probe / defensive"
    return "0% | off"




def _learning_rank_adjustment(card: Dict[str, Any], learning_summary: Dict[str, Any]) -> Dict[str, Any]:
    key = str(card.get("bot_key") or "").strip()
    cards = list((learning_summary or {}).get("learning_cards") or [])
    selected = None
    for item in cards:
        if str(item.get("bot_key") or "").strip() == key:
            selected = item
            break
    if selected is None:
        return {"delta": 0.0, "summary": "нет learning-данных для ranking", "reasons": []}

    samples = int(selected.get("samples") or 0)
    closed_trades = int(selected.get("closed_trades") or 0)
    wins = int(selected.get("wins") or 0)
    losses = int(selected.get("losses") or 0)
    breakeven = int(selected.get("breakeven") or 0)
    avg_rr = _safe_float(selected.get("avg_rr"), 0.0)
    avg_result_pct = _safe_float(selected.get("avg_result_pct"), 0.0)
    success_ratio = _safe_float(selected.get("success_ratio"), 0.5)
    learned_mode = str(selected.get("learned_mode") or "NEUTRAL").upper()

    delta = 0.0
    reasons: List[str] = []

    if closed_trades >= 3:
        base = min(0.10, 0.02 + closed_trades * 0.005)
        if wins > losses:
            delta += base
            reasons.append("закрытые сделки этого бота исторически лучше среднего")
        elif losses > wins:
            delta -= base
            reasons.append("закрытые сделки этого бота исторически слабее среднего")

        if avg_rr >= 1.2:
            delta += min(0.05, (avg_rr - 1.0) * 0.03)
            reasons.append("avg RR поддерживает приоритет этого бота")
        elif avg_rr <= 0.8 and losses >= wins:
            delta -= min(0.05, (1.0 - avg_rr) * 0.04)
            reasons.append("avg RR просит охлаждать приоритет этого бота")

        if avg_result_pct >= 0.4:
            delta += 0.02
            reasons.append("средний результат сделки положительный")
        elif avg_result_pct <= -0.4:
            delta -= 0.02
            reasons.append("средний результат сделки отрицательный")

    if samples >= 3 and learned_mode == "FAVORED":
        delta += 0.015
    elif samples >= 3 and learned_mode == "CAUTIOUS":
        delta -= 0.015

    if wins == 0 and losses == 0 and breakeven == 0:
        delta *= 0.35
        if reasons:
            reasons.append("закрытых сделок ещё мало, влияние ranking ограничено")

    delta = max(-0.12, min(0.12, delta))
    if abs(delta) < 0.005:
        summary = "learning почти не меняет ranking"
    elif delta > 0:
        summary = "learning поднимает приоритет бота"
    else:
        summary = "learning опускает приоритет бота"
    return {
        "delta": round(delta, 4),
        "summary": summary,
        "reasons": reasons[:3],
        "closed_trades": closed_trades,
        "wins": wins,
        "losses": losses,
        "breakeven": breakeven,
        "avg_rr": round(avg_rr, 3),
        "avg_result_pct": round(avg_result_pct, 3),
        "success_ratio": round(success_ratio, 3),
    }

def _build_size_allocator(unified_matrix: List[Dict[str, Any]], deviation_ladder: Dict[str, Any], hold_bias: str, execution_bias: str) -> Dict[str, Any]:
    active_side = str(deviation_ladder.get("active_side") or "NONE").upper()
    strongest_tier = float(deviation_ladder.get("strongest_tier") or 0.0)
    sized: List[Dict[str, Any]] = []

    for item in unified_matrix:
        label = str(item.get("label") or item.get("key") or "BOT")
        side = str(item.get("side") or "NEUTRAL").upper()
        status = str(item.get("status") or "OFF").upper()
        action = str(item.get("action") or "WAIT").upper()
        group = str(item.get("group") or "GENERIC").upper()
        tier = _extract_deviation_tier(label)

        if status == "OFF":
            size_pct = 0
        elif status == "WATCH":
            size_pct = 25
        else:
            size_pct = 50

        if group == "DEVIATION":
            if active_side != "NONE" and side != active_side:
                size_pct = 0
            else:
                if strongest_tier >= 3.5:
                    if abs(tier - 1.3) < 0.01:
                        size_pct = max(size_pct, 75)
                    elif abs(tier - 2.5) < 0.01:
                        size_pct = max(size_pct, 50)
                    elif abs(tier - 3.5) < 0.01 and status != "OFF":
                        size_pct = max(size_pct, 25)
                elif strongest_tier >= 2.5:
                    if abs(tier - 1.3) < 0.01:
                        size_pct = max(size_pct, 50)
                    elif abs(tier - 2.5) < 0.01 and status != "OFF":
                        size_pct = max(size_pct, 25)
                    elif abs(tier - 3.5) < 0.01:
                        size_pct = 0
                elif strongest_tier >= 1.3:
                    if abs(tier - 1.3) < 0.01:
                        size_pct = max(size_pct, 25 if status == "WATCH" else 50)
                    else:
                        size_pct = 0
                else:
                    size_pct = 0
        elif group == "RANGE":
            if active_side in {"LONG", "SHORT"}:
                if side == active_side:
                    size_pct = min(size_pct, 25 if execution_bias == "SCALP ONLY" else 50)
                else:
                    size_pct = 0
            else:
                if hold_bias == side.lower():
                    size_pct = max(size_pct, 25)
                elif execution_bias == "WAIT":
                    size_pct = min(size_pct, 25)

        if action == "УСИЛИВАТЬ" and size_pct > 0:
            size_pct = min(100, size_pct + 25)
        elif action == "ВКЛЮЧАТЬ" and size_pct > 0:
            size_pct = max(size_pct, 50 if group == "DEVIATION" and strongest_tier >= 2.5 and side == active_side else size_pct)
        elif action == "ОСЛАБИТЬ":
            size_pct = min(size_pct, 25)

        if hold_bias in {"long", "short"} and side == hold_bias.upper():
            size_pct = min(100, size_pct + (0 if group == "DEVIATION" else 10))
        elif hold_bias in {"long", "short"} and side in {"LONG", "SHORT"} and side != hold_bias.upper():
            size_pct = max(0, size_pct - 15)

        size_pct = max(0, min(100, int(round(size_pct / 5.0) * 5)))
        item["recommended_size_pct"] = size_pct
        item["size_label"] = _size_label(size_pct)
        sized.append(item)

    sized.sort(key=lambda x: (int(x.get("recommended_size_pct") or 0), 1 if str(x.get("status") or "") == "READY" else 0), reverse=True)
    enabled = [x for x in sized if int(x.get("recommended_size_pct") or 0) > 0]
    primary = enabled[0] if enabled else None
    secondary = enabled[1] if len(enabled) > 1 else None
    reduce = [x.get("label") for x in sized if int(x.get("recommended_size_pct") or 0) == 0 and str(x.get("status") or "") in {"WATCH", "READY"}]

    max_size = int(primary.get("recommended_size_pct") or 0) if primary else 0
    if max_size >= 100:
        aggression_mode = "MAX AGGRESSIVE"
    elif max_size >= 75:
        aggression_mode = "AGGRESSIVE ALLOWED"
    elif max_size >= 50:
        aggression_mode = "BALANCED"
    elif max_size >= 25:
        aggression_mode = "DEFENSIVE PROBE"
    else:
        aggression_mode = "WAIT"

    size_plan: List[str] = []
    for item in enabled[:4]:
        size_plan.append(f"{item.get('label')}: {item.get('size_label')}")

    return {
        "matrix": sized,
        "primary_bot": primary.get("label") if primary else None,
        "secondary_bot": secondary.get("label") if secondary else None,
        "primary_size_pct": int(primary.get("recommended_size_pct") or 0) if primary else 0,
        "secondary_size_pct": int(secondary.get("recommended_size_pct") or 0) if secondary else 0,
        "aggression_mode": aggression_mode,
        "size_plan": size_plan,
        "bots_to_reduce": reduce[:4],
    }


def _deviation_status(abs_dev_pct: float, threshold: float) -> str:
    if abs_dev_pct >= threshold:
        return "READY"
    if abs_dev_pct >= threshold * 0.72:
        return "WATCH"
    return "OFF"


def _build_deviation_ladder(symbol: str, hold_bias: str, breakout_risk: str, preferred_bot: str) -> Dict[str, Any]:
    try:
        df5 = load_klines(symbol=symbol, timeframe="5m", limit=120)
        if df5 is None or df5.empty or len(df5) < 15:
            raise RuntimeError("not enough 5m data")
        close = df5["close"].astype(float)
        price = float(close.iloc[-1])
        base_price = float(close.iloc[-13]) if len(close) >= 13 else float(close.iloc[0])
        impulse_move_pct = ((price / base_price) - 1.0) * 100.0 if base_price else 0.0
        abs_move_pct = abs(impulse_move_pct)
        thresholds = [1.5, 2.5, 3.3]
        long_ladder = []
        short_ladder = []
        for threshold in thresholds:
            long_ladder.append({
                "key": f"impulse_long_{str(threshold).replace('.', '_')}",
                "label": f"LONG IMPULSE {threshold:.1f}%",
                "threshold": threshold,
                "status": _deviation_status(abs_move_pct, threshold) if impulse_move_pct <= 0 else "OFF",
                "aggressive": abs_move_pct >= threshold and threshold >= 2.5 and impulse_move_pct <= 0,
            })
            short_ladder.append({
                "key": f"impulse_short_{str(threshold).replace('.', '_')}",
                "label": f"SHORT IMPULSE {threshold:.1f}%",
                "threshold": threshold,
                "status": _deviation_status(abs_move_pct, threshold) if impulse_move_pct >= 0 else "OFF",
                "aggressive": abs_move_pct >= threshold and threshold >= 2.5 and impulse_move_pct >= 0,
            })

        active_side = "LONG" if impulse_move_pct <= -1.5 else "SHORT" if impulse_move_pct >= 1.5 else "NONE"
        strongest_tier = 0.0
        if active_side != "NONE":
            for threshold in thresholds:
                if abs_move_pct >= threshold:
                    strongest_tier = threshold

        ladder_action = "ждать более резкий импульс от текущей проторговки"
        if active_side == "LONG":
            if strongest_tier >= 3.3:
                ladder_action = "long impulse 3.3% активен: 3.3% можно вести агрессивнее; 2.5% держать; 1.5% базовый"
            elif strongest_tier >= 2.5:
                ladder_action = "long impulse 2.5% активен: можно усиливать второй long-бот; 1.5% держать базой; 3.3% ждать"
            elif strongest_tier >= 1.5:
                ladder_action = "сработал первый long-бот 1.5%; дальнейшее усиление только если импульс растянется сильнее"
        elif active_side == "SHORT":
            if strongest_tier >= 3.3:
                ladder_action = "short impulse 3.3% активен: 3.3% можно вести агрессивнее; 2.5% держать; 1.5% базовый"
            elif strongest_tier >= 2.5:
                ladder_action = "short impulse 2.5% активен: можно усиливать второй short-бот; 1.5% держать базой; 3.3% ждать"
            elif strongest_tier >= 1.5:
                ladder_action = "сработал первый short-бот 1.5%; дальнейшее усиление только если импульс растянется сильнее"

        range_bias = "нейтрально"
        range_action = "range-боты пока вторичны"
        if breakout_risk in {"LOW", "MEDIUM"}:
            if hold_bias == "long":
                range_bias = "RANGE LONG"
                range_action = "range long усиливать только после стабилизации и возврата в спокойную проторговку"
            elif hold_bias == "short":
                range_bias = "RANGE SHORT"
                range_action = "range short усиливать только после стабилизации и возврата в спокойную проторговку"
            else:
                range_bias = "RANGE BOTH"
                range_action = "если импульс погас и цена снова крутится узко, можно подключать объёмные range-боты малым размером"

        preferred_ladder = preferred_bot
        if active_side == "LONG":
            preferred_ladder = f"impulse long {strongest_tier:.1f}%" if strongest_tier else "impulse long watch"
        elif active_side == "SHORT":
            preferred_ladder = f"impulse short {strongest_tier:.1f}%" if strongest_tier else "impulse short watch"

        summary = []
        if active_side == "LONG":
            summary.append(f"за последние 60m цена резко ушла вниз на {abs_move_pct:.2f}% от базы {base_price:.2f} — long impulse-боты в работе")
        elif active_side == "SHORT":
            summary.append(f"за последние 60m цена резко ушла вверх на {abs_move_pct:.2f}% от базы {base_price:.2f} — short impulse-боты в работе")
        else:
            summary.append(f"за 60m импульс всего {impulse_move_pct:+.2f}% от базы {base_price:.2f} — impulse-боты лучше не форсировать")
        # history-informed qualitative assessment, not a full backtest
        if strongest_tier >= 3.3:
            summary.append("3.3% tier исторически стоит вести только как агрессивный добор с быстрым контролем риска, без усреднения вслепую")
        elif strongest_tier >= 2.5:
            summary.append("2.5% tier выглядит как рабочая зона для усиления, но лучше только при замедлении импульса или первом признаке поглощения")
        elif strongest_tier >= 1.5:
            summary.append("1.5% tier выглядит как ранний триггер: хороший стартовый слой, но не повод сразу включать максимальный размер")
        else:
            summary.append("для истории такая лестница обычно лучше работает как staged-entry, а не как одиночный all-in на первом импульсе")
        summary.append(ladder_action)
        summary.append(range_action)

        return {
            "impulse_base_price": round(base_price, 2),
            "price": round(price, 2),
            "impulse_move_pct": round(impulse_move_pct, 3),
            "abs_impulse_move_pct": round(abs_move_pct, 3),
            "active_side": active_side,
            "strongest_tier": strongest_tier,
            "long_ladder": long_ladder,
            "short_ladder": short_ladder,
            "ladder_action": ladder_action,
            "range_bias": range_bias,
            "range_action": range_action,
            "preferred_ladder": preferred_ladder,
            "summary": summary,
            "evaluation_note": "это history-informed qualitative overlay, не полноценный статистический бэктест",
        }
    except Exception:
        return {
            "impulse_base_price": 0.0,
            "price": 0.0,
            "impulse_move_pct": 0.0,
            "abs_impulse_move_pct": 0.0,
            "active_side": "NONE",
            "strongest_tier": 0.0,
            "long_ladder": [],
            "short_ladder": [],
            "ladder_action": "не удалось рассчитать impulse ladder",
            "range_bias": "нейтрально",
            "range_action": "range-боты пока вторичны",
            "preferred_ladder": preferred_bot,
            "summary": ["impulse ladder временно недоступен"],
            "evaluation_note": "history-informed overlay недоступен",
        }

def analyze_ginarea(symbol: str = "BTCUSDT", timeframe: str = "1h") -> Dict[str, Any]:
    df = add_indicators(load_klines(symbol=symbol, timeframe=timeframe, limit=160))
    last = df.iloc[-1]
    rng = analyze_range(symbol=symbol, timeframe=timeframe)
    reversal = analyze_reversal(df, range_info=rng)
    try:
        history_pattern = analyze_history_pattern(df.tail(120), symbol=symbol, timeframe=timeframe)
    except Exception:
        history_pattern = {"direction": "NEUTRAL", "confidence": 0.0, "summary": "pattern-memory недоступна"}
    spy_ctx = _fetch_spy_context()

    # локальный контекст анализа: не должен ронять ginarea, если общий analysis не передан
    analysis: Dict[str, Any] = {}

    price = float(last["close"])
    rsi = float(last.get("rsi14", 50.0))
    low = float(rng["range_low"])
    high = float(rng["range_high"])
    mid = float(rng["range_mid"])
    position = str(rng.get("range_position") or "UNKNOWN").upper()
    edge_bias = str(rng.get("edge_bias") or "NONE").upper()
    breakout_risk = str(rng.get("breakout_risk") or "LOW").upper()
    edge_score = _safe_float(rng.get("edge_score"), 0.0)
    reversal_dir = str(reversal.get("direction") or "NEUTRAL").upper()
    reversal_conf = _safe_float(reversal.get("confidence"), 0.0)
    false_break_signal = str(reversal.get("false_break_signal") or "NONE").upper()
    trap_comment = str(reversal.get("trap_comment") or "").strip()

    if reversal_dir == "SHORT" and reversal_conf >= 0.52:
        ct_now = "контртренд: найден bearish rejection / возможен разворот вниз"
    elif reversal_dir == "LONG" and reversal_conf >= 0.52:
        ct_now = "контртренд: найден bullish rejection / возможен разворот вверх"
    elif rsi < 35 and price <= mid:
        ct_now = "контртренд: рынок локально перепродан, возможен отскок"
    elif rsi > 65 and price >= mid:
        ct_now = "контртренд: рынок локально перегрет, возможен откат"
    else:
        ct_now = "контртренд: явного перекоса нет"

    if abs(price - low) < abs(price - high):
        ginarea = f"ближе поддержка в районе {low:.0f}, середина {mid:.0f}"
    else:
        ginarea = f"ближе сопротивление в районе {high:.0f}, середина {mid:.0f}"

    preferred_bot = "none"
    trade_style = "wait"
    hold_bias = "none"
    scalp_only = False
    confirmation_needed = True
    reentry_zone = "ждать формирование новой зоны"
    invalidation_hint = "отмена идеи при закреплении за пределом рабочей зоны"
    tactical_plan: List[str] = []

    if edge_bias == "LONG_EDGE":
        preferred_bot = "ct_long" if reversal_dir == "LONG" or false_break_signal == "DOWN_TRAP" else "range_long"
        hold_bias = "long"
        reentry_zone = f"зона возврата/выкупа {low:.0f}-{mid:.0f}"
        invalidation_hint = f"лонг-идея ухудшится при закреплении ниже {low:.0f}"
        tactical_plan.append(f"лонг-контекст сильнее у поддержки {low:.0f}")
    elif edge_bias == "SHORT_EDGE":
        preferred_bot = "ct_short" if reversal_dir == "SHORT" or false_break_signal == "UP_TRAP" else "range_short"
        hold_bias = "short"
        reentry_zone = f"зона возврата/отката {mid:.0f}-{high:.0f}"
        invalidation_hint = f"шорт-идея ухудшится при закреплении выше {high:.0f}"
        tactical_plan.append(f"шорт-контекст сильнее у сопротивления {high:.0f}")
    else:
        scalp_only = True
        reentry_zone = f"лучше ждать подхода к {low:.0f} или {high:.0f}"
        tactical_plan.append("середина диапазона чаще даёт слабый edge и плохой RR")

    if false_break_signal == "UP_TRAP":
        preferred_bot = "ct_short"
        trade_style = "reversal_short"
        hold_bias = "short"
        scalp_only = False if position in {"HIGH_EDGE", "UPPER_PART"} else True
        tactical_plan.append("после ложного выноса вверх лучше ждать возврат под high и давление продавца")
    elif false_break_signal == "DOWN_TRAP":
        preferred_bot = "ct_long"
        trade_style = "reversal_long"
        hold_bias = "long"
        scalp_only = False if position in {"LOW_EDGE", "LOWER_PART"} else True
        tactical_plan.append("после ложного выноса вниз лучше ждать возврат над low и подтверждение покупателя")
    elif reversal_dir == "LONG" and reversal_conf >= 0.52:
        trade_style = "countertrend_long"
        preferred_bot = preferred_bot if preferred_bot != "none" else "ct_long"
        scalp_only = position not in {"LOW_EDGE", "LOWER_PART"}
        tactical_plan.append("лонг только после подтверждённого выкупа, не на первой свече")
    elif reversal_dir == "SHORT" and reversal_conf >= 0.52:
        trade_style = "countertrend_short"
        preferred_bot = preferred_bot if preferred_bot != "none" else "ct_short"
        scalp_only = position not in {"HIGH_EDGE", "UPPER_PART"}
        tactical_plan.append("шорт только после подтверждённого rejection, не в догонку")
    elif position == "MID":
        trade_style = "wait_range_edge"
        scalp_only = True
        tactical_plan.append("в середине диапазона лучше ждать край или новый импульс")
    elif edge_score >= 0.55 and breakout_risk != "HIGH":
        trade_style = "range_edge"
        confirmation_needed = False
        tactical_plan.append("есть edge у границы диапазона, можно работать аккуратнее по месту")
    else:
        trade_style = "wait_confirmation"
        tactical_plan.append("нужен более чистый сигнал или повторная реакция от уровня")

    if breakout_risk == "HIGH":
        scalp_only = True
        confirmation_needed = True
        tactical_plan.append("риск выноса высокий, без подтверждения лучше не удерживать позицию")
    elif breakout_risk == "MEDIUM":
        tactical_plan.append("если входить, то с быстрой оценкой удержания уровня")

    if rsi >= 68 and hold_bias == "long":
        scalp_only = True
        tactical_plan.append("лонг уже перегрет, без отката лучше не рассчитывать на hold")
    if rsi <= 32 and hold_bias == "short":
        scalp_only = True
        tactical_plan.append("шорт уже растянут вниз, лучше не давить продажу внизу")

    if scalp_only and hold_bias in {"long", "short"}:
        tactical_plan.append("скорее scalp / partial, чем спокойный hold")
    if confirmation_needed:
        tactical_plan.append("подтверждение: удержание уровня, возврат в диапазон или свеча продолжения")
    if trap_comment:
        tactical_plan.append(trap_comment)
    tactical_plan = _dedupe(tactical_plan)[:7]

    ct_long_score = 0.18
    ct_short_score = 0.18
    range_long_score = 0.18
    range_short_score = 0.18

    if position in {"LOW_EDGE", "LOWER_PART"}:
        ct_long_score += 0.16
        range_long_score += 0.22
    elif position in {"HIGH_EDGE", "UPPER_PART"}:
        ct_short_score += 0.16
        range_short_score += 0.22
    elif position == "MID":
        ct_long_score -= 0.06
        ct_short_score -= 0.06
        range_long_score -= 0.10
        range_short_score -= 0.10

    if edge_bias == "LONG_EDGE":
        ct_long_score += 0.10
        range_long_score += 0.18
    elif edge_bias == "SHORT_EDGE":
        ct_short_score += 0.10
        range_short_score += 0.18

    if false_break_signal == "DOWN_TRAP":
        ct_long_score += 0.34
        range_short_score -= 0.08
    elif false_break_signal == "UP_TRAP":
        ct_short_score += 0.34
        range_long_score -= 0.08

    if reversal_dir == "LONG":
        ct_long_score += 0.22 * min(1.0, reversal_conf)
    elif reversal_dir == "SHORT":
        ct_short_score += 0.22 * min(1.0, reversal_conf)

    if breakout_risk == "HIGH":
        range_long_score -= 0.18
        range_short_score -= 0.18
    elif breakout_risk == "MEDIUM":
        range_long_score -= 0.08
        range_short_score -= 0.08

    if rsi < 34:
        ct_long_score += 0.08
        ct_short_score -= 0.05
    elif rsi > 66:
        ct_short_score += 0.08
        ct_long_score -= 0.05

    if trade_style in {"reversal_long", "countertrend_long"}:
        ct_long_score += 0.12
    elif trade_style in {"reversal_short", "countertrend_short"}:
        ct_short_score += 0.12
    elif trade_style == "range_edge":
        if hold_bias == "long":
            range_long_score += 0.10
        elif hold_bias == "short":
            range_short_score += 0.10

    if scalp_only:
        ct_long_score -= 0.03
        ct_short_score -= 0.03
        range_long_score -= 0.06
        range_short_score -= 0.06

    ct_long_score = max(0.0, min(1.0, ct_long_score))
    ct_short_score = max(0.0, min(1.0, ct_short_score))
    range_long_score = max(0.0, min(1.0, range_long_score))
    range_short_score = max(0.0, min(1.0, range_short_score))

    bot_cards = [
        _make_bot_card(
            "ct_long", ct_long_score, f"{low:.0f}-{mid:.0f}", f"слабее при закреплении ниже {low:.0f}",
            "ловить выкуп / reclaim от low, не брать первую свечу" if ct_long_score >= 0.45 else "контртренд long пока не собран",
            "scalp" if scalp_only or ct_long_score < 0.72 else "intraday",
            "контртренд от low / false-break long", "вход только после выкупа и удержания low",
        ),
        _make_bot_card(
            "ct_short", ct_short_score, f"{mid:.0f}-{high:.0f}", f"слабее при закреплении выше {high:.0f}",
            "ловить rejection / возврат под high, не шортить в дно" if ct_short_score >= 0.45 else "контртренд short пока не собран",
            "scalp" if scalp_only or ct_short_score < 0.72 else "intraday",
            "контртренд от high / false-break short", "вход после rejection и возврата под high",
        ),
        _make_bot_card(
            "range_long", range_long_score, f"{low:.0f}-{mid:.0f}", f"range long ломается при выходе ниже {low:.0f}",
            "работать от поддержки диапазона, если нет явного breakdown pressure" if range_long_score >= 0.45 else "range long слабый / далеко от зоны",
            "scalp" if breakout_risk == "HIGH" or range_long_score < 0.70 else "intraday",
            "отбой от диапазона вверх", "лучше после касания края и удержания диапазона",
        ),
        _make_bot_card(
            "range_short", range_short_score, f"{mid:.0f}-{high:.0f}", f"range short ломается при выходе выше {high:.0f}",
            "работать от сопротивления диапазона, если нет явного breakout pressure" if range_short_score >= 0.45 else "range short слабый / далеко от зоны",
            "scalp" if breakout_risk == "HIGH" or range_short_score < 0.70 else "intraday",
            "отбой от диапазона вниз", "лучше после реакции от верхней границы",
        ),
    ]
    for card in bot_cards:
        key = str(card.get("bot_key") or "")
        score = float(card.get("score") or 0.0)
        card["plan_state"] = _plan_state_by_score(score)
        card["management_action"] = _management_action(card, breakout_risk, position, trap_comment)
        card["entry_instruction"] = _entry_instruction(key, score, breakout_risk, position)
        card["exit_instruction"] = _exit_instruction(key, score, breakout_risk, trap_comment)
        card["can_add"] = bool(score >= 0.68 and card.get("status") in {"READY", "WATCH"})
        card["small_entry_only"] = bool(key.startswith("ct_") and 0.45 <= score < 0.68)
        card["aggressive_entry_ok"] = bool(score >= 0.82 and card.get("status") == "READY")
        _normalize_card_by_context(card, hold_bias, position, breakout_risk)

    manager_state = sync_bot_manager(bot_cards)
    learning_state = update_personal_bot_learning(bot_cards, {
        'market_regime': trade_style,
        'range_position': position,
        'trade_style': trade_style,
        'breakout_risk': breakout_risk,
    })
    learning_summary = summarize_personal_bot_learning(learning_state, bot_cards)
    learning_adjustments = build_learning_adjustments(learning_summary, trade_style, position)

    for card in bot_cards:
        learn = learning_adjustments.get(str(card.get("bot_key") or ""), {})
        raw_score = float(card.get("score") or 0.0)
        delta = float(learn.get("delta") or 0.0)
        adjusted = max(0.0, min(1.0, raw_score + delta))
        card["raw_score"] = round(raw_score, 3)
        card["learning_delta"] = round(delta, 3)
        card["learning_context_match"] = bool(learn.get("context_match"))
        card["learning_reasons"] = list(learn.get("reasons") or [])
        card["learning_mode"] = str(learn.get("mode") or "NEUTRAL")
        card["score"] = round(adjusted, 3)
        card["status"] = _bot_status(adjusted)
        _normalize_card_by_context(card, hold_bias, position, breakout_risk)

    execution_learning = build_learning_execution_adjustments(learning_summary, bot_cards, trade_style, position)
    learning_execution_summary: List[str] = []
    learning_ranking_summary: List[str] = []

    for card in bot_cards:
        rank_learn = _learning_rank_adjustment(card, learning_summary)
        card["learning_rank_delta"] = float(rank_learn.get("delta") or 0.0)
        card["learning_rank_summary"] = str(rank_learn.get("summary") or "")
        card["learning_rank_reasons"] = list(rank_learn.get("reasons") or [])
        card["learning_closed_trades"] = int(rank_learn.get("closed_trades") or 0)
        card["learning_wins"] = int(rank_learn.get("wins") or 0)
        card["learning_losses"] = int(rank_learn.get("losses") or 0)
        card["learning_breakeven"] = int(rank_learn.get("breakeven") or 0)
        card["learning_avg_rr"] = float(rank_learn.get("avg_rr") or 0.0)
        card["learning_avg_result_pct"] = float(rank_learn.get("avg_result_pct") or 0.0)

        exec_learn = execution_learning.get(str(card.get("bot_key") or ""), {})
        card["execution_learning_delta"] = float(exec_learn.get("execution_delta") or 0.0)
        card["execution_learning_mode"] = str(exec_learn.get("execution_mode") or "NEUTRAL")
        card["execution_learning_summary"] = str(exec_learn.get("summary") or "")
        card["execution_learning_reasons"] = list(exec_learn.get("reasons") or [])
        card["base_plan_state"] = str(card.get("plan_state") or "WAIT")
        card["base_management_action"] = str(card.get("management_action") or "WAIT")
        card["base_entry_instruction"] = str(card.get("entry_instruction") or "")
        card["base_exit_instruction"] = str(card.get("exit_instruction") or "")

        if str(card.get("execution_learning_mode") or "NEUTRAL").upper() in {"BOOST", "COOL"}:
            card["plan_state"] = str(exec_learn.get("adjusted_plan_state") or card.get("plan_state") or "WAIT")
            card["management_action"] = str(exec_learn.get("adjusted_management_action") or card.get("management_action") or "WAIT")
            card["entry_instruction"] = str(exec_learn.get("adjusted_entry_instruction") or card.get("entry_instruction") or "")
            card["exit_instruction"] = str(exec_learn.get("adjusted_exit_instruction") or card.get("exit_instruction") or "")

        if abs(float(card.get("execution_learning_delta") or 0.0)) >= 0.01:
            sign = "+" if float(card.get("execution_learning_delta") or 0.0) >= 0 else ""
            learning_execution_summary.append(
                f"{card.get('bot_label')}: execution {sign}{float(card.get('execution_learning_delta') or 0.0) * 100:.1f}% — {card.get('execution_learning_summary')}"
            )
        if abs(float(card.get("learning_rank_delta") or 0.0)) >= 0.01:
            sign = "+" if float(card.get("learning_rank_delta") or 0.0) >= 0 else ""
            learning_ranking_summary.append(
                f"{card.get('bot_label')}: ranking {sign}{float(card.get('learning_rank_delta') or 0.0) * 100:.1f}% — {card.get('learning_rank_summary')}"
            )

    for card in bot_cards:
        manager = card.get("manager_state") or {}
        phase = str(manager.get("phase") or "IDLE")
        size_hint = str(manager.get("size_hint") or "NONE")
        adds_used = int(manager.get("adds_used") or 0)
        card["manager_phase"] = phase
        card["size_hint"] = size_hint
        card["adds_used"] = adds_used
        card["position_open"] = bool(manager.get("position_open"))
        card["manager_comment"] = str(manager.get("note") or "").strip()

    for card in bot_cards:
        activation_state = str(card.get("activation_state") or "OFF").upper()
        activation_bonus = 0.0
        if activation_state == "ARMED":
            activation_bonus = 0.08
        elif activation_state == "WAIT":
            activation_bonus = 0.02
        raw_score = float(card.get("score") or 0.0)
        rank_delta = float(card.get("learning_rank_delta") or 0.0)
        card["ranking_score_raw"] = round(raw_score + activation_bonus, 3)
        card["ranking_score"] = round(max(0.0, min(1.0, raw_score + activation_bonus + rank_delta)), 3)

    volume_bot_status = ''
    try:
        volume_bot_status = str((build_bot_control_center(bot_cards, execution_bias) or {}).get('range_volume_mode') or '')
    except Exception:
        volume_bot_status = ''
    confirmation_ready = 0.0
    try:
        confirmation_ready = float((analysis.get('arming_logic') or {}).get('confirm_ready') or 0.0)
    except Exception:
        confirmation_ready = 0.0
    decision_block = analysis.get('decision') if isinstance(analysis.get('decision'), dict) else {}
    decision_execution = str(decision_block.get('execution') or '').upper()
    decision_action = str(decision_block.get('action') or '').upper()
    soft_probe_allowed = decision_execution == 'PROBE_ALLOWED' or decision_action in {'ENTER','ВХОДИТЬ','PROBE'}
    no_trade_lock = _truth_lock_active(edge_score, volume_bot_status, confirmation_ready=confirmation_ready) and (not soft_probe_allowed)
    if no_trade_lock:
        for card in bot_cards:
            card['small_entry_only'] = False
            card['can_add'] = False
            card['aggressive_entry_ok'] = False
            if bool(card.get('position_open')):
                card['status'] = 'OPEN'
                card['plan_state'] = 'MANAGE ONLY'
                card['management_action'] = 'MANAGE OPEN'
                card['entry_instruction'] = 'новый вход не разрешён; только сопровождение уже открытой позиции'
                card['exit_instruction'] = 'частичный выход / защита остатка только после confirm'
                continue
            card['status'] = 'BLOCKED' if not bool(card.get('position_open')) else card.get('status')
            if str(card.get('bot_key') or '').startswith('range'):
                card['plan_state'] = 'WAIT'
                card['management_action'] = 'WAIT_CONFIRM'
                card['entry_instruction'] = 'range-бот заблокирован до confirm / reclaim; новый вход не разрешён'
                card['exit_instruction'] = 'без активации до подтверждения'
            else:
                if str(card.get('plan_state') or '').upper() in {'PREPARE', 'CAN ADD', 'SMALL ENTRY', 'AGGRESSIVE ENTRY'}:
                    card['plan_state'] = 'WAIT'
                if str(card.get('management_action') or '').upper() in {'ENABLE / CAN ADD', 'ENABLE SMALL SIZE', 'AGGRESSIVE ENTRY', 'CAN ADD', 'WAIT_EDGE'}:
                    card['management_action'] = 'WAIT_CONFIRM'
                card['entry_instruction'] = 'новый вход заблокирован до confirm; даже small-вход не разрешён'

    if soft_probe_allowed and not no_trade_lock:
        for card in bot_cards:
            bot_key = str(card.get('bot_key') or '')
            if bot_key.startswith('range') or bot_key.endswith('short'):
                if str(card.get('status') or '').upper() == 'OFF':
                    card['status'] = 'SOFT_READY'
                if str(card.get('plan_state') or '').upper() in {'WAIT', 'PREPARE'}:
                    card['plan_state'] = 'READY_SMALL'
                if str(card.get('management_action') or '').upper() in {'WAIT', 'WAIT_CONFIRM', 'WAIT EDGE'}:
                    card['management_action'] = 'ENABLE SMALL SIZE'
                card['small_entry_only'] = True
                card['entry_instruction'] = 'разрешён ранний малый запуск по soft-authorization; без доборов до confirm'

    bot_cards.sort(key=lambda x: (float(x.get("ranking_score") or 0.0), float(x.get("score") or 0.0)), reverse=True)

    best_card = None if no_trade_lock else (bot_cards[0] if bot_cards else None)
    avoid_card = bot_cards[-1] if bot_cards else None
    if best_card is not None:
        best_score = float(best_card.get("score") or 0.0)
        best_rank = float(best_card.get("ranking_score") or best_score)
        if position == "MID" and breakout_risk != "LOW" and best_rank < 0.45:
            best_card = None
        elif hold_bias not in {"long", "short"} and best_rank < 0.50:
            best_card = None
    scalp_candidates = [c for c in bot_cards if _bot_hold_mode(c) == "SCALP ONLY" and float(c.get("score") or 0.0) >= 0.45]
    intraday_candidates = [c for c in bot_cards if _bot_hold_mode(c) == "INTRADAY" and str(c.get("status") or "") in {"READY", "WATCH"}]

    dangerous_bots: List[Dict[str, Any]] = []
    for card in bot_cards:
        score = float(card.get("score") or 0.0)
        reasons: List[str] = []
        if score < 0.45:
            reasons.append("нет edge")
        if breakout_risk == "HIGH" and str(card.get("bot_key") or "").startswith("range"):
            reasons.append("высокий breakout risk")
        if position == "MID":
            reasons.append("цена не у края диапазона")
        if trap_comment and str(card.get("bot_key") or "").startswith("range"):
            reasons.append("ловушечный контекст")
        if reasons:
            dangerous_bots.append({"bot_label": card.get("bot_label"), "reasons": _dedupe(reasons)[:2]})

    execution_bias = "WAIT"
    if scalp_candidates and not intraday_candidates:
        execution_bias = "SCALP ONLY"
    elif intraday_candidates:
        execution_bias = "INTRADAY"
    elif best_card is not None:
        execution_bias = _bot_hold_mode(best_card)

    scalp_bot_label = scalp_candidates[0].get("bot_label") if scalp_candidates else None
    intraday_bot_label = intraday_candidates[0].get("bot_label") if intraday_candidates else None
    avoid_reason_parts: List[str] = []
    if avoid_card is not None:
        if float(avoid_card.get("score") or 0.0) < 0.45:
            avoid_reason_parts.append("сейчас у него слишком слабый edge")
        if breakout_risk == "HIGH" and str(avoid_card.get("bot_key") or "").startswith("range"):
            avoid_reason_parts.append("его часто ломает на повышенном breakout risk")
        if position == "MID":
            avoid_reason_parts.append("в середине диапазона RR для него слабый")
        if trap_comment:
            avoid_reason_parts.append("ловушечный контекст может быстро сломать идею")
    avoid_reason = "; ".join(_dedupe(avoid_reason_parts)[:3]) or "сейчас не даёт понятного преимущества"

    learning_weighted_bots = [c for c in bot_cards if abs(float(c.get("learning_delta") or 0.0)) >= 0.01 or abs(float(c.get("learning_rank_delta") or 0.0)) >= 0.01]
    execution_priority = [c.get("bot_label") for c in bot_cards if float(c.get("ranking_score") or 0.0) >= 0.45][:4]
    matrix_summary: List[str] = []
    soft_candidates = [c for c in bot_cards if not no_trade_lock and (str(c.get("status") or c.get("activation_state") or "").upper() in {"SOFT_READY", "WATCH"} or bool(c.get("small_entry_only")))]
    watchlist_candidates = [c for c in bot_cards if str(c.get("status") or c.get("activation_state") or "").upper() in {"WATCH", "SOFT_READY", "ARMED"}]
    if not no_trade_lock and not soft_candidates and str(analysis.get('range_volume_bot', {}).get('status') or '') in {'READY_SMALL', 'READY_SMALL_REDUCED'}:
        soft_candidates = [c for c in bot_cards if str(c.get('bot_key') or '').startswith('range')] or soft_candidates
    if not watchlist_candidates and str(analysis.get('range_volume_bot', {}).get('status') or '') in {'READY_SMALL', 'READY_SMALL_REDUCED'}:
        watchlist_candidates = [c for c in bot_cards if str(c.get('bot_key') or '').startswith('range')] or watchlist_candidates
    if best_card is not None:
        matrix_summary.append(f"сильный кандидат сейчас: {best_card.get('bot_label')}")
        matrix_summary.append(f"learning-weighted ranking: {best_card.get('bot_label')} | {float(best_card.get('ranking_score') or 0.0) * 100:.1f}%")
    else:
        matrix_summary.append("сильный кандидат сейчас: нет")
    if no_trade_lock:
        matrix_summary.append("мягкий кандидат сейчас: нет")
    elif soft_candidates:
        matrix_summary.append(f"мягкий кандидат сейчас: {soft_candidates[0].get('bot_label')}")
    else:
        matrix_summary.append("мягкий кандидат сейчас: нет")
    if watchlist_candidates:
        matrix_summary.append(f"watchlist: {watchlist_candidates[0].get('bot_label')} (без активации до confirm)")
    else:
        matrix_summary.append("watchlist: нет")
    if intraday_bot_label:
        matrix_summary.append(f"спокойнее всего сейчас выглядит {intraday_bot_label} для intraday-удержания")
    if scalp_bot_label and not no_trade_lock:
        matrix_summary.append(f"только быстрым scalp сейчас выглядит {scalp_bot_label}")
    if avoid_card is not None:
        matrix_summary.append(f"не форсировать сейчас {avoid_card.get('bot_label')}: {avoid_reason}")
    for card in learning_weighted_bots[:2]:
        delta_pct = float(card.get("learning_delta") or 0.0) * 100.0
        sign = "+" if delta_pct >= 0 else ""
        matrix_summary.append(f"слой личного обучения: {card.get('bot_label')} score {sign}{delta_pct:.1f}%")
        rank_pct = float(card.get("learning_rank_delta") or 0.0) * 100.0
        rank_sign = "+" if rank_pct >= 0 else ""
        if abs(rank_pct) >= 1.0:
            matrix_summary.append(f"learning ranking: {card.get('bot_label')} {rank_sign}{rank_pct:.1f}%")

    recommended_sequence: List[str] = []
    if best_card is not None:
        recommended_sequence.append(f"сначала смотреть {best_card.get('bot_label')}: {best_card.get('execution_hint')}")
    else:
        recommended_sequence.append("сейчас нет чистого кандидата: лучше ждать край диапазона или более явный импульс")
    if intraday_bot_label:
        recommended_sequence.append(f"для более спокойного ведения позиции приоритетнее {intraday_bot_label}")
    if scalp_bot_label and scalp_bot_label != intraday_bot_label and not no_trade_lock:
        recommended_sequence.append(f"если рынок нервный, работать только быстрым сценарием через {scalp_bot_label}")

    management_summary: List[str] = []
    range_management: List[str] = []
    ct_management: List[str] = []
    for card in bot_cards:
        label = str(card.get("bot_label") or "бот")
        action = str(card.get("management_action") or "WAIT")
        plan_state = str(card.get("plan_state") or "WAIT")
        if card.get("aggressive_entry_ok"):
            management_summary.append(f"{label}: разрешён более агрессивный вход по подтверждению")
        elif card.get("can_add"):
            management_summary.append(f"{label}: позицию можно добавлять только после удержания рабочей зоны")
        elif card.get("small_entry_only"):
            management_summary.append(f"{label}: вход только небольшой позицией")
        elif action in {"CAUTIOUS EXIT", "CANCEL SCENARIO"}:
            management_summary.append(f"{label}: {action.lower()}")
        if str(card.get("bot_key") or "").startswith("range"):
            range_management.append(f"{label}: {plan_state} / {action} — {card.get('entry_instruction')}")
        else:
            ct_management.append(f"{label}: {plan_state} / {action} — {card.get('entry_instruction')}")

    state_summary: List[str] = []
    active_bots_now: List[str] = []
    manual_summary: List[str] = []
    for card in bot_cards:
        label = str(card.get("bot_label") or "бот")
        phase = str(card.get("manager_phase") or "IDLE")
        size_hint = str(card.get("size_hint") or "NONE")
        adds_used = int(card.get("adds_used") or 0)
        manual = ((card.get("manager_state") or {}).get("manual") or {})
        manual_action = str(manual.get("action") or "").strip()
        if card.get("position_open"):
            active_bots_now.append(label)
        if manual_action:
            manual_summary.append(f"{label}: вручную отмечено -> {manual_action}")
        if phase == "ACTIVE":
            state_summary.append(f"{label}: бот активен, режим {size_hint.lower() if size_hint != 'NONE' else 'base'}")
        elif phase == "ADD_READY":
            state_summary.append(f"{label}: бот уже ведётся, можно добавить (adds used: {adds_used})")
        elif phase == "CAUTIOUS_EXIT":
            state_summary.append(f"{label}: перевести в осторожное сопровождение / частичный выход")
        elif phase == "WAIT_EDGE":
            state_summary.append(f"{label}: был интерес, но сейчас лучше ждать край диапазона")
        elif phase == "WATCH":
            state_summary.append(f"{label}: сценарий собирается, пока без активации")
        elif phase == "CANCELLED":
            state_summary.append(f"{label}: сценарий отменён")

    management_summary = _dedupe(management_summary)[:6]
    range_management = _dedupe(range_management)[:4]
    ct_management = _dedupe(ct_management)[:4]
    state_summary = _dedupe(state_summary)[:6]
    manual_summary = _dedupe(manual_summary)[:6]

    deviation_ladder = _build_deviation_ladder(symbol=symbol, hold_bias=hold_bias, breakout_risk=breakout_risk, preferred_bot=preferred_bot)
    unified_strategy_matrix = _build_unified_strategy_matrix(
        bot_cards,
        deviation_ladder,
        hold_bias,
        str(history_pattern.get("direction") or "NEUTRAL"),
        float(history_pattern.get("confidence") or 0.0),
        spy_ctx,
        reversal_dir,
        reversal_conf,
    )
    overlay_commentary = _build_overlay_commentary(
        hold_bias,
        str(history_pattern.get("direction") or "NEUTRAL"),
        float(history_pattern.get("confidence") or 0.0),
        str(history_pattern.get("summary") or ""),
        spy_ctx,
        list(reversal.get("patterns") or []),
        unified_strategy_matrix,
    )
    size_allocator = _build_size_allocator(unified_strategy_matrix, deviation_ladder, hold_bias, execution_bias)
    unified_strategy_matrix = size_allocator.get("matrix") or unified_strategy_matrix

    if no_trade_lock:
        for item in unified_strategy_matrix:
            activation = str(item.get("activation_state") or item.get("status") or "OFF").upper()
            if activation in {"READY", "SOFT_READY", "ARMED"}:
                item["status"] = "BLOCKED"
                item["activation_state"] = "BLOCKED"
            elif activation == "WATCH":
                item["activation_state"] = "WATCH"
            item["action"] = "WAIT_CONFIRM" if activation in {"READY", "SOFT_READY", "ARMED", "WATCH"} else "OFF"
            comment = str(item.get("comment") or "").strip()
            lock_note = "execution заблокирован truth-lock: до confirm/reclaim новый вход не разрешён"
            item["comment"] = f"{comment}; {lock_note}" if comment else lock_note

    bot_control_center = build_bot_control_center(bot_cards, execution_bias)

    active_best = best_card or {"bot_key": "none", "bot_label": "нет чистого кандидата", "status": "OFF", "score": 0.0}
    if best_card is None:
        unified_advice = (
            f"сейчас ни один бот не имеет чистого edge; "
            f"режим {execution_bias.lower()}; "
            f"re-entry зона: {reentry_zone}"
        )
    else:
        unified_advice = (
            f"лучше всего сейчас смотреть {active_best.get('bot_label')}; "
            f"режим {execution_bias.lower()}; "
            f"re-entry зона: {reentry_zone}"
        )

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "ct_now": ct_now,
        "ginarea_advice": ginarea,
        "unified_advice": unified_advice,
        "trade_style": trade_style,
        "preferred_bot": preferred_bot,
        "hold_bias": hold_bias,
        "scalp_only": scalp_only,
        "confirmation_needed": confirmation_needed,
        "reentry_zone": reentry_zone,
        "invalidation_hint": invalidation_hint,
        "tactical_plan": tactical_plan,
        "bot_cards": bot_cards,
        "best_bot": active_best.get("bot_key"),
        "best_bot_label": active_best.get("bot_label"),
        "best_bot_status": active_best.get("status"),
        "best_bot_score": active_best.get("score"),
        "best_bot_ranking_score": active_best.get("ranking_score"),
        "execution_bias": execution_bias,
        "execution_priority": execution_priority,
        "scalp_bot_label": scalp_bot_label,
        "intraday_bot_label": intraday_bot_label,
        "avoid_bot_label": avoid_card.get("bot_label") if avoid_card else None,
        "avoid_bot_reason": avoid_reason,
        "matrix_summary": matrix_summary,
        "dangerous_bots": dangerous_bots,
        "recommended_sequence": recommended_sequence,
        "management_summary": management_summary,
        "range_management": range_management,
        "ct_management": ct_management,
        "state_summary": state_summary,
        "active_bots_now": active_bots_now,
        "bot_manager_state": manager_state,
        "personal_learning": {
            **learning_summary,
            "execution_weighted_bots": [c.get("bot_label") for c in bot_cards if abs(float(c.get("execution_learning_delta") or 0.0)) >= 0.01],
        },
        "learning_adjustments": learning_adjustments,
        "learning_execution_adjustments": execution_learning,
        "learning_execution_summary": learning_execution_summary[:6],
        "learning_ranking_summary": learning_ranking_summary[:6],
        "bot_control_center": bot_control_center,
        "bot_control_center_summary": bot_control_center.get("summary") or [],
        "learning_weighted_bots": [c.get("bot_label") for c in learning_weighted_bots[:4]],
        "custom_bot_labels": BOT_LABELS,
        "manual_summary": manual_summary,
        "unified_strategy_matrix": unified_strategy_matrix,
        "overlay_commentary": overlay_commentary,
        "primary_bot": size_allocator.get("primary_bot"),
        "secondary_bot": size_allocator.get("secondary_bot"),
        "primary_size_pct": size_allocator.get("primary_size_pct"),
        "secondary_size_pct": size_allocator.get("secondary_size_pct"),
        "size_plan": size_allocator.get("size_plan"),
        "bots_to_reduce": size_allocator.get("bots_to_reduce"),
        "aggression_mode": size_allocator.get("aggression_mode"),
        "spy_context": spy_ctx,
        "history_pattern_direction": history_pattern.get("direction"),
        "history_pattern_confidence": history_pattern.get("confidence"),
        "history_pattern_summary": history_pattern.get("summary"),
        "range_low": round(low, 2),
        "range_mid": round(mid, 2),
        "range_high": round(high, 2),
        "range_state": rng["range_state"],
        "range_position": position,
        "edge_bias": edge_bias,
        "edge_score": round(edge_score, 3),
        "breakout_risk": breakout_risk,
        "reversal_signal": reversal.get("signal"),
        "reversal_direction": reversal_dir,
        "reversal_confidence": reversal_conf,
        "reversal_summary": reversal.get("summary"),
        "reversal_patterns": reversal.get("patterns"),
        "false_break_signal": false_break_signal,
        "trap_comment": trap_comment,
        "deviation_ladder": deviation_ladder,
        "mean60_price": deviation_ladder.get("impulse_base_price"),
        "deviation_pct": deviation_ladder.get("impulse_move_pct"),
        "ladder_action": deviation_ladder.get("ladder_action"),
        "range_bias_action": deviation_ladder.get("range_action"),
        "execution_truth_lock": no_trade_lock,
        "execution_confirm_ready": confirmation_ready,
    }
