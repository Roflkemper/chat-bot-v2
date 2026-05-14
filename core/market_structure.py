from __future__ import annotations

from typing import Any, Dict, Optional

from core.import_compat import normalize_direction, to_float
from core.btc_plan import calc_long_score, calc_short_score, fmt_pct, fmt_price


def analyze_market_structure(data: Dict[str, Any], side: Optional[str] = None, journal: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    price = to_float(data.get("price"))
    low = to_float(data.get("range_low"))
    mid = to_float(data.get("range_mid"))
    high = to_float(data.get("range_high"))
    decision = data.get("decision") or {}
    journal = journal or {}

    decision_direction = str(decision.get("direction") or "").upper()
    if decision_direction not in ("LONG", "SHORT"):
        ls = calc_long_score(data)
        ss = calc_short_score(data)
        if ls >= ss + 0.12:
            decision_direction = "LONG"
        elif ss >= ls + 0.12:
            decision_direction = "SHORT"
        else:
            decision_direction = "NONE"

    requested_side = str(side or "AUTO").upper()
    focus_side = requested_side if requested_side in ("LONG", "SHORT") else decision_direction
    if focus_side not in ("LONG", "SHORT"):
        focus_side = "LONG" if calc_long_score(data) >= calc_short_score(data) else "SHORT"

    zone = "UNKNOWN"
    if price is not None:
        if low is not None and price < low:
            zone = "BELOW_RANGE"
        elif high is not None and price > high:
            zone = "ABOVE_RANGE"
        elif mid is not None:
            if low is not None and price <= (low + mid) / 2:
                zone = "LOWER_HALF"
            elif high is not None and price >= (mid + high) / 2:
                zone = "UPPER_HALF"
            else:
                zone = "MID_ZONE"
        else:
            zone = "IN_RANGE"

    status = "NEUTRAL"
    structure_break = False
    choch_risk = False
    continuation_quality = "MID"
    invalidation_level = None
    next_confirmation = None
    comments = []

    if focus_side == "LONG":
        invalidation_level = low if low is not None else mid if mid is not None else price
        next_confirmation = high if high is not None else mid if mid is not None else price
        if price is None:
            status = "NO_DATA"
            continuation_quality = "UNKNOWN"
            comments.append("не хватает цены, чтобы подтвердить лонг-структуру")
        elif low is not None and price < low:
            status = "BOS_DOWN"
            structure_break = True
            continuation_quality = "LOW"
            comments.append("цена уже ниже range low — лонг-структура сломана")
        elif mid is not None and price < mid:
            status = "CHOCH_RISK"
            choch_risk = True
            continuation_quality = "MID"
            comments.append("цена ушла под range mid — есть риск CHOCH против лонга")
        elif high is not None and price >= high:
            status = "BOS_UP"
            continuation_quality = "HIGH"
            comments.append("цена держится у/выше range high — есть продолжение вверх")
        else:
            status = "HOLDING_UP"
            continuation_quality = "GOOD"
            comments.append("лонг-структура пока держится выше ключевой середины")
    else:
        invalidation_level = high if high is not None else mid if mid is not None else price
        next_confirmation = low if low is not None else mid if mid is not None else price
        if price is None:
            status = "NO_DATA"
            continuation_quality = "UNKNOWN"
            comments.append("не хватает цены, чтобы подтвердить шорт-структуру")
        elif high is not None and price > high:
            status = "BOS_UP"
            structure_break = True
            continuation_quality = "LOW"
            comments.append("цена уже выше range high — шорт-структура сломана")
        elif mid is not None and price > mid:
            status = "CHOCH_RISK"
            choch_risk = True
            continuation_quality = "MID"
            comments.append("цена ушла выше range mid — есть риск CHOCH против шорта")
        elif low is not None and price <= low:
            status = "BOS_DOWN"
            continuation_quality = "HIGH"
            comments.append("цена держится у/ниже range low — есть продолжение вниз")
        else:
            status = "HOLDING_DOWN"
            continuation_quality = "GOOD"
            comments.append("шорт-структура пока держится ниже ключевой середины")

    long_score = calc_long_score(data)
    short_score = calc_short_score(data)
    score_gap = abs(long_score - short_score)
    if score_gap < 0.08 and continuation_quality != "LOW":
        comments.append("перевес по скорингу не очень большой — структура есть, но без сильного доминирования")
    if journal.get("trade_id") and journal.get("side"):
        entry_side = str(journal.get("side") or "").upper()
        if entry_side in ("LONG", "SHORT") and entry_side != focus_side:
            comments.append("текущая структура уже не совпадает со стороной последней сделки")

    bias = "LONG" if long_score > short_score else "SHORT" if short_score > long_score else "NONE"
    return {
        "focus_side": focus_side,
        "bias": bias,
        "status": status,
        "zone": zone,
        "structure_break": structure_break,
        "choch_risk": choch_risk,
        "continuation_quality": continuation_quality,
        "invalidation_level": invalidation_level,
        "next_confirmation": next_confirmation,
        "comments": comments,
        "decision_direction": decision_direction,
        "decision_action": str(decision.get("action") or "WAIT").upper(),
        "decision_mode": str(decision.get("mode") or "MIXED").upper(),
        "decision_risk": str(decision.get("risk_level") or "HIGH").upper(),
        "decision_confidence_pct": float(decision.get("confidence_pct") or 0.0),
        "long_score": long_score,
        "short_score": short_score,
    }


def build_btc_structure_text(data: Dict[str, Any], side: str = "AUTO", journal: Optional[Dict[str, Any]] = None) -> str:
    timeframe = data.get("timeframe", "1h")
    snap = analyze_market_structure(data, side=side, journal=journal)
    lines = [
        f"🏗 BTC STRUCTURE [{timeframe}]",
        "",
        f"Focus side: {snap['focus_side']}",
        f"Structure status: {snap['status']}",
        f"Continuation quality: {snap['continuation_quality']}",
        f"Zone now: {snap['zone']}",
        f"Structure break: {'да' if snap['structure_break'] else 'нет'}",
        f"CHOCH risk: {'да' if snap['choch_risk'] else 'нет'}",
        "",
        "Ключевые уровни:",
        f"• price: {fmt_price(data.get('price'))}",
        f"• range low: {fmt_price(data.get('range_low'))}",
        f"• range mid: {fmt_price(data.get('range_mid'))}",
        f"• range high: {fmt_price(data.get('range_high'))}",
        f"• invalidation level: {fmt_price(snap.get('invalidation_level'))}",
        f"• next confirmation: {fmt_price(snap.get('next_confirmation'))}",
        "",
        "Почему это важно сейчас:",
    ]
    for item in (snap.get('comments') or [])[:5]:
        lines.append(f"• {item}")
    lines.extend([
        "",
        "Decision + scores:",
        f"• decision direction: {normalize_direction((data.get('decision') or {}).get('direction_text') or snap.get('decision_direction'))}",
        f"• decision action: {(data.get('decision') or {}).get('action_text') or snap.get('decision_action') or 'WAIT'}",
        f"• decision mode: {snap.get('decision_mode')}",
        f"• decision risk: {snap.get('decision_risk')}",
        f"• decision confidence: {round(snap.get('decision_confidence_pct') or 0.0, 1)}%",
        f"• long score: {fmt_pct(snap.get('long_score'))}",
        f"• short score: {fmt_pct(snap.get('short_score'))}",
        "",
        "Логика v8.4:",
        "• BOS_UP / BOS_DOWN — структура реально пробила границу диапазона",
        "• CHOCH_RISK — рынок зашёл за середину range против твоей стороны",
        "• HOLDING_UP / HOLDING_DOWN — базовая структура пока держится",
    ])
    return "\n".join(lines)


__all__ = ["analyze_market_structure", "build_btc_structure_text"]