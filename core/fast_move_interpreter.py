from __future__ import annotations

from typing import Any, Dict


def _f(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _s(v: Any, default: str = "") -> str:
    return str(v or default)


def build_fast_move_context(liquidity: Dict[str, Any], orderflow: Dict[str, Any], volatility: Dict[str, Any], micro: Dict[str, Any], current_price: float = 0.0, liquidation: Dict[str, Any] | None = None) -> Dict[str, Any]:
    liquidity = liquidity or {}
    orderflow = orderflow or {}
    volatility = volatility or {}
    micro = micro or {}
    liquidation = liquidation or {}

    liq_state = _s(liquidity.get("liquidity_state"), "NEUTRAL").upper()
    liq_magnet = _s(liquidity.get("magnet_side"), "NEUTRAL").upper()
    cascade_risk = _s(liquidity.get("cascade_risk"), "LOW").upper()

    of_bias = _s(orderflow.get("bias"), "NEUTRAL").upper()
    absorb_hi = bool(orderflow.get("absorption_at_high"))
    absorb_lo = bool(orderflow.get("absorption_at_low"))
    exhaust_up = bool(orderflow.get("exhaustion_up"))
    exhaust_down = bool(orderflow.get("exhaustion_down"))

    impulse_state = _s(volatility.get("impulse_state"), "NO_CLEAR_IMPULSE").upper()
    impulse_strength = _s(volatility.get("impulse_strength"), "LOW").upper()
    countertrend_risk = _s(volatility.get("countertrend_risk"), "LOW").upper()

    micro_bias = _s(micro.get("micro_bias"), "NEUTRAL").upper()
    compression = bool(micro.get("compression"))

    real_liq_state = _s(liquidation.get("liquidity_state"), "NEUTRAL").upper()
    real_magnet = _s(liquidation.get("magnet_side"), "NEUTRAL").upper()
    recent_events = int(_f(liquidation.get("recent_liquidation_events"), 0))
    recent_notional = _f(liquidation.get("recent_liquidation_notional_usd"), 0.0)
    price_oi_regime = _s(liquidation.get("price_oi_regime"), "NEUTRAL").upper()
    feed_ok = bool(liquidation.get("heatmap_ready") or liquidation.get("events_count") or liquidation.get("ok") or liquidation.get("fallback_active"))
    feed_health = _s(liquidation.get("feed_health"), "").upper()
    fallback_active = bool(liquidation.get("fallback_active"))
    soft_feed_ok = feed_ok and (fallback_active or feed_health in {"LIVE", "METRICS_ONLY", "DEGRADED", ""})

    if real_liq_state != 'NEUTRAL':
        liq_state = real_liq_state
    if real_magnet != 'NEUTRAL':
        liq_magnet = real_magnet

    classification = "BALANCED"
    direction = "NEUTRAL"
    confidence = 48.0
    summary = "характер движения пока смешанный"
    action = "ждать подтверждение"
    long_action = "лонги без агрессивных добавлений"
    short_action = "шорты без агрессивных добавлений"
    watch = "наблюдаю дальше, дам сигнал когда характер движения изменится"
    continuation_target = "нет данных"
    acceptance_state = "UNDEFINED"
    tactical_plan = "ждать реакцию на ближайшей зоне"

    if liq_state == "BUY_SIDE_SWEEP_REJECTED" or (liq_magnet == "UP" and (absorb_hi or exhaust_up) and micro_bias != "LONG"):
        classification = "LIKELY_FAKE_UP"
        direction = "UP_TRAP"
        confidence = 68.0 if liq_state == "BUY_SIDE_SWEEP_REJECTED" else 61.0
        summary = "вынос вверх похож на ложный: сверху сняли ликвидность, но принятие цены слабое"
        action = "шорт можно пробовать только после слабой реакции / возврата ниже зоны выноса"
        long_action = "лонги в зоне выноса лучше частично фиксировать"
        short_action = "шорты не форсировать в догонку; ждать подтверждение слабости"
        watch = "смотрю возврат под high выноса и слабую реакцию покупателя"
        continuation_target = "возврат к середине диапазона / ближайшей поддержке"
        acceptance_state = "FAILED_UP_ACCEPTANCE"
        tactical_plan = "fade вверх только после возврата под зону выноса"
    elif liq_state == "SELL_SIDE_SWEEP_REJECTED" or (liq_magnet == "DOWN" and (absorb_lo or exhaust_down) and micro_bias != "SHORT"):
        classification = "LIKELY_FAKE_DOWN"
        direction = "DOWN_TRAP"
        confidence = 68.0 if liq_state == "SELL_SIDE_SWEEP_REJECTED" else 61.0
        summary = "пролив вниз похож на ложный: снизу сняли ликвидность, но принятие цены слабое"
        action = "лонг можно пробовать только после возврата выше зоны пролива / reclaim"
        long_action = "лонги только после подтверждения возврата"
        short_action = "шорты в зоне пролива лучше частично фиксировать"
        watch = "смотрю reclaim выше low пролива и удержание возврата"
        continuation_target = "возврат к середине диапазона / ближайшему сопротивлению"
        acceptance_state = "FAILED_DOWN_ACCEPTANCE"
        tactical_plan = "fade вниз только после reclaim обратно в диапазон"
    elif feed_ok and recent_events >= 3 and recent_notional > 0 and price_oi_regime == "UP_OI_UP" and liq_magnet == "UP" and not absorb_hi:
        classification = "CONTINUATION_UP"
        direction = "UP"
        confidence = 66.0 if impulse_strength == "HIGH" else 63.0
        summary = "идёт реальный поток ликвидаций и OI растёт вместе с ценой: движение вверх пока больше похоже на продолжение"
        action = "шорты лучше не усреднять против импульса; ждать выдоха или нового теста"
        long_action = "лонги можно удерживать частично до следующей верхней зоны"
        short_action = "контртренд шорт только после явного выдоха"
        watch = "смотрю, удерживают ли пробой и остаётся ли OI поддерживающим"
        continuation_target = "верхняя зона ликвидности / следующий кластер выше"
        acceptance_state = "UP_ACCEPTANCE_CONFIRMED"
        tactical_plan = "continuation вверх, но без догоняющего входа"
    elif feed_ok and recent_events >= 3 and recent_notional > 0 and price_oi_regime == "DOWN_OI_UP" and liq_magnet == "DOWN" and not absorb_lo:
        classification = "CONTINUATION_DOWN"
        direction = "DOWN"
        confidence = 66.0 if impulse_strength == "HIGH" else 63.0
        summary = "идёт реальный поток ликвидаций и OI растёт вместе с падением: движение вниз пока больше похоже на продолжение"
        action = "лонги лучше не усреднять против импульса; ждать выдоха или нового теста"
        long_action = "контртренд лонг только после явного выдоха"
        short_action = "шорты можно удерживать частично до следующей нижней зоны"
        watch = "смотрю, удерживают ли продавцы пробитую зону"
        continuation_target = "нижняя зона ликвидности / следующий кластер ниже"
        acceptance_state = "DOWN_ACCEPTANCE_CONFIRMED"
        tactical_plan = "continuation вниз, но без агрессивного добора в догонку"
    elif ((liq_magnet == "UP" and of_bias in {"LONG","BUYER","UP"}) or (micro_bias == "LONG" and impulse_strength in {"HIGH","MODERATE"})) and not absorb_hi and countertrend_risk != "HIGH":
        classification = "CONTINUATION_UP"
        direction = "UP"
        confidence = 63.0 if impulse_strength == "HIGH" else 57.0
        summary = "движение вверх больше похоже на продолжение, а не на ложный вынос"
        action = "шорты лучше прикрывать; контртренд против движения пока слабый"
        long_action = "лонги можно держать частично, но следить за признаками выдоха"
        short_action = "шорты сокращать / не добавлять"
        watch = "смотрю retest и качество удержания пробоя"
        continuation_target = "следующая верхняя зона ликвидности"
        acceptance_state = "UP_ACCEPTANCE_PROBING"
        tactical_plan = "приоритет continuation вверх, вход только на retest"
    elif ((liq_magnet == "DOWN" and of_bias in {"SHORT","SELLER","DOWN"}) or (micro_bias == "SHORT" and impulse_strength in {"HIGH","MODERATE"})) and not absorb_lo and countertrend_risk != "HIGH":
        classification = "CONTINUATION_DOWN"
        direction = "DOWN"
        confidence = 63.0 if impulse_strength == "HIGH" else 57.0
        summary = "движение вниз больше похоже на продолжение, а не на ложный пролив"
        action = "лонги лучше прикрывать; контртренд против движения пока слабый"
        long_action = "лонги сокращать / не добавлять"
        short_action = "шорты можно держать частично, но следить за признаками выдоха"
        watch = "смотрю retest снизу и качество удержания слабости"
        continuation_target = "следующая нижняя зона ликвидности"
        acceptance_state = "DOWN_ACCEPTANCE_PROBING"
        tactical_plan = "приоритет continuation вниз, вход только на retest"
    elif feed_ok and recent_events >= 2 and recent_notional > 0 and liq_magnet == "UP" and (absorb_hi or exhaust_up) and price_oi_regime in {"UP_OI_DOWN", "UP_OI_FLAT", "NEUTRAL"}:
        classification = "LIKELY_FAKE_UP"
        direction = "UP_TRAP"
        confidence = 69.0
        summary = "сверху прошёл вынос с ликвидациями, но OI не подтверждает устойчивое продолжение — есть риск ложного движения вверх"
        action = "шорт смотреть только после возврата ниже зоны выноса / слабой реакции"
        long_action = "лонги в зоне выноса лучше частично фиксировать"
        short_action = "не шортить в догонку; ждать слабость и возврат"
        watch = "смотрю отказ от удержания верхней зоны после снятия ликвидности"
        continuation_target = "возврат к середине диапазона / ближайшей поддержке"
        acceptance_state = "FAILED_UP_ACCEPTANCE"
        tactical_plan = "ловушка вверх после ликвидаций, нужен возврат под зону"
    elif feed_ok and recent_events >= 2 and recent_notional > 0 and liq_magnet == "DOWN" and (absorb_lo or exhaust_down) and price_oi_regime in {"DOWN_OI_DOWN", "DOWN_OI_FLAT", "NEUTRAL"}:
        classification = "LIKELY_FAKE_DOWN"
        direction = "DOWN_TRAP"
        confidence = 69.0
        summary = "снизу прошёл пролив с ликвидациями, но OI не подтверждает устойчивое продолжение — есть риск ложного движения вниз"
        action = "лонг смотреть только после reclaim / возврата выше зоны пролива"
        long_action = "лонги только после возврата и подтверждения"
        short_action = "шорты в зоне пролива лучше частично фиксировать"
        watch = "смотрю reclaim обратно в диапазон после снятия нижней ликвидности"
        continuation_target = "возврат к середине диапазона / ближайшему сопротивлению"
        acceptance_state = "FAILED_DOWN_ACCEPTANCE"
        tactical_plan = "ловушка вниз после ликвидаций, нужен reclaim"
    elif soft_feed_ok and liq_magnet == "UP" and (absorb_hi or exhaust_up or cascade_risk == "HIGH") and price_oi_regime in {"UP_OI_DOWN", "UP_OI_FLAT", "NEUTRAL"}:
        classification = "EARLY_FAKE_UP_RISK"
        direction = "UP_TRAP_RISK"
        confidence = 57.0 if fallback_active else 59.0
        summary = "сверху есть ранние признаки ложного выноса: принятие цены слабое, OI не подтверждает уверенное продолжение"
        action = "не шортить в догонку; ждать возврат под локальный high / слабую реакцию продавца"
        long_action = "лонги часть можно защитить или частично фиксировать у выноса"
        short_action = "ранний шорт только после подтверждения слабости"
        watch = "смотрю, останется ли цена над выносом или быстро вернётся обратно"
        continuation_target = "возврат к середине диапазона / ближайшей поддержке"
        acceptance_state = "UP_ACCEPTANCE_AT_RISK"
        tactical_plan = "ранний риск fake up, подтверждение важнее идеи"
    elif soft_feed_ok and liq_magnet == "DOWN" and (absorb_lo or exhaust_down or cascade_risk == "HIGH") and price_oi_regime in {"DOWN_OI_DOWN", "DOWN_OI_FLAT", "NEUTRAL"}:
        classification = "EARLY_FAKE_DOWN_RISK"
        direction = "DOWN_TRAP_RISK"
        confidence = 57.0 if fallback_active else 59.0
        summary = "снизу есть ранние признаки ложного пролива: продавец давит, но OI и принятие цены не дают чистого продолжения"
        action = "не ловить нож; ждать reclaim выше локального low / возврат в диапазон"
        long_action = "ранний лонг только после возврата и удержания"
        short_action = "шорты часть можно фиксировать у пролива"
        watch = "смотрю, появится ли быстрый возврат обратно в диапазон"
        continuation_target = "возврат к середине диапазона / ближайшему сопротивлению"
        acceptance_state = "DOWN_ACCEPTANCE_AT_RISK"
        tactical_plan = "ранний риск fake down, нужен reclaim"
    elif soft_feed_ok and liq_magnet == "UP" and price_oi_regime in {"UP_OI_UP", "UP_OI_FLAT"} and of_bias in {"LONG","BUYER","UP"} and not absorb_hi:
        classification = "WEAK_CONTINUATION_UP"
        direction = "UP"
        confidence = 56.0
        summary = "есть мягкое продолжение вверх, но без права агрессивно заходить из середины диапазона"
        action = "шорты не добавлять; лонг смотреть только на откате или retest"
        long_action = "лонги держать умеренно, без агрессивных добавлений"
        short_action = "контртренд шорт пока слабый"
        watch = "смотрю ретест и неудачу продавца остановить движение"
        continuation_target = "верхняя реакционная зона / локальный high"
        acceptance_state = "UP_ACCEPTANCE_PROBING"
        tactical_plan = "слабое continuation вверх, только аккуратный retest"
    elif soft_feed_ok and liq_magnet == "DOWN" and price_oi_regime in {"DOWN_OI_UP", "DOWN_OI_FLAT"} and of_bias in {"SHORT","SELLER","DOWN"} and not absorb_lo:
        classification = "WEAK_CONTINUATION_DOWN"
        direction = "DOWN"
        confidence = 56.0
        summary = "есть мягкое продолжение вниз, но без права агрессивно входить из середины диапазона"
        action = "лонги не добавлять; шорт смотреть только на retest / слабом откате"
        long_action = "контртренд лонг пока слабый"
        short_action = "шорты держать умеренно, без агрессивных добавлений"
        watch = "смотрю ретест снизу и провал reclaim"
        continuation_target = "нижняя реакционная зона / локальный low"
        acceptance_state = "DOWN_ACCEPTANCE_PROBING"
        tactical_plan = "слабое continuation вниз, только аккуратный retest"
    elif compression and impulse_state == "NO_CLEAR_IMPULSE":
        classification = "SQUEEZE_WITHOUT_CONFIRMATION"
        direction = "NEUTRAL"
        confidence = 55.0
        summary = "рынок сжат, но подтверждённого продолжения пока нет — возможен резкий вынос в обе стороны"
        action = "из середины не входить; ждать вынос и оценку принятия цены"
        watch = "наблюдаю за первым выносом и дам сигнал, ложный он или настоящий"
        acceptance_state = "UNDEFINED"
        tactical_plan = "до выноса приоритет wait"
    elif countertrend_risk == "HIGH" and (exhaust_up or exhaust_down):
        classification = "POST_LIQUIDATION_EXHAUSTION"
        direction = "NEUTRAL"
        confidence = 58.0
        summary = "после быстрого движения видны признаки выдоха; продолжение уже не выглядит чистым"
        action = "фиксировать часть по ходу и не догонять движение без нового подтверждения"
        watch = "наблюдаю, выдох перейдёт в разворот или в проторговку"
        acceptance_state = "EXHAUSTION"
        tactical_plan = "после выноса приоритет reduce / wait"

    alert = "явного live-алерта пока нет"
    if classification == "LIKELY_FAKE_UP":
        alert = "вынос похож на ложный (вверх): лонги часть фиксируем, шорт смотрим только после слабой реакции"
    elif classification == "LIKELY_FAKE_DOWN":
        alert = "пролив похож на ложный (вниз): шорты часть фиксируем, лонг смотрим только после возврата"
    elif classification == "CONTINUATION_UP":
        alert = "движение вверх не выглядит ложным: шорты лучше прикрывать, наблюдаю дальше до смены характера"
    elif classification == "CONTINUATION_DOWN":
        alert = "движение вниз не выглядит ложным: лонги лучше прикрывать, наблюдаю дальше до смены характера"
    elif classification == "EARLY_FAKE_UP_RISK":
        alert = "ранний риск ложного выноса вверх: шорт только после возврата под локальный high"
    elif classification == "EARLY_FAKE_DOWN_RISK":
        alert = "ранний риск ложного пролива вниз: лонг только после reclaim выше локального low"
    elif classification == "WEAK_CONTINUATION_UP":
        alert = "есть слабое продолжение вверх: шорты не добавлять, вход в лонг только на retest"
    elif classification == "WEAK_CONTINUATION_DOWN":
        alert = "есть слабое продолжение вниз: лонги не добавлять, шорт только на retest"
    elif classification == "POST_LIQUIDATION_EXHAUSTION":
        alert = "после выноса виден выдох: часть можно фиксировать, дальше смотрим на характер удержания"

    return {
        "classification": classification,
        "direction": direction,
        "confidence": round(confidence, 1),
        "summary": summary,
        "action": action,
        "long_action": long_action,
        "short_action": short_action,
        "watch_text": watch,
        "continuation_target": continuation_target,
        "alert_text": alert,
        "real_feed_ok": feed_ok,
        "recent_liquidation_events": recent_events,
        "recent_liquidation_notional_usd": round(recent_notional, 2),
        "price_oi_regime": price_oi_regime,
        "acceptance_state": acceptance_state,
        "tactical_plan": tactical_plan,
    }
