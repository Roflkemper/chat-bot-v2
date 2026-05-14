from __future__ import annotations

from typing import Any, Dict, Tuple
import time

from core.data_loader import load_klines
from core.pattern_memory import analyze_history_pattern
from core.v13_trade_fix import build_v13_trade_fix_context


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        if isinstance(value, bool):
            return float(value)
        if isinstance(value, (int, float)):
            return float(value)
        s = str(value).strip().replace('%', '').replace(',', '.')
        if not s:
            return default
        return float(s)
    except Exception:
        return default


def _s(value: Any, default: str = '') -> str:
    try:
        if value is None:
            return default
        return str(value).strip()
    except Exception:
        return default


def _upper(value: Any, default: str = '') -> str:
    return _s(value, default).upper()


def _norm_pct(value: Any, default: float = 0.0) -> float:
    x = _f(value, default)
    if 0.0 <= x <= 1.0:
        x *= 100.0
    return max(0.0, min(100.0, x))


def _zone_icon(zone: str) -> str:
    zone = _upper(zone)
    return {
        'LONG_ZONE': '🟢 LONG-ZONE',
        'SHORT_ZONE': '🔴 SHORT-ZONE',
        'NO_TRADE_MID': '⚪ MID',
    }.get(zone, '⚪ OUTSIDE')


def _entry_icon(state: str) -> str:
    state = _upper(state)
    return {
        'ACTIVE': '🟢 ACTIVE',
        'READY': '🟡 READY',
        'WATCH': '🟠 WATCH',
    }.get(state, '⚪ NOT_READY')


def _confirm_icon(state: str) -> str:
    state = _upper(state)
    return {
        'CONFIRMED': '✅ CONFIRM',
        'EARLY': '🟡 EARLY',
    }.get(state, '⚪ NO-CONFIRM')


def _impulse_icon(label: str) -> str:
    label = _upper(label)
    return {
        'STRONG': '⚡ STRONG',
        'ACTIVE': '⚡ ACTIVE',
        'WEAK': '⚡ WEAK',
    }.get(label, '⚡ DEAD')


_HISTORY_CACHE: Dict[Tuple[str, str], Tuple[float, Dict[str, Any]]] = {}
_HISTORY_TTL_SECONDS = 90.0


def _infer_symbol(payload: Dict[str, Any]) -> str:
    return _s(payload.get('symbol') or payload.get('ticker') or payload.get('instrument') or 'BTCUSDT', 'BTCUSDT').upper()


def _history_for_tf(symbol: str, timeframe: str) -> Dict[str, Any]:
    key = (symbol.upper(), timeframe)
    now = time.time()
    cached = _HISTORY_CACHE.get(key)
    if cached and (now - cached[0]) <= _HISTORY_TTL_SECONDS:
        return dict(cached[1])
    try:
        limit = 320 if timeframe == '1h' else 260
        df = load_klines(symbol=symbol, timeframe=timeframe, limit=limit, use_cache=True)
        if df is not None and not df.empty:
            res = analyze_history_pattern(df, symbol=symbol, timeframe=timeframe)
            if isinstance(res, dict):
                _HISTORY_CACHE[key] = (now, dict(res))
                return dict(res)
    except Exception:
        pass
    return {
        'direction': 'NEUTRAL',
        'confidence': 0.0,
        'summary': '',
        'avg_future_return': 0.0,
        'regime': 'UNKNOWN',
        'move_style': 'unknown',
    }


def _combine_history(payload: Dict[str, Any], decision: Dict[str, Any], side: str) -> Dict[str, Any]:
    symbol = _infer_symbol(payload)
    h1 = _history_for_tf(symbol, '1h')
    h4 = _history_for_tf(symbol, '4h')

    def _pct(v: Any) -> float:
        x = _norm_pct(v, 0.0)
        return x

    dir1 = _norm_dir(h1.get('direction'))
    dir4 = _norm_dir(h4.get('direction'))
    conf1 = _pct(h1.get('confidence'))
    conf4 = _pct(h4.get('confidence'))
    avg1 = _f(h1.get('avg_future_return'), 0.0) * 100.0
    avg4 = _f(h4.get('avg_future_return'), 0.0) * 100.0

    score_long = 0.0
    score_short = 0.0
    score_neutral = 0.0
    for direction, conf, weight in ((dir1, conf1, 1.0), (dir4, conf4, 1.35)):
        if direction == 'LONG':
            score_long += conf * weight
        elif direction == 'SHORT':
            score_short += conf * weight
        else:
            score_neutral += max(20.0, conf) * weight

    if score_long > score_short + 6.0 and score_long > score_neutral:
        final_dir = 'LONG'
        final_conf = min(88.0, (score_long - max(score_short, score_neutral * 0.55)) * 0.62 + 22.0)
    elif score_short > score_long + 6.0 and score_short > score_neutral:
        final_dir = 'SHORT'
        final_conf = min(88.0, (score_short - max(score_long, score_neutral * 0.55)) * 0.62 + 22.0)
    else:
        final_dir = 'NEUTRAL'
        final_conf = min(65.0, max(conf1, conf4) * 0.55)

    if side in {'LONG', 'SHORT'} and final_dir == side:
        label = f'{final_dir}_ALIGNED'
    elif side in {'LONG', 'SHORT'} and final_dir in {'LONG', 'SHORT'} and final_dir != side:
        label = f'{final_dir}_CONTRA'
    else:
        label = final_dir

    return {
        'label': label or 'NEUTRAL',
        'direction': final_dir or 'NEUTRAL',
        'confidence': round(final_conf, 1),
        'tf_1h_direction': dir1 or 'NEUTRAL',
        'tf_1h_confidence': round(conf1, 1),
        'tf_1h_move_pct': round(avg1, 2),
        'tf_4h_direction': dir4 or 'NEUTRAL',
        'tf_4h_confidence': round(conf4, 1),
        'tf_4h_move_pct': round(avg4, 2),
        'summary_1h': _s(h1.get('summary')),
        'summary_4h': _s(h4.get('summary')),
    }


def _decision(payload: Dict[str, Any]) -> Dict[str, Any]:
    d = payload.get('decision')
    return d if isinstance(d, dict) else {}


def _first_dict(*values: Any) -> Dict[str, Any]:
    for value in values:
        if isinstance(value, dict):
            return value
    return {}


def _get_range(payload: Dict[str, Any]) -> Dict[str, float]:
    decision = _decision(payload)
    r = payload.get('range') if isinstance(payload.get('range'), dict) else {}
    low = _f(payload.get('range_low', decision.get('range_low', r.get('low', 0.0))), 0.0)
    mid = _f(payload.get('range_mid', decision.get('range_mid', r.get('mid', 0.0))), 0.0)
    high = _f(payload.get('range_high', decision.get('range_high', r.get('high', 0.0))), 0.0)
    return {'low': low, 'mid': mid, 'high': high}


def _range_pct(price: float, low: float, high: float) -> float:
    if high <= low:
        return 50.0
    return max(0.0, min(100.0, (price - low) / (high - low) * 100.0))


def _norm_dir(value: Any) -> str:
    text = _upper(value, '')
    if text in {'UP', 'BULL', 'BULLISH'} or 'UP' in text:
        return 'LONG'
    if text in {'DOWN', 'BEAR', 'BEARISH'} or 'DOWN' in text:
        return 'SHORT'
    if 'LONG' in text or 'ЛОНГ' in text:
        return 'LONG'
    if 'SHORT' in text or 'ШОРТ' in text:
        return 'SHORT'
    return 'NEUTRAL'


def _fmt_side_ru(side: str) -> str:
    return 'ШОРТ' if side == 'SHORT' else 'ЛОНГ' if side == 'LONG' else 'НЕЙТРАЛЬНО'


def _classify_history(payload: Dict[str, Any], decision: Dict[str, Any], side: str) -> tuple[str, float, str, Dict[str, Any]]:
    hist_combo = _combine_history(payload, decision, side)
    label = _s(hist_combo.get('label'), 'NEUTRAL')
    conf = _f(hist_combo.get('confidence'), 0.0)
    d1 = _fmt_side_ru(_s(hist_combo.get('tf_1h_direction'), 'NEUTRAL'))
    d4 = _fmt_side_ru(_s(hist_combo.get('tf_4h_direction'), 'NEUTRAL'))
    c1 = _f(hist_combo.get('tf_1h_confidence'), 0.0)
    c4 = _f(hist_combo.get('tf_4h_confidence'), 0.0)
    m1 = _f(hist_combo.get('tf_1h_move_pct'), 0.0)
    m4 = _f(hist_combo.get('tf_4h_move_pct'), 0.0)
    summary = f'1h: {d1} {c1:.1f}% ({m1:+.2f}%) | 4h: {d4} {c4:.1f}% ({m4:+.2f}%)'
    return label, conf, summary, hist_combo


def _classify_liquidity(payload: Dict[str, Any], decision: Dict[str, Any], side: str, price: float, low: float, high: float) -> tuple[str, str, float]:
    liq = _first_dict(payload.get('liquidation_context'), decision.get('liquidation_context'))
    state = _upper(liq.get('liquidity_state') or decision.get('liquidity_state_live') or decision.get('liquidity_context') or '', '')
    magnet = _norm_dir(liq.get('magnet_side') or liq.get('liquidity_magnet_side') or decision.get('liquidation_magnet'))
    cascade = _upper(liq.get('cascade_risk') or decision.get('liquidation_cascade_risk') or '', '')
    upper_cluster = _f(liq.get('upper_cluster_price'), 0.0)
    lower_cluster = _f(liq.get('lower_cluster_price'), 0.0)
    dist_up = abs(price - upper_cluster) / price * 100.0 if price > 0 and upper_cluster > 0 else 999.0
    dist_dn = abs(price - lower_cluster) / price * 100.0 if price > 0 and lower_cluster > 0 else 999.0
    rpct = _range_pct(price, low, high) if price > 0 and high > low else 50.0

    label = 'NEUTRAL'
    bonus = 0.0
    if 'BUY_SIDE_SWEEP_REJECTED' in state:
        label = 'SHORT_SWEEP_REJECT'
        bonus += 16.0 if side == 'SHORT' else 6.0
    elif 'SELL_SIDE_SWEEP_REJECTED' in state:
        label = 'LONG_SWEEP_REJECT'
        bonus += 16.0 if side == 'LONG' else 6.0
    elif magnet in {'LONG', 'SHORT'}:
        label = f'{magnet}_MAGNET'
        if side == magnet:
            bonus += 5.0
        elif side != 'NEUTRAL':
            bonus -= 4.0

    if cascade == 'HIGH':
        label += ' + CASCADE_RISK' if label != 'NEUTRAL' else 'CASCADE_RISK_HIGH'
        bonus -= 4.0

    if side == 'SHORT' and high > low and price >= high * 0.985 and dist_up <= 0.55:
        label = 'UP_LIQUIDITY_NEAR'
        bonus += 10.0
    elif side == 'LONG' and high > low and price <= low * 1.015 and dist_dn <= 0.55:
        label = 'DOWN_LIQUIDITY_NEAR'
        bonus += 10.0

    # Fallback when no live liquidation feed is available: use range position as a simple liquidity proxy.
    if label == 'NEUTRAL':
        if rpct >= 68.0:
            label = 'UP_LIQUIDITY_PRESSURE'
            if side == 'SHORT':
                bonus += 7.0
            elif side == 'LONG':
                bonus -= 5.0
            else:
                bonus += 2.0
        elif rpct <= 32.0:
            label = 'DOWN_LIQUIDITY_PRESSURE'
            if side == 'LONG':
                bonus += 7.0
            elif side == 'SHORT':
                bonus -= 5.0
            else:
                bonus += 2.0
        elif rpct >= 60.0:
            label = 'WEAK_UP_LIQUIDITY'
            if side == 'SHORT':
                bonus += 4.0
        elif rpct <= 40.0:
            label = 'WEAK_DOWN_LIQUIDITY'
            if side == 'LONG':
                bonus += 4.0

    return label, state or 'NEUTRAL', bonus


def _classify_fake_move(payload: Dict[str, Any], decision: Dict[str, Any], price: float = 0.0, low: float = 0.0, high: float = 0.0, side: str = 'NEUTRAL') -> tuple[str, float, str]:
    fake = _first_dict(payload.get('fake_move_detector'), decision.get('fake_move_detector'))
    ftype = _upper(fake.get('type') or fake.get('classification') or '', '')
    conf = _norm_pct(fake.get('confidence') or fake.get('reclaim_strength') or 0.0, 0.0)
    implication = _s(fake.get('summary') or fake.get('implication') or fake.get('action') or '')
    if not ftype and conf <= 0.0:
        # fallback heuristic around range edges when explicit fake-move detector is silent
        rpct = _range_pct(price, low, high) if price > 0 and high > low else 50.0
        if side == 'SHORT' and rpct >= 68.0:
            conf = min(72.0, 34.0 + (rpct - 68.0) * 1.7)
            return 'EARLY_FAKE_UP_RISK', conf, 'верхняя зона перегрета: допустимо искать early fake-up / возврат вниз'
        if side == 'LONG' and rpct <= 32.0:
            conf = min(72.0, 34.0 + (32.0 - rpct) * 1.7)
            return 'EARLY_FAKE_DOWN_RISK', conf, 'нижняя зона перепродана: допустимо искать early fake-down / возврат вверх'
        return 'NONE', 0.0, ''
    if 'FAKE_UP' in ftype or 'EARLY_FAKE_UP' in ftype:
        return 'FAKE_UP_RISK', conf or 52.0, implication
    if 'FAKE_DOWN' in ftype or 'EARLY_FAKE_DOWN' in ftype:
        return 'FAKE_DOWN_RISK', conf or 52.0, implication
    if 'CONTINUATION_UP' in ftype:
        return 'REAL_UP_CONTINUATION', conf or 64.0, implication
    if 'CONTINUATION_DOWN' in ftype:
        return 'REAL_DOWN_CONTINUATION', conf or 64.0, implication
    if 'RANGE_FAKE_RISK' in ftype:
        return 'RANGE_FAKE_RISK', conf or 44.0, implication
    return ftype or 'NONE', conf, implication


def evaluate_shadow_engine(payload: Dict[str, Any], *, title: str = '') -> Dict[str, Any]:
    decision = _decision(payload)
    price = _f(payload.get('price') or payload.get('last_price') or payload.get('close'), 0.0)
    rr = _get_range(payload)
    low, mid, high = rr['low'], rr['mid'], rr['high']
    rpct = _range_pct(price, low, high) if price > 0 and high > low else 50.0
    range_pos = 'MID'
    if rpct >= 68:
        range_pos = 'UPPER'
    elif rpct <= 32:
        range_pos = 'LOWER'

    long_score = _norm_pct(decision.get('long_score', payload.get('long_score', 0.0)), 0.0)
    short_score = _norm_pct(decision.get('short_score', payload.get('short_score', 0.0)), 0.0)

    bias_dir = _norm_dir(
        decision.get('direction_text')
        or decision.get('direction')
        or payload.get('forecast_direction')
        or payload.get('signal')
        or decision.get('bias_direction')
        or 'NEUTRAL'
    )
    if bias_dir != 'NEUTRAL':
        side = bias_dir
    else:
        if short_score > long_score + 1.0:
            side = 'SHORT'
        elif long_score > short_score + 1.0:
            side = 'LONG'
        else:
            side = 'NEUTRAL'

    diff = 0.0
    if side == 'SHORT':
        diff = max(0.0, short_score - long_score)
    elif side == 'LONG':
        diff = max(0.0, long_score - short_score)
    else:
        diff = abs(short_score - long_score) * 0.35

    bias_conf = _norm_pct(
        decision.get('bias_confidence')
        or decision.get('confidence_pct')
        or decision.get('confidence')
        or payload.get('forecast_confidence')
        or 0.0,
        0.0,
    )
    edge = 10.0 + min(26.0, diff * 1.25) + min(9.0, max(0.0, bias_conf - 25.0) * 0.16)

    if side == 'SHORT':
        if rpct >= 72:
            edge += 16.0
        elif rpct >= 60:
            edge += 8.0
        elif rpct <= 40:
            edge -= 12.0
        elif 45 <= rpct <= 55:
            edge -= 4.0
    elif side == 'LONG':
        if rpct <= 28:
            edge += 16.0
        elif rpct <= 40:
            edge += 8.0
        elif rpct >= 60:
            edge -= 12.0
        elif 45 <= rpct <= 55:
            edge -= 4.0
    else:
        edge += 1.0 if range_pos == 'MID' else 4.0

    fake_label, fake_conf, fake_note = _classify_fake_move(payload, decision, price=price, low=low, high=high, side=side)
    if side == 'SHORT':
        if fake_label == 'FAKE_UP_RISK':
            edge += min(18.0, 6.0 + fake_conf * 0.16)
        elif fake_label == 'REAL_UP_CONTINUATION':
            edge -= min(16.0, 6.0 + fake_conf * 0.14)
        elif fake_label == 'FAKE_DOWN_RISK':
            edge -= min(10.0, fake_conf * 0.10)
    elif side == 'LONG':
        if fake_label == 'FAKE_DOWN_RISK':
            edge += min(18.0, 6.0 + fake_conf * 0.16)
        elif fake_label == 'REAL_DOWN_CONTINUATION':
            edge -= min(16.0, 6.0 + fake_conf * 0.14)
        elif fake_label == 'FAKE_UP_RISK':
            edge -= min(10.0, fake_conf * 0.10)
    elif fake_label == 'RANGE_FAKE_RISK':
        edge += 6.0

    liq_label, liq_state, liq_bonus = _classify_liquidity(payload, decision, side, price, low, high)
    edge += liq_bonus

    hist_label, hist_conf, hist_note, hist_pack = _classify_history(payload, decision, side)
    if hist_label.endswith('_ALIGNED'):
        edge += min(14.0, 5.0 + hist_conf * 0.11)
    elif hist_label.endswith('_CONTRA'):
        edge -= min(14.0, 5.0 + hist_conf * 0.11)
    elif hist_label in {'LONG', 'SHORT'} and side == 'NEUTRAL':
        edge += min(8.0, hist_conf * 0.08)

    regime = _upper(payload.get('market_regime') or payload.get('range_state') or decision.get('market_mode') or decision.get('mode') or 'MIXED', 'MIXED')
    bot_mode = _first_dict(decision.get('bot_mode_context'), payload.get('bot_mode_context'))
    volume_range = _first_dict(payload.get('volume_range_conditions'), decision.get('range_bot_permission'))
    breakout_risk = _upper(
        volume_range.get('breakout_risk')
        or bot_mode.get('breakout_risk')
        or decision.get('breakout_risk')
        or decision.get('trap_risk')
        or payload.get('breakout_risk')
        or 'MID',
        'MID',
    )
    if breakout_risk == 'HIGH':
        edge -= 4.0
    elif breakout_risk == 'LOW':
        edge += 4.0

    edge = max(8.0, min(84.0, edge))
    if side == 'NEUTRAL' and edge > 44.0:
        edge = 44.0

    if edge >= 60.0:
        edge_label = 'TRADEABLE'
    elif edge >= 44.0:
        edge_label = 'SOFT'
    elif edge >= 26.0:
        edge_label = 'WEAK'
    else:
        edge_label = 'MIXED'

    near_short_edge = rpct >= 58.0
    near_long_edge = rpct <= 42.0
    very_near_short_edge = rpct >= 70.0
    very_near_long_edge = rpct <= 30.0
    if side == 'NEUTRAL':
        execution = 'WATCH'
    elif side == 'SHORT':
        if fake_label == 'FAKE_UP_RISK' and fake_conf >= 60.0 and rpct >= 58.0:
            execution = 'SMALL'
        elif (very_near_short_edge and edge >= 44.0) or (near_short_edge and edge >= 36.0 and fake_label == 'FAKE_UP_RISK'):
            execution = 'PROBE'
        elif (near_short_edge and edge >= 18.0) or (rpct >= 64.0 and edge >= 15.0):
            execution = 'PROBE'
        elif near_short_edge or edge >= 24.0:
            execution = 'WATCH'
        else:
            execution = 'WAIT'
    else:
        if fake_label == 'FAKE_DOWN_RISK' and fake_conf >= 60.0 and rpct <= 42.0:
            execution = 'SMALL'
        elif (very_near_long_edge and edge >= 44.0) or (near_long_edge and edge >= 36.0 and fake_label == 'FAKE_DOWN_RISK'):
            execution = 'PROBE'
        elif (near_long_edge and edge >= 18.0) or (rpct <= 36.0 and edge >= 15.0):
            execution = 'PROBE'
        elif near_long_edge or edge >= 24.0:
            execution = 'WATCH'
        else:
            execution = 'WAIT'

    zone_top = f'{high:.2f}' if high > 0 else 'верхней зоне'
    zone_low = f'{low:.2f}' if low > 0 else 'нижней зоне'
    if side == 'SHORT':
        base = 'ШОРТ: искать реакцию продавца у верхней зоны и возврат в диапазон'
        alt = f'если рынок примет цену выше {zone_top}, шортовый сценарий ломается'
        invalidation = f'принятие цены выше {zone_top} и follow-through вверх'
        tactical = 'приоритет short; без погони, у верхней зоны допускается probe, при фейке вверх — small'
        best_trade = 'fade upper sweep / reclaim short'
    elif side == 'LONG':
        base = 'ЛОНГ: искать выкуп нижней зоны и возврат в диапазон'
        alt = f'если рынок примет цену ниже {zone_low}, лонговый сценарий ломается'
        invalidation = f'принятие цены ниже {zone_low} и follow-through вниз'
        tactical = 'приоритет long; без погони, у нижней зоны допускается probe, при фейке вниз — small'
        best_trade = 'fade lower sweep / reclaim long'
    else:
        base = 'диапазон жив, базово ждать подход к краю и реакцию'
        alt = 'если появится импульс с удержанием за уровнем, рынок уйдёт из range'
        invalidation = 'сильный импульс и принятие цены за границей диапазона'
        tactical = 'середина диапазона: только наблюдение и ранний arm для range-логики'
        best_trade = 'range participation / early arm'

    range_friendly = ('RANGE' in regime) or ('FRIENDLY' in regime) or (bot_mode.get('range_friendly') is True)
    if breakout_risk == 'HIGH':
        gin = 'BLOCKED_BREAKOUT'
        gin_note = 'breakout risk высокий: только reduced / без adds'
    elif range_friendly and side == 'SHORT' and rpct >= 65.0:
        gin = 'READY_L1'
        gin_note = 'верхняя зона близко: short volume-layer L1 можно включать раньше точного входа'
    elif range_friendly and side == 'LONG' and rpct <= 35.0:
        gin = 'READY_L1'
        gin_note = 'нижняя зона близко: long volume-layer L1 можно включать раньше точного входа'
    elif range_friendly and side == 'NEUTRAL' and rpct >= 65.0:
        gin = 'READY_L1'
        gin_note = 'верхняя часть диапазона: range short L1 можно готовить заранее'
    elif range_friendly and side == 'NEUTRAL' and rpct <= 35.0:
        gin = 'READY_L1'
        gin_note = 'нижняя часть диапазона: range long L1 можно готовить заранее'
    elif range_friendly and 30.0 < rpct < 70.0:
        gin = 'EARLY_ARM'
        gin_note = 'диапазон жив: volume-layer можно армить заранее, adds пока не давать'
    else:
        gin = 'WATCH'
        gin_note = 'пока только наблюдение без выключения range-логики'

    if gin == 'READY_L1' and execution in {'WAIT', 'WATCH'}:
        execution = 'PROBE'
    elif gin == 'EARLY_ARM' and execution == 'WAIT' and edge >= 14.0:
        execution = 'WATCH'

    if execution == 'SMALL':
        action_now = 'small вход допустим только по стороне сценария, без агрессивных доборов'
    elif execution == 'PROBE':
        action_now = 'можно пробовать малый вход у рабочей зоны, без погони и без усреднения'
    elif execution == 'WATCH':
        action_now = 'наблюдать реакцию у рабочей зоны и не форсировать вход'
    else:
        action_now = 'ждать подход к рабочей зоне, не входить из середины'

    trade_fix = build_v13_trade_fix_context(payload, side=side)

    if trade_fix.get('action_code') == 'NO_TRADE_MID':
        execution = 'WAIT'
    elif trade_fix.get('entry_state') == 'ACTIVE':
        execution = 'SMALL'
    elif trade_fix.get('entry_state') == 'READY':
        execution = 'PROBE' if execution in {'WAIT', 'WATCH'} else execution
    elif trade_fix.get('action_code') == 'FOLLOW_THROUGH':
        execution = 'WATCH' if execution == 'WAIT' else execution
    elif trade_fix.get('action_code') in {'LOOK_SHORT_ZONE', 'LOOK_LONG_ZONE'}:
        execution = 'PROBE' if execution in {'WAIT', 'WATCH'} else execution

    if trade_fix.get('action_text'):
        action_now = trade_fix.get('action_text')

    global_side = side if side in {'LONG', 'SHORT', 'NEUTRAL'} else 'NEUTRAL'
    local_side = trade_fix.get('entry_side') if trade_fix.get('entry_side') in {'LONG', 'SHORT'} else (
        trade_fix.get('reversal_side') if trade_fix.get('reversal_side') in {'LONG', 'SHORT'} else global_side
    )
    local_mode = 'MAIN'
    if global_side in {'LONG', 'SHORT'} and local_side in {'LONG', 'SHORT'} and local_side != global_side:
        local_mode = 'COUNTERTREND'
    elif local_side == 'NEUTRAL':
        local_mode = 'WAIT'

    if local_side == 'LONG':
        local_context = 'локально лонг от зоны / выкуп снизу'
    elif local_side == 'SHORT':
        local_context = 'локально шорт от зоны / реакция сверху'
    else:
        local_context = 'локально входа нет'

    if local_mode == 'COUNTERTREND':
        local_context += ' (контртренд против глобального уклона)'

    if trade_fix.get('entry_state') == 'ACTIVE' and trade_fix.get('entry_side') in {'LONG', 'SHORT'}:
        best_trade = f"{trade_fix.get('entry_side', 'NEUTRAL').lower()} trigger active / reclaim entry"
    elif trade_fix.get('entry_state') == 'READY' and trade_fix.get('entry_side') in {'LONG', 'SHORT'}:
        best_trade = f"{trade_fix.get('entry_side', 'NEUTRAL').lower()} setup ready / wait reclaim"
    elif trade_fix.get('entry_side') in {'LONG', 'SHORT'} and trade_fix.get('reversal_conf', 0.0) >= 52.0:
        best_trade = f"{trade_fix.get('entry_side', 'NEUTRAL').lower()} edge / real zone reaction"

    bot_states = {
        'ct_long': 'BLOCKED' if side == 'SHORT' and execution in {'PROBE', 'SMALL'} else 'WATCH',
        'ct_short': 'PROBE' if side == 'SHORT' and execution == 'PROBE' else 'ACTIVE_LIGHT' if side == 'SHORT' and execution == 'SMALL' else 'WATCH',
        'range_long': 'WATCH' if gin in {'WATCH', 'BLOCKED_BREAKOUT'} else 'EARLY_ARM' if gin == 'EARLY_ARM' and side != 'SHORT' else 'READY_L1' if gin == 'READY_L1' and side in {'LONG', 'NEUTRAL'} and rpct <= 50.0 else 'WATCH',
        'range_short': 'WATCH' if gin in {'WATCH', 'BLOCKED_BREAKOUT'} else 'EARLY_ARM' if gin == 'EARLY_ARM' and side != 'LONG' else 'READY_L1' if gin == 'READY_L1' and side in {'SHORT', 'NEUTRAL'} and rpct >= 50.0 else 'WATCH',
    }
    if gin == 'BLOCKED_BREAKOUT':
        bot_states['range_long'] = 'BLOCKED'
        bot_states['range_short'] = 'BLOCKED'

    return {
        'side': side,
        'global_side': global_side,
        'local_side': local_side,
        'local_mode': local_mode,
        'local_context': local_context,
        'edge_score': round(edge, 1),
        'edge_label': edge_label,
        'execution': execution,
        'range_pct': round(rpct, 1),
        'range_position': range_pos,
        'base': base,
        'alternative': alt,
        'invalidation': invalidation,
        'tactical': tactical,
        'action_now': action_now,
        'best_trade': best_trade,
        'ginarea_state': gin,
        'ginarea_note': gin_note,
        'liquidity_label': liq_label,
        'liquidity_state': liq_state or 'NEUTRAL',
        'history_label': hist_label,
        'history_conf': round(hist_conf, 1),
        'history_note': hist_note,
        'history_1h_direction': hist_pack.get('tf_1h_direction', 'NEUTRAL'),
        'history_1h_confidence': hist_pack.get('tf_1h_confidence', 0.0),
        'history_1h_move_pct': hist_pack.get('tf_1h_move_pct', 0.0),
        'history_4h_direction': hist_pack.get('tf_4h_direction', 'NEUTRAL'),
        'history_4h_confidence': hist_pack.get('tf_4h_confidence', 0.0),
        'history_4h_move_pct': hist_pack.get('tf_4h_move_pct', 0.0),
        'fake_move_label': fake_label,
        'fake_move_conf': round(fake_conf, 1),
        'fake_move_note': fake_note,
        'bot_states': bot_states,
        'trade_fix': trade_fix,
    }


def render_shadow_compare(payload: Dict[str, Any], *, title: str = '') -> str:
    """V14 hardening: legacy V13 shadow overlay disabled in production output."""
    return ''
    e = evaluate_shadow_engine(payload, title=title)
    side_ru = _fmt_side_ru(e['side'])
    global_side_ru = _fmt_side_ru(e.get('global_side', e['side']))
    local_side_ru = _fmt_side_ru(e.get('local_side', 'NEUTRAL'))
    upper_title = _upper(title, '')
    lines = ['', '🆕 V13 CORE (NEW ENGINE)']

    hist_line = f'• history 1h/4h: {_fmt_side_ru(e["history_1h_direction"])} {float(e["history_1h_confidence"]):.1f}% ({float(e["history_1h_move_pct"]):+.2f}%) | {_fmt_side_ru(e["history_4h_direction"])} {float(e["history_4h_confidence"]):.1f}% ({float(e["history_4h_move_pct"]):+.2f}%)'

    tf = e.get('trade_fix', {}) if isinstance(e.get('trade_fix'), dict) else {}
    context_line = f'• глобально/локально: {global_side_ru} → {local_side_ru} | {e.get("local_context", "локально входа нет")}'
    impulse_line = f"• impulse: {tf.get('impulse_label', 'UNKNOWN')} ({float(tf.get('impulse_score', 0.0)):.1f}/100) | continuation: {tf.get('continuation_label', 'LOW')} ({float(tf.get('continuation_score', 0.0)):.1f}/100)"
    zones_line = f"• зоны: short {tf.get('short_zone_text', 'нет данных')} | long {tf.get('long_zone_text', 'нет данных')} | mid {tf.get('no_trade_text', 'нет данных')}"
    reversal_line = f"• разворот: {tf.get('reversal_side_ru', 'НЕЙТРАЛЬНО')} ({float(tf.get('reversal_conf', 0.0)):.1f}%) | {tf.get('reversal_reason', 'нет данных')}"
    reaction_line = f"• реакция: {tf.get('reaction_state', 'NONE')} ({float(tf.get('reaction_score', 0.0)):.1f}%) | {tf.get('reaction_text', 'нет данных')}"
    liquidity_line = f"• ликвидность: {tf.get('liquidity_text', 'нет данных')} | fake: {tf.get('fake_type', 'NONE')} ({float(tf.get('fake_conf', 0.0)):.1f}%)"
    entry_line = f"• entry: {tf.get('entry_state_ru', 'НЕ ГОТОВО')} | trigger {float(tf.get('trigger_strength', 0.0)):.1f}% | {tf.get('entry_trigger_text', 'нет данных')}"
    lifecycle_line = f"• lifecycle: {tf.get('lifecycle_state_ru', 'НЕ ГОТОВО')} | {tf.get('lifecycle_reason', 'нет данных')}"
    confirm_line = f"• confirm: {tf.get('confirmation_state_ru', 'НЕТ')} ({float(tf.get('confirmation_score', 0.0)):.1f}%) | {tf.get('confirmation_reason', 'нет данных')}"
    quick_map_line = f"• карта: {_zone_icon(tf.get('active_zone', ''))} | {_entry_icon(tf.get('entry_state', ''))} | {_confirm_icon(tf.get('confirmation_state', ''))} | {_impulse_icon(tf.get('impulse_label', ''))}"

    if 'FORECAST' in upper_title or 'ПРОГНОЗ' in upper_title:
        lines.extend([
            f'• перевес: {side_ru}',
            f'• edge: {e["edge_label"]} ({e["edge_score"]:.1f}/100)',
            f'• execution: {e["execution"]}',
            context_line,
            f'• global: {e["base"]}',
            f'• local: {tf.get("action_reason") or e.get("local_context")}',
            f'• alternative: {e["alternative"]}',
            impulse_line,
            zones_line,
            reversal_line,
            reaction_line,
            liquidity_line,
            entry_line,
            lifecycle_line,
            confirm_line,
            f'• invalidation: {tf.get("invalidation_text") or e["invalidation"]}',
            hist_line,
        ])
    elif 'ЛУЧШАЯ СДЕЛКА' in upper_title or 'BEST TRADE' in upper_title:
        lines.extend([
            f'• лучший сценарий: {e["best_trade"]}',
            f'• сторона: {side_ru}',
            f'• edge: {e["edge_label"]} ({e["edge_score"]:.1f}/100)',
            f'• execution: {e["execution"]}',
            context_line,
            quick_map_line,
            f'• действие сейчас: {tf.get("action_text") or e["action_now"]}',
            entry_line,
            lifecycle_line,
            confirm_line,
            reversal_line,
            reaction_line,
            zones_line,
            f'• invalidation: {tf.get("invalidation_text") or e["invalidation"]}',
        ])
    elif 'TRADE MANAGER' in upper_title or 'МЕНЕДЖЕР' in upper_title:
        lines.extend([
            f'• сторона: {side_ru}',
            f'• execution: {e["execution"]}',
            f'• главное действие: {tf.get("action_text") or e["action_now"]}',
            context_line,
            f'• причина: {tf.get("action_reason") or e.get("local_context")}',
            quick_map_line,
            entry_line,
            lifecycle_line,
            confirm_line,
            impulse_line,
            reversal_line,
            reaction_line,
            liquidity_line,
            f'• invalidation: {tf.get("invalidation_text") or e["invalidation"]}',
        ])
    elif 'GINAREA' in upper_title:
        lines.extend([
            f'• перевес: {side_ru}',
            f'• edge: {e["edge_label"]} ({e["edge_score"]:.1f}/100)',
            f'• status: {e["ginarea_state"]}',
            f'• действие: {e["ginarea_note"]}',
            f'• range long: {e["bot_states"]["range_long"]}',
            f'• range short: {e["bot_states"]["range_short"]}',
            zones_line,
            liquidity_line,
            hist_line,
        ])
    elif 'СТАТУС БОТОВ' in upper_title or 'BOTS STATUS' in upper_title:
        lines.extend([
            f'• CT LONG: {e["bot_states"]["ct_long"]}',
            f'• CT SHORT: {e["bot_states"]["ct_short"]}',
            f'• RANGE LONG: {e["bot_states"]["range_long"]}',
            f'• RANGE SHORT: {e["bot_states"]["range_short"]}',
            f'• ginarea: {e["ginarea_state"]} | {e["ginarea_note"]}',
            context_line,
            f'• trigger: {tf.get("action_text") or e.get("local_context")}',
            entry_line,
            zones_line,
            hist_line,
        ])
    elif 'СВОДКА' in upper_title or 'SUMMARY' in upper_title:
        lines.extend([
            f'• перевес: {side_ru}',
            f'• edge: {e["edge_label"]} ({e["edge_score"]:.1f}/100)',
            f'• execution: {e["execution"]}',
            context_line,
            f'• scenario: {tf.get("action_reason") or e.get("local_context")}',
            quick_map_line,
            impulse_line,
            zones_line,
            liquidity_line,
            entry_line,
            hist_line,
        ])
    elif 'ЧТО ДЕЛАТЬ' in upper_title or 'ACTION' in upper_title:
        lines.extend([
            f'• приоритет: {side_ru}',
            f'• edge: {e["edge_label"]} ({e["edge_score"]:.1f}/100)',
            f'• execution: {e["execution"]}',
            context_line,
            f'• что делать: {tf.get("action_text") or e["action_now"]}',
            f'• почему: {tf.get("action_reason") or e.get("local_context")}',
            quick_map_line,
            entry_line,
            lifecycle_line,
            confirm_line,
            reaction_line,
            impulse_line,
            zones_line,
            reversal_line,
            liquidity_line,
            f'• ginarea: {e["ginarea_state"]} | {e["ginarea_note"]}',
            hist_line,
            f'• отмена идеи: {tf.get("invalidation_text") or e["invalidation"]}',
        ])
    else:
        lines.extend([
            f'• перевес: {side_ru}',
            f'• edge: {e["edge_label"]} ({e["edge_score"]:.1f}/100)',
            f'• execution: {e["execution"]}',
            f'• range pos: {e["range_position"]} ({e["range_pct"]:.1f}%)',
            context_line,
            f'• глобально: {e["base"]}',
            f'• локально: {tf.get("action_reason") or e.get("local_context")}',
            f'• альтернатива: {e["alternative"]}',
            quick_map_line,
            impulse_line,
            zones_line,
            reversal_line,
            reaction_line,
            liquidity_line,
            entry_line,
            lifecycle_line,
            confirm_line,
            f'• invalidation: {tf.get("invalidation_text") or e["invalidation"]}',
            f'• тактика: {tf.get("action_text") or e["tactical"]}',
            hist_line,
            f'• ginarea: {e["ginarea_state"]} | {e["ginarea_note"]}',
        ])
    return '\n'.join(lines)
