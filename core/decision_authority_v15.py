from __future__ import annotations

from typing import Any, Dict, List


def _f(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == '':
            return default
        if isinstance(v, str):
            v = v.replace(' ', '').replace(',', '')
        return float(v)
    except Exception:
        return default


def build_decision_authority_v15(payload: Dict[str, Any], legacy_decision: Dict[str, Any] | None = None) -> Dict[str, Any]:
    blocks = payload.get('liquidity_blocks') if isinstance(payload.get('liquidity_blocks'), dict) else {}
    reaction = payload.get('liquidation_reaction') if isinstance(payload.get('liquidation_reaction'), dict) else {}
    move = payload.get('impulse_character') if isinstance(payload.get('impulse_character'), dict) else {}
    pattern = payload.get('pattern_memory_v2') if isinstance(payload.get('pattern_memory_v2'), dict) else {}
    pin = payload.get('pinbar_context') if isinstance(payload.get('pinbar_context'), dict) else {}
    volume = payload.get('volume_confirmation') if isinstance(payload.get('volume_confirmation'), dict) else {}
    liq = payload.get('liquidity_decision') if isinstance(payload.get('liquidity_decision'), dict) else {}
    rev = payload.get('reversal_v15') if isinstance(payload.get('reversal_v15'), dict) else {}
    price = _f(payload.get('price') or payload.get('last_price') or payload.get('current_price') or payload.get('close'))
    low = _f(payload.get('range_low')); mid = _f(payload.get('range_mid')); high = _f(payload.get('range_high'))

    long_score=0.0; short_score=0.0; why_long: List[str]=[]; why_short: List[str]=[]

    pos = 0.5
    if low < price < high:
        pos = (price-low)/max(high-low,1e-9)
    if pos <= 0.24:
        long_score += 18; why_long.append('цена у нижней части диапазона / блока')
    elif pos >= 0.76:
        short_score += 18; why_short.append('цена у верхней части диапазона / блока')

    trap_side = str(reaction.get('trap_side') or 'NONE').upper()
    if trap_side == 'LONG':
        long_score += 34; why_long.append('нижний вынос не принят рынком')
    elif trap_side == 'SHORT':
        short_score += 34; why_short.append('верхний вынос не принят рынком')

    acceptance = str(reaction.get('acceptance') or 'NONE').upper()
    if acceptance == 'ACCEPTED_ABOVE':
        long_score += 24; short_score -= 14; why_long.append('рынок удерживает цену выше верхнего блока')
    elif acceptance == 'ACCEPTED_BELOW':
        short_score += 24; long_score -= 14; why_short.append('рынок удерживает цену ниже нижнего блока')

    move_state = str(move.get('state') or 'NO_CLEAR_IMPULSE').upper()
    if move_state in {'EXHAUSTION_DOWN','TRAP_CANDIDATE_DOWN'}:
        long_score += 18; why_long.append('движение вниз затухает / похоже на trap')
    elif move_state in {'EXHAUSTION_UP','TRAP_CANDIDATE_UP'}:
        short_score += 18; why_short.append('движение вверх затухает / похоже на trap')
    elif move_state == 'CONTINUATION_UP':
        long_score += 15; short_score -= 8; why_long.append('продолжение вверх пока живое')
    elif move_state == 'CONTINUATION_DOWN':
        short_score += 15; long_score -= 8; why_short.append('продолжение вниз пока живое')

    pbias = str(pattern.get('pattern_bias') or pattern.get('direction') or 'NEUTRAL').upper()
    pconf = _f(pattern.get('confidence'))
    if pbias == 'LONG' and pconf >= 40:
        long_score += 8 + min(10.0, pconf / 8.0); why_long.append('история паттернов чаще поддерживает bounce вверх')
    elif pbias == 'SHORT' and pconf >= 40:
        short_score += 8 + min(10.0, pconf / 8.0); why_short.append('история паттернов чаще поддерживает движение вниз')

    if pin.get('pinbar_valid'):
        if str(pin.get('side')).upper() == 'LONG':
            long_score += 12 if pin.get('pinbar_confirmed') else 8; why_long.append('есть рабочий bullish pinbar в блоке')
        elif str(pin.get('side')).upper() == 'SHORT':
            short_score += 12 if pin.get('pinbar_confirmed') else 8; why_short.append('есть рабочий bearish pinbar в блоке')

    vstate = str(volume.get('state') or '').upper()
    if vstate == 'CONFIRMED':
        if acceptance == 'ACCEPTED_ABOVE' or move_state == 'CONTINUATION_UP':
            long_score += 8; why_long.append('объём подтверждает продолжение вверх')
        elif acceptance == 'ACCEPTED_BELOW' or move_state == 'CONTINUATION_DOWN':
            short_score += 8; why_short.append('объём подтверждает продолжение вниз')
    elif vstate == 'WEAK':
        if trap_side == 'LONG':
            long_score += 6; why_long.append('объём не подтвердил пролив вниз')
        if trap_side == 'SHORT':
            short_score += 6; why_short.append('объём не подтвердил вынос вверх')

    liq_pressure = str(liq.get('liq_side_pressure') or 'NEUTRAL').upper()
    unwind = str(liq.get('unwind_state') or 'NONE').upper()
    if liq_pressure == 'UP' and acceptance != 'REJECTED_ABOVE':
        long_score += 6; why_long.append('деривативный поток давит вверх')
    elif liq_pressure == 'DOWN' and acceptance != 'REJECTED_BELOW':
        short_score += 6; why_short.append('деривативный поток давит вниз')
    if unwind == 'LONG_UNWIND' and trap_side == 'LONG':
        long_score += 6; why_long.append('long unwind уже прошёл, отскок вероятнее')
    if unwind == 'SHORT_COVER' and trap_side == 'SHORT':
        short_score += 6; why_short.append('short cover уже прошёл, fade вероятнее')

    rev_state = str(rev.get('state') or 'NO_REVERSAL').upper()
    if rev_state.endswith('_UP'):
        long_score += 12; why_long.append('разворот вверх подтверждается')
    elif rev_state.endswith('_DOWN'):
        short_score += 12; why_short.append('разворот вниз подтверждается')

    # block quality and freshness
    long_score += min(10.0, _f(blocks.get('lower_block_strength')) / 15.0)
    short_score += min(10.0, _f(blocks.get('upper_block_strength')) / 15.0)
    if str(blocks.get('lower_state')).upper() == 'WEAKENING':
        long_score -= 6
    if str(blocks.get('upper_state')).upper() == 'WEAKENING':
        short_score -= 6

    long_score=max(0.0,long_score); short_score=max(0.0,short_score)
    direction='NEUTRAL'; reasons=['нет достаточного перевеса']
    dom=max(long_score,short_score); diff=abs(long_score-short_score)
    if diff >= 8:
        if long_score > short_score:
            direction='LONG'; reasons=why_long
        else:
            direction='SHORT'; reasons=why_short

    state='WATCH_ZONE'; action='WATCH_ZONE'; summary='ждать реакцию на рабочем блоке'; setup_note='готового входа ещё нет'; entry_hint=''; grid_action='WATCH'
    if direction == 'LONG' and trap_side == 'LONG' and (pin.get('pinbar_confirmed') or rev_state in {'CONFIRMED_REVERSAL_UP','EARLY_REVERSAL_UP'}):
        state='EXECUTE_PROBE_LONG'; action='EXECUTE_PROBE_LONG'; summary='нижний блок удержан, long probe допустим'; setup_note='после reclaim выше блока можно включать small long-grid'; entry_hint=f'возврат выше {low:.2f} и отсутствие follow-through вниз'; grid_action='ENABLE_SMALL'
    elif direction == 'SHORT' and trap_side == 'SHORT' and (pin.get('pinbar_confirmed') or rev_state in {'CONFIRMED_REVERSAL_DOWN','EARLY_REVERSAL_DOWN'}):
        state='EXECUTE_PROBE_SHORT'; action='EXECUTE_PROBE_SHORT'; summary='верхний блок удержан, short probe допустим'; setup_note='после возврата под блок можно включать small short-grid'; entry_hint=f'возврат под {high:.2f} и отсутствие follow-through вверх'; grid_action='ENABLE_SMALL'
    elif direction == 'LONG' and pos <= 0.3:
        state='ARM_LONG'; action='ARM_LONG'; summary='следить за выкупом нижнего блока'; setup_note='ждём reclaim / bullish reaction'; entry_hint=f'смотреть реакцию {low:.2f}–{mid:.2f}'; grid_action='ARM_LONG'
    elif direction == 'SHORT' and pos >= 0.7:
        state='ARM_SHORT'; action='ARM_SHORT'; summary='следить за отказом от верхнего блока'; setup_note='ждём rejection / bearish reaction'; entry_hint=f'смотреть реакцию {mid:.2f}–{high:.2f}'; grid_action='ARM_SHORT'
    elif direction == 'LONG' and move_state == 'CONTINUATION_UP' and acceptance == 'ACCEPTED_ABOVE':
        state='EXECUTE_LONG'; action='EXECUTE_LONG'; summary='пробой вверх принят, long по продолжению допустим'; setup_note='лонг только без погони, лучше на слабом откате'; entry_hint=f'удержание выше {high:.2f}'; grid_action='HOLD'
    elif direction == 'SHORT' and move_state == 'CONTINUATION_DOWN' and acceptance == 'ACCEPTED_BELOW':
        state='EXECUTE_SHORT'; action='EXECUTE_SHORT'; summary='пролив вниз принят, short по продолжению допустим'; setup_note='шорт лучше без догонки, на слабом откате'; entry_hint=f'удержание ниже {low:.2f}'; grid_action='HOLD'

    invalidation=''
    if direction == 'LONG' and low > 0: invalidation=f'закрепление ниже {low:.2f} ломает long-сценарий'
    elif direction == 'SHORT' and high > 0: invalidation=f'закрепление выше {high:.2f} ломает short-сценарий'
    elif low > 0 and high > 0: invalidation=f'выход из диапазона {low:.2f}–{high:.2f} с удержанием'

    effective_edge = min(95.0, round(dom,1))
    edge_label = 'WATCH'
    if effective_edge >= 65: edge_label = 'STRONG'
    elif effective_edge >= 42: edge_label = 'WORKABLE'
    elif effective_edge >= 20: edge_label = 'BUILDING'
    elif direction != 'NEUTRAL': edge_label = 'SETUP'
    return {
        'state': state, 'action': action, 'direction': direction,
        'edge_score': effective_edge, 'edge_label': edge_label,
        'summary': summary, 'setup_note': setup_note, 'entry_hint': entry_hint,
        'invalidation': invalidation, 'why': reasons[:5],
        'scores': {'long': round(long_score,1), 'short': round(short_score,1)},
        'impulse_state': move_state,
        'fake_move_state': acceptance if trap_side == 'NONE' else f'TRAP_{trap_side}',
        'liquidity_pressure': liq_pressure,
        'grid_action': grid_action,
    }
