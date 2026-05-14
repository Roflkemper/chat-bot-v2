from __future__ import annotations

from typing import Any, Dict


def _f(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        if isinstance(v, str):
            v = v.replace(" ", "").replace(",", "")
        return float(v)
    except Exception:
        return default


def _s(v: Any, default: str = "") -> str:
    try:
        if v is None:
            return default
        return str(v).strip()
    except Exception:
        return default


def _u(v: Any, default: str = "") -> str:
    return _s(v, default).upper()


def _direction_from_decision(decision: Dict[str, Any], payload: Dict[str, Any]) -> str:
    raw = _u(
        decision.get("direction_text")
        or decision.get("direction")
        or payload.get("final_decision")
        or payload.get("forecast_direction")
        or "NEUTRAL"
    )
    if "LONG" in raw or "ЛОНГ" in raw or raw in {"UP", "BULL", "BULLISH"}:
        return "LONG"
    if "SHORT" in raw or "ШОРТ" in raw or raw in {"DOWN", "BEAR", "BEARISH"}:
        return "SHORT"
    return "NEUTRAL"


def _location_state(payload: Dict[str, Any], decision: Dict[str, Any]) -> str:
    direct = _u(
        decision.get("location_state")
        or decision.get("range_position")
        or ((decision.get("range_bot_permission") or {}).get("entry_location") if isinstance(decision.get("range_bot_permission"), dict) else None)
        or payload.get("location_state")
        or payload.get("range_position")
        or ((payload.get("liquidity_lite") or {}).get("location") if isinstance(payload.get("liquidity_lite"), dict) else None)
    )

    aliases = {
        "UPPER_EDGE": "EDGE_HIGH",
        "LOWER_EDGE": "EDGE_LOW",
        "UPPER": "HIGH",
        "LOWER": "LOW",
        "UPPER_PART": "HIGH",
        "LOWER_PART": "LOW",
    }
    if direct in aliases:
        return aliases[direct]

    if direct in {"LOW", "MID", "HIGH", "EDGE_LOW", "EDGE_HIGH"}:
        return direct

    price = _f(payload.get("price") or payload.get("last_price") or payload.get("close"))
    low = _f(payload.get("range_low"))
    high = _f(payload.get("range_high"))

    if price <= 0 or high <= low:
        return "UNKNOWN"

    width = high - low
    pos = (price - low) / width

    if pos <= 0.18:
        return "EDGE_LOW"
    if pos <= 0.40:
        return "LOW"
    if pos >= 0.82:
        return "EDGE_HIGH"
    if pos >= 0.60:
        return "HIGH"
    return "MID"
def _fade_quality(payload: Dict[str, Any], decision: Dict[str, Any]) -> str:
    direct = _u(payload.get("post_impulse_fade") or payload.get("fade_quality") or decision.get("fade_quality"))
    if direct in {"NONE", "PARTIAL", "GOOD", "STRONG", "YES", "NO"}:
        if direct == 'YES':
            return 'GOOD'
        if direct == 'NO':
            return 'NONE'
        return direct
    impulse_state = _u(decision.get("impulse_state") or payload.get("impulse_state"))
    trap_risk = _u(decision.get("trap_risk") or payload.get("trap_risk"))
    if impulse_state in {"FADING", "WEAK", "DECAY", 'NO_CLEAR_IMPULSE'}:
        return "GOOD"
    if trap_risk == "HIGH":
        return "PARTIAL"
    return "NONE"


def _continuation_risk(payload: Dict[str, Any], decision: Dict[str, Any], fast_move: Dict[str, Any]) -> str:
    direct = _u(decision.get("continuation_risk") or payload.get("continuation_risk") or fast_move.get("continuation_risk"))
    if direct in {"LOW", "MEDIUM", "HIGH", "EXTREME"}:
        return direct
    cls = _u(fast_move.get("classification"))
    if cls in {"CONTINUATION_UP", "CONTINUATION_DOWN"}:
        return "HIGH"
    if cls in {"WEAK_CONTINUATION_UP", "WEAK_CONTINUATION_DOWN"}:
        return "MEDIUM"
    return "LOW"


def _regime(payload: Dict[str, Any], decision: Dict[str, Any]) -> str:
    regime = _u(
        decision.get("market_mode")
        or decision.get("mode")
        or decision.get("regime")
        or payload.get("market_mode")
        or payload.get("regime")
        or (payload.get("regime_v2") or {}).get("regime")
        or "UNKNOWN"
    )
    if "RANGE" in regime:
        return "RANGE"
    if "TREND" in regime:
        return "TREND"
    if "MIXED" in regime:
        return "MIXED"
    return "UNKNOWN"


def build_move_type_context(payload: Dict[str, Any], decision: Dict[str, Any]) -> Dict[str, Any]:
    fast_move = payload.get("fast_move_context") if isinstance(payload.get("fast_move_context"), dict) else {}
    fake_move = decision.get("fake_move_detector") if isinstance(decision.get("fake_move_detector"), dict) else (payload.get("fake_move_detector") if isinstance(payload.get("fake_move_detector"), dict) else {})
    regime_v2 = payload.get("regime_v2") if isinstance(payload.get("regime_v2"), dict) else {}

    regime = _regime(payload, decision)
    location_state = _location_state(payload, decision)
    fade_quality = _fade_quality(payload, decision)
    continuation_risk = _continuation_risk(payload, decision, fast_move)
    fast_cls = _u(fast_move.get("classification"))
    fake_type = _u(fake_move.get("type"))
    trap_risk = _u(decision.get("trap_risk") or payload.get("trap_risk"))
    base_bias = _direction_from_decision(decision, payload)

    move_type = "NO_CLEAR_MOVE"
    bias = base_bias
    summary = "движение не даёт чистого преимущества"
    implication = "лучше ждать край диапазона или новый импульс"
    range_rotation_ready = False
    fake_break_side = None
    invalidation_hint = "подтверждённый выход и удержание за ключевой границей"
    confidence = _f(fake_move.get("confidence") or fast_move.get("confidence") or 0.0)

    if fake_type == "FAKE_UP" or fast_cls == "LIKELY_FAKE_UP":
        move_type = "FAKE_BREAK_UP"
        bias = "SHORT"
        fake_break_side = "SHORT"
        summary = "вынос вверх больше похож на ложный, чем на устойчивое продолжение"
        implication = "контртренд short смотреть только после возврата под зону выноса"
        range_rotation_ready = regime == "RANGE" and location_state in {"HIGH", "EDGE_HIGH"}
        invalidation_hint = "если цена удержится выше зоны выноса и получит acceptance вверх"
    elif fake_type == "FAKE_DOWN" or fast_cls == "LIKELY_FAKE_DOWN":
        move_type = "FAKE_BREAK_DOWN"
        bias = "LONG"
        fake_break_side = "LONG"
        summary = "пролив вниз больше похож на ложный, чем на устойчивое продолжение"
        implication = "контртренд long смотреть только после reclaim выше зоны пролива"
        range_rotation_ready = regime == "RANGE" and location_state in {"LOW", "EDGE_LOW"}
        invalidation_hint = "если цена удержится ниже зоны пролива и получит acceptance вниз"
    elif fast_cls == "CONTINUATION_UP":
        move_type = "IMPULSE_CONTINUATION_UP"
        bias = "LONG"
        summary = "движение вверх пока выглядит как реальное продолжение"
        implication = "шорты не форсировать, long — только на retest / удержании"
        invalidation_hint = "потеря удержания пробоя и быстрый возврат в диапазон"
    elif fast_cls == "CONTINUATION_DOWN":
        move_type = "IMPULSE_CONTINUATION_DOWN"
        bias = "SHORT"
        summary = "движение вниз пока выглядит как реальное продолжение"
        implication = "лонги не форсировать, short — только на retest / удержании"
        invalidation_hint = "неудача удержать слабость и быстрый reclaim вверх"
    elif fast_cls == "WEAK_CONTINUATION_UP":
        if trap_risk == "HIGH" or fade_quality in {"GOOD", "STRONG"}:
            move_type = "EXHAUSTION_UP"
            bias = "NEUTRAL"
            summary = "движение вверх слабеет: есть признаки выдоха"
            implication = "не догонять; ждать либо retest continuation, либо слабость для возврата"
        else:
            move_type = "NO_CLEAR_MOVE"
            bias = "LONG"
            summary = "есть мягкое продолжение вверх, но без чистого входа"
            implication = "long только на откате; из середины не лезть"
    elif fast_cls == "WEAK_CONTINUATION_DOWN":
        if trap_risk == "HIGH" or fade_quality in {"GOOD", "STRONG"}:
            move_type = "EXHAUSTION_DOWN"
            bias = "NEUTRAL"
            summary = "движение вниз слабеет: есть признаки выдоха"
            implication = "не догонять; ждать либо retest continuation, либо reclaim для возврата"
        else:
            move_type = "NO_CLEAR_MOVE"
            bias = "SHORT"
            summary = "есть мягкое продолжение вниз, но без чистого входа"
            implication = "short только на retest; из середины не лезть"
    elif regime == "RANGE":
        if location_state in {"EDGE_HIGH", "HIGH"} and fade_quality in {"GOOD", "PARTIAL", "STRONG"}:
            move_type = "RANGE_ROTATION"
            bias = "SHORT"
            summary = "рынок вращается внутри диапазона; сверху возможна ротация вниз"
            implication = "short-сценарий смотреть только от верхней части диапазона"
            range_rotation_ready = True
            invalidation_hint = "удержание выше high диапазона"
        elif location_state in {"EDGE_LOW", "LOW"} and fade_quality in {"GOOD", "PARTIAL", "STRONG"}:
            move_type = "RANGE_ROTATION"
            bias = "LONG"
            summary = "рынок вращается внутри диапазона; снизу возможна ротация вверх"
            implication = "long-сценарий смотреть только от нижней части диапазона"
            range_rotation_ready = True
            invalidation_hint = "удержание ниже low диапазона"
        elif location_state == "MID":
            move_type = "RANGE_ROTATION_PENDING"
            bias = "NEUTRAL"
            summary = "рынок остаётся в диапазоне, но цена сейчас в середине шума"
            implication = "range-логика допустима, но новый вход из середины не форсировать"
            invalidation_hint = "пробой и удержание за границей диапазона"
        else:
            move_type = "NO_CLEAR_MOVE"
            bias = "NEUTRAL"
            summary = "range есть, но локация и структура пока не дают чистого сценария"
            implication = "ждать край диапазона или возврат после выноса"
    elif _u(regime_v2.get("state")) == "COMPRESSION":
        move_type = "NO_CLEAR_MOVE"
        bias = "NEUTRAL"
        summary = "рынок сжат, но подтверждения направления нет"
        implication = "из середины не входить; ждать вынос и оценку acceptance"

    return {
        "type": move_type,
        "bias": bias,
        "summary": summary,
        "implication": implication,
        "location_state": location_state,
        "continuation_risk": continuation_risk,
        "fade_quality": fade_quality,
        "range_rotation_ready": range_rotation_ready,
        "fake_break_side": fake_break_side,
        "invalidation_hint": invalidation_hint,
        "regime": regime,
        "trap_risk": trap_risk or "UNKNOWN",
        "confidence": round(confidence, 1),
    }


__all__ = ["build_move_type_context"]
