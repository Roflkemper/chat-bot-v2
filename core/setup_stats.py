from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from storage.personal_bot_learning import load_personal_bot_learning

BOT_LABELS = {
    'ct_long': 'CT LONG',
    'ct_short': 'CT SHORT',
    'range_long': 'RANGE LONG',
    'range_short': 'RANGE SHORT',
}

FAMILY_LABELS = {
    'FAKE_UP_FADE': 'fake up fade',
    'FAKE_DOWN_FADE': 'fake down fade',
    'RECLAIM_CONTINUATION': 'reclaim continuation',
    'RANGE_FADE': 'range fade',
    'BREAKOUT_FAILURE': 'breakout failure',
    'POST_LIQUIDATION_REVERSAL': 'post-liquidation reversal',
    'UNKNOWN': 'unknown',
}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def _read_jsonl(path: str | Path) -> List[Dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    rows: List[Dict[str, Any]] = []
    try:
        with p.open('r', encoding='utf-8') as f:
            for line in f:
                text = line.strip()
                if not text:
                    continue
                try:
                    row = json.loads(text)
                except Exception:
                    continue
                if isinstance(row, dict):
                    rows.append(row)
    except Exception:
        return []
    return rows


def _bot_side(bot_key: str) -> str:
    key = str(bot_key or '').lower()
    if key.endswith('long'):
        return 'LONG'
    if key.endswith('short'):
        return 'SHORT'
    return 'NEUTRAL'


def _setup_score(samples: int, winrate: float, avg_rr: float) -> float:
    sample_factor = min(1.0, max(0.15, samples / 10.0))
    return round(((winrate - 0.5) * 0.8 + avg_rr * 0.35) * sample_factor, 4)


def _top_bucket(d: Dict[str, Any]) -> Tuple[str, int]:
    if not isinstance(d, dict) or not d:
        return ('нет данных', 0)
    best = max(((str(k), _safe_int(v)) for k, v in d.items()), key=lambda kv: kv[1])
    return best


def _flatten_text(value: Any) -> str:
    if isinstance(value, dict):
        return ' '.join(_flatten_text(v) for v in value.values())
    if isinstance(value, (list, tuple, set)):
        return ' '.join(_flatten_text(v) for v in value)
    return str(value or '')


def _classify_setup_family(row: Dict[str, Any]) -> str:
    text = _flatten_text(row).lower()
    if any(k in text for k in ('post_liquidation', 'post liquidation', 'liquidation reversal', 'liquidation trap', 'liquidation sweep')):
        return 'POST_LIQUIDATION_REVERSAL'
    if any(k in text for k in ('fake up', 'fake_up', 'failed up sweep', 'false break up', 'bear trap above', 'upper fakeout')):
        return 'FAKE_UP_FADE'
    if any(k in text for k in ('fake down', 'fake_down', 'failed down sweep', 'false break down', 'bull trap below', 'lower fakeout')):
        return 'FAKE_DOWN_FADE'
    if any(k in text for k in ('reclaim continuation', 'reclaim + continuation', 'acceptance', 'accepted breakout', 'retest hold', 'continuation after reclaim')):
        return 'RECLAIM_CONTINUATION'
    if any(k in text for k in ('breakout failure', 'failed breakout', 'failed continuation', 'reclaim failed', 'acceptance failed')):
        return 'BREAKOUT_FAILURE'
    if any(k in text for k in ('range fade', 'upper-range', 'lower-range', 'mean reversion', 'range short', 'range long', 'fade from high', 'fade from low')):
        return 'RANGE_FADE'
    return 'UNKNOWN'


def _extract_result_metrics(row: Dict[str, Any]) -> Tuple[float, float, bool]:
    result_pct = _safe_float(row.get('result_pct'))
    result_rr = _safe_float(row.get('result_rr'))
    if result_rr == 0.0:
        result_rr = _safe_float(row.get('final_rr'))
    is_win = result_rr > 0.0 or result_pct > 0.15 or str(row.get('result') or '').upper() == 'WIN'
    return result_pct, result_rr, is_win


def _build_family_rows(trade_rows: List[Dict[str, Any]], decision_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    buckets: Dict[str, Dict[str, Any]] = {}
    for row in list(trade_rows) + list(decision_rows):
        if not isinstance(row, dict):
            continue
        family = _classify_setup_family(row)
        bucket = buckets.setdefault(family, {
            'family': family,
            'label': FAMILY_LABELS.get(family, family.lower()),
            'samples': 0,
            'wins': 0,
            'sum_rr': 0.0,
            'sum_result_pct': 0.0,
            'hold_quality_sum': 0.0,
            'failure_profile': {},
        })
        bucket['samples'] += 1
        result_pct, result_rr, is_win = _extract_result_metrics(row)
        bucket['sum_rr'] += result_rr
        bucket['sum_result_pct'] += result_pct
        if is_win:
            bucket['wins'] += 1
        hold_quality = row.get('holding_time_minutes')
        if hold_quality is None:
            hold_quality = row.get('holding_minutes')
        bucket['hold_quality_sum'] += max(0.0, _safe_float(hold_quality))
        failure = str(row.get('exit_reason') or row.get('failure_reason') or row.get('close_reason') or 'нет данных')
        fp = bucket['failure_profile']
        fp[failure] = fp.get(failure, 0) + 1
    out: List[Dict[str, Any]] = []
    for bucket in buckets.values():
        samples = max(1, bucket['samples'])
        winrate = bucket['wins'] / samples
        avg_rr = bucket['sum_rr'] / samples
        avg_result_pct = bucket['sum_result_pct'] / samples
        hold_quality = bucket['hold_quality_sum'] / samples
        top_failure, top_failure_count = _top_bucket(bucket['failure_profile'])
        out.append({
            'family': bucket['family'],
            'label': bucket['label'],
            'samples': samples,
            'winrate': round(winrate, 4),
            'avg_rr': round(avg_rr, 4),
            'avg_result_pct': round(avg_result_pct, 4),
            'hold_quality': round(hold_quality, 1),
            'failure_profile': top_failure,
            'failure_profile_count': top_failure_count,
            'edge_score': _setup_score(samples, winrate, avg_rr),
        })
    out.sort(key=lambda x: (x['edge_score'], x['winrate'], x['avg_rr'], x['samples']), reverse=True)
    return out


def _current_family(analysis: Dict[str, Any]) -> str:
    if not isinstance(analysis, dict):
        return 'UNKNOWN'
    return _classify_setup_family(analysis)


def _build_bot_rows(learning_state: Dict[str, Any]) -> List[Dict[str, Any]]:
    bots = learning_state.get('bots') if isinstance(learning_state.get('bots'), dict) else {}
    rows: List[Dict[str, Any]] = []
    for bot_key, payload in bots.items():
        if not isinstance(payload, dict):
            continue
        samples = _safe_int(payload.get('closed_trades'))
        wins = _safe_int(payload.get('wins'))
        losses = _safe_int(payload.get('losses'))
        be = _safe_int(payload.get('breakeven'))
        total = max(samples, wins + losses + be)
        winrate = (wins / total) if total > 0 else 0.0
        avg_rr = _safe_float(payload.get('avg_rr'))
        avg_result_pct = _safe_float(payload.get('avg_result_pct'))
        top_setup, top_setup_count = _top_bucket(payload.get('setup_qualities') or {})
        top_scenario, top_scenario_count = _top_bucket(payload.get('scenarios') or {})
        top_tf, top_tf_count = _top_bucket(payload.get('timeframes') or {})
        rows.append({
            'bot_key': bot_key,
            'bot_label': BOT_LABELS.get(bot_key, bot_key),
            'side': _bot_side(bot_key),
            'samples': total,
            'wins': wins,
            'losses': losses,
            'breakeven': be,
            'winrate': round(winrate, 4),
            'avg_rr': round(avg_rr, 4),
            'avg_result_pct': round(avg_result_pct, 4),
            'top_setup_quality': top_setup,
            'top_setup_quality_count': top_setup_count,
            'top_scenario': top_scenario,
            'top_scenario_count': top_scenario_count,
            'top_timeframe': top_tf,
            'top_timeframe_count': top_tf_count,
            'setup_score': _setup_score(total, winrate, avg_rr),
        })
    rows.sort(key=lambda x: (x['setup_score'], x['winrate'], x['avg_rr'], x['samples']), reverse=True)
    return rows


def _aggregate_side(rows: Iterable[Dict[str, Any]], side: str) -> Dict[str, Any]:
    items = [r for r in rows if str(r.get('side')) == side]
    total_samples = sum(_safe_int(r.get('samples')) for r in items)
    if total_samples <= 0:
        return {'side': side, 'samples': 0, 'winrate': 0.0, 'avg_rr': 0.0, 'edge_score': 0.0}
    weighted_winrate = sum(_safe_float(r.get('winrate')) * _safe_int(r.get('samples')) for r in items) / total_samples
    weighted_rr = sum(_safe_float(r.get('avg_rr')) * _safe_int(r.get('samples')) for r in items) / total_samples
    edge_score = _setup_score(total_samples, weighted_winrate, weighted_rr)
    return {
        'side': side,
        'samples': total_samples,
        'winrate': round(weighted_winrate, 4),
        'avg_rr': round(weighted_rr, 4),
        'edge_score': edge_score,
    }


def _build_recent_closed_summary(trade_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    closed = [r for r in trade_rows if isinstance(r, dict) and (r.get('closed') or r.get('exit_reason') or r.get('result_rr') is not None)]
    recent = closed[-20:]
    if not recent:
        return {'closed_trades_recent': 0, 'recent_winrate': 0.0, 'recent_avg_rr': 0.0, 'recent_avg_result_pct': 0.0}
    wins = sum(1 for r in recent if _extract_result_metrics(r)[2])
    avg_rr = sum(_extract_result_metrics(r)[1] for r in recent) / max(1, len(recent))
    avg_res = sum(_extract_result_metrics(r)[0] for r in recent) / max(1, len(recent))
    return {
        'closed_trades_recent': len(recent),
        'recent_winrate': round(wins / len(recent), 4),
        'recent_avg_rr': round(avg_rr, 4),
        'recent_avg_result_pct': round(avg_res, 4),
    }


def build_setup_stats_context(analysis: Dict[str, Any] | None = None, trade_journal_path: str = 'state/trade_journal.jsonl', decision_journal_path: str = 'state/decision_journal.jsonl') -> Dict[str, Any]:
    analysis = analysis if isinstance(analysis, dict) else {}
    learning_state = load_personal_bot_learning()
    bot_rows = _build_bot_rows(learning_state)
    long_side = _aggregate_side(bot_rows, 'LONG')
    short_side = _aggregate_side(bot_rows, 'SHORT')
    favored_side = 'NEUTRAL'
    if long_side['edge_score'] > short_side['edge_score'] + 0.02 and long_side['samples'] >= 2:
        favored_side = 'LONG'
    elif short_side['edge_score'] > long_side['edge_score'] + 0.02 and short_side['samples'] >= 2:
        favored_side = 'SHORT'

    active_bot = str(analysis.get('best_bot') or analysis.get('active_bot') or '').strip().lower()
    active_bot_row = next((r for r in bot_rows if r.get('bot_key') == active_bot), None)
    best_setup = bot_rows[0] if bot_rows else None
    weakest_setup = bot_rows[-1] if bot_rows else None

    trade_rows = _read_jsonl(trade_journal_path)
    decision_rows = _read_jsonl(decision_journal_path)
    recent = _build_recent_closed_summary(trade_rows)
    family_rows = _build_family_rows(trade_rows, decision_rows)
    current_family = _current_family(analysis)
    active_family = next((r for r in family_rows if r.get('family') == current_family), None)
    strongest_family = family_rows[0] if family_rows else None
    weakest_family = family_rows[-1] if family_rows else None

    summary = 'learning engine ещё не накопил достаточно кейсов'
    if active_family and active_family.get('samples', 0) >= 2:
        summary = (
            f"current family {active_family['label']} | samples {active_family['samples']} | "
            f"win {active_family['winrate'] * 100:.1f}% | avg RR {active_family['avg_rr']:.2f}"
        )
    elif active_bot_row and active_bot_row.get('samples', 0) >= 2:
        summary = (
            f"{active_bot_row['bot_label']}: {active_bot_row['samples']} closed | "
            f"win {active_bot_row['winrate'] * 100:.1f}% | avg RR {active_bot_row['avg_rr']:.2f}"
        )
    elif strongest_family and strongest_family.get('samples', 0) >= 2:
        summary = (
            f"best family {strongest_family['label']} | samples {strongest_family['samples']} | "
            f"win {strongest_family['winrate'] * 100:.1f}% | avg RR {strongest_family['avg_rr']:.2f}"
        )
    elif best_setup and best_setup.get('samples', 0) >= 2:
        summary = (
            f"исторически сильнее {best_setup['bot_label']} | "
            f"win {best_setup['winrate'] * 100:.1f}% | avg RR {best_setup['avg_rr']:.2f}"
        )

    return {
        'ready': any(_safe_int(r.get('samples')) >= 2 for r in bot_rows) or any(_safe_int(r.get('samples')) >= 2 for r in family_rows),
        'summary': summary,
        'favored_side': favored_side,
        'active_bot': active_bot_row,
        'best_setup': best_setup,
        'weakest_setup': weakest_setup,
        'top_setups': bot_rows[:4],
        'side_stats': {
            'LONG': long_side,
            'SHORT': short_side,
        },
        'decision_journal_samples': len(decision_rows),
        'family_rows': family_rows[:6],
        'active_family': active_family,
        'strongest_family': strongest_family,
        'weakest_family': weakest_family,
        'current_family': current_family,
        'learning_engine_ready': any(_safe_int(r.get('samples')) >= 2 for r in family_rows),
        **recent,
    }


def build_setup_learning_adjustment(setup_stats: Dict[str, Any], analysis: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(setup_stats, dict):
        return {'delta': 0.0, 'aggressiveness': 'NEUTRAL', 'reasons': [], 'summary': 'setup stats unavailable'}
    reasons: List[str] = []
    delta = 0.0
    direction = str((analysis.get('decision') or {}).get('direction') or '').upper()
    if direction not in {'LONG', 'SHORT'}:
        direction = str(analysis.get('final_decision') or '').upper()
    favored_side = str(setup_stats.get('favored_side') or 'NEUTRAL').upper()
    active = setup_stats.get('active_bot') if isinstance(setup_stats.get('active_bot'), dict) else None
    active_family = setup_stats.get('active_family') if isinstance(setup_stats.get('active_family'), dict) else None
    if favored_side in {'LONG', 'SHORT'} and direction in {'LONG', 'SHORT'}:
        if favored_side == direction:
            delta += 0.03
            reasons.append('личная статистика по закрытым сетапам поддерживает текущую сторону')
        else:
            delta -= 0.03
            reasons.append('исторически противоположная сторона у тебя работала лучше')
    if active and _safe_int(active.get('samples')) >= 2:
        wr = _safe_float(active.get('winrate'))
        rr = _safe_float(active.get('avg_rr'))
        if wr >= 0.58 and rr > 0.25:
            delta += 0.025
            reasons.append('активный бот имеет хороший personal track record')
        elif wr <= 0.42 or rr < -0.05:
            delta -= 0.025
            reasons.append('активный бот исторически слабее, лучше осторожность')
    if active_family and _safe_int(active_family.get('samples')) >= 2:
        wr = _safe_float(active_family.get('winrate'))
        rr = _safe_float(active_family.get('avg_rr'))
        if wr >= 0.58 and rr > 0.20:
            delta += 0.02
            reasons.append('текущий тип сетапа исторически у тебя держится лучше среднего')
        elif wr <= 0.42 or rr < -0.05:
            delta -= 0.02
            reasons.append('этот тип сетапа в истории у тебя чаще ломался')
    recent_winrate = _safe_float(setup_stats.get('recent_winrate'))
    recent_avg_rr = _safe_float(setup_stats.get('recent_avg_rr'))
    recent_samples = _safe_int(setup_stats.get('closed_trades_recent'))
    if recent_samples >= 3 and recent_winrate >= 0.60 and recent_avg_rr > 0.2:
        delta += 0.015
        reasons.append('последние закрытые сделки тоже в плюс по среднему RR')
    elif recent_samples >= 3 and recent_winrate <= 0.40 and recent_avg_rr < 0.0:
        delta -= 0.015
        reasons.append('последние закрытые сделки ухудшили статистику')
    delta = max(-0.10, min(0.10, delta))
    aggressiveness = 'NEUTRAL'
    if delta >= 0.04:
        aggressiveness = 'AGGRESSIVE_OK'
    elif delta <= -0.04:
        aggressiveness = 'SMALL_OR_WAIT'
    return {
        'delta': round(delta, 4),
        'aggressiveness': aggressiveness,
        'reasons': reasons[:4],
        'summary': str(setup_stats.get('summary') or 'нет данных'),
        'favored_side': favored_side,
        'active_bot_label': (active or {}).get('bot_label') if active else None,
        'active_family_label': (active_family or {}).get('label') if active_family else None,
    }



def build_learning_execution_plan(setup_stats: Dict[str, Any], setup_adj: Dict[str, Any], analysis: Dict[str, Any]) -> Dict[str, Any]:
    setup_stats = setup_stats if isinstance(setup_stats, dict) else {}
    setup_adj = setup_adj if isinstance(setup_adj, dict) else {}
    analysis = analysis if isinstance(analysis, dict) else {}

    decision = analysis.get('decision') if isinstance(analysis.get('decision'), dict) else {}
    direction = str(decision.get('direction') or analysis.get('final_decision') or 'NONE').upper()
    favored_side = str(setup_stats.get('favored_side') or 'NEUTRAL').upper()
    delta = _safe_float(setup_adj.get('delta'))
    strongest = setup_stats.get('strongest_family') if isinstance(setup_stats.get('strongest_family'), dict) else {}
    weakest = setup_stats.get('weakest_family') if isinstance(setup_stats.get('weakest_family'), dict) else {}
    active_family = setup_stats.get('active_family') if isinstance(setup_stats.get('active_family'), dict) else {}

    posture = 'NEUTRAL'
    size_mode = 'x1.00'
    execution = 'STANDARD'
    note = 'личная статистика пока не даёт сильной коррекции'

    if delta >= 0.04:
        posture = 'PRESS_IF_TRIGGER'
        size_mode = 'x1.15'
        execution = 'ALLOW_SMALL_ADD'
        note = 'история поддерживает сетап: можно чуть смелее, но только после триггера'
    elif delta >= 0.015:
        posture = 'FAVOR_IF_TRIGGER'
        size_mode = 'x1.05'
        execution = 'STANDARD_PLUS'
        note = 'история слегка поддерживает сценарий: можно держать стандартный план'
    elif delta <= -0.04:
        posture = 'SMALL_OR_WAIT'
        size_mode = 'x0.50'
        execution = 'NO_ADD'
        note = 'история против сетапа: размер снизить, без доборов'
    elif delta <= -0.015:
        posture = 'REDUCED'
        size_mode = 'x0.75'
        execution = 'REDUCED_SIZE'
        note = 'история слабее среднего: лучше консервативный размер'

    if favored_side in {'LONG', 'SHORT'} and direction in {'LONG', 'SHORT'} and favored_side != direction and delta > -0.015:
        posture = 'SIDE_CONFLICT'
        size_mode = 'x0.75'
        execution = 'REDUCED_SIZE'
        note = 'по личной статистике сильнее противоположная сторона: лучше осторожность'

    strongest_label = strongest.get('label') or strongest.get('family') or 'нет данных'
    weakest_label = weakest.get('label') or weakest.get('family') or 'нет данных'
    active_label = active_family.get('label') or active_family.get('family') or 'нет данных'
    reasons = list(setup_adj.get('reasons') or [])[:3]

    return {
        'posture': posture,
        'size_mode': size_mode,
        'execution': execution,
        'summary': note,
        'favored_side': favored_side,
        'active_family_label': active_label,
        'strongest_family_label': strongest_label,
        'weakest_family_label': weakest_label,
        'reasons': reasons,
        'delta_pct': round(delta * 100.0, 2),
    }
