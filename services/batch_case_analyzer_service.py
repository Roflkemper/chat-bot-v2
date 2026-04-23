from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {}


def _read_text(path: Path) -> str:
    if not path.exists():
        return ''
    try:
        return path.read_text(encoding='utf-8', errors='ignore')
    except Exception:
        return ''


def discover_case_dirs(base_dir: Path) -> list[Path]:
    if not base_dir.exists():
        return []
    candidates: list[Path] = []
    for child in sorted(base_dir.iterdir()):
        if not child.is_dir():
            continue
        if child.name.startswith('btc_case_') or child.name.startswith('btc_debug_export_'):
            candidates.append(child)
            continue
        if (child / 'analysis_snapshots.json').exists() or (child / 'comparison_pack.json').exists():
            candidates.append(child)
    return candidates


def _extract_expectation(case_dir: Path) -> dict[str, Any]:
    expectation = _load_json(case_dir / 'trader_expectation.json')
    if expectation:
        return expectation
    template = _load_json(case_dir / 'trader_expectation_template.json')
    return template or {}


def summarize_case(case_dir: Path) -> dict[str, Any]:
    comparison = _load_json(case_dir / 'comparison_pack.json')
    manifest = _load_json(case_dir / 'replay_manifest.json')
    expectation = _extract_expectation(case_dir)
    summary_txt = _read_text(case_dir / 'comparison_summary.txt')

    baseline = manifest.get('baseline_snapshots') or {}
    tf_preference = expectation.get('timeframe') or next(iter(baseline.keys()), 'unknown')
    baseline_tf = baseline.get(tf_preference) or {}

    conflicts = comparison.get('conflicts') or []
    conflict_codes = [str(item.get('code')) for item in conflicts if isinstance(item, dict)]
    internal_conflict_count = len(conflicts)

    expected_direction = expectation.get('expected_direction') or expectation.get('direction') or expectation.get('bias')
    actual_signal = baseline_tf.get('signal') or baseline_tf.get('final_decision')
    actual_decision_direction = ((baseline_tf.get('decision') or {}).get('direction')) if isinstance(baseline_tf.get('decision'), dict) else None
    reversal_signal = baseline_tf.get('reversal_signal')
    range_state = baseline_tf.get('range_state')
    ct_now = baseline_tf.get('ct_now')

    mismatch_expected = bool(expected_direction and str(expected_direction).upper() not in str(actual_signal).upper() and str(expected_direction).upper() not in str(actual_decision_direction).upper())

    return {
        'case_name': case_dir.name,
        'path': str(case_dir),
        'timeframe': tf_preference,
        'expected_direction': expected_direction,
        'actual_signal': actual_signal,
        'actual_decision_direction': actual_decision_direction,
        'reversal_signal': reversal_signal,
        'range_state': range_state,
        'ct_now': ct_now,
        'internal_conflict_count': internal_conflict_count,
        'conflict_codes': conflict_codes,
        'expected_mismatch': mismatch_expected,
        'summary_excerpt': summary_txt[:500].strip(),
    }


def build_batch_summary(case_dirs: Iterable[Path]) -> dict[str, Any]:
    cases = [summarize_case(case_dir) for case_dir in case_dirs]

    total = len(cases)
    mismatches = sum(1 for case in cases if case.get('expected_mismatch'))
    internal_conflicts = sum(1 for case in cases if (case.get('internal_conflict_count') or 0) > 0)

    by_timeframe: dict[str, int] = {}
    conflict_code_counts: dict[str, int] = {}
    range_state_counts: dict[str, int] = {}
    for case in cases:
        tf = str(case.get('timeframe') or 'unknown')
        by_timeframe[tf] = by_timeframe.get(tf, 0) + 1
        rs = str(case.get('range_state') or 'unknown')
        range_state_counts[rs] = range_state_counts.get(rs, 0) + 1
        for code in case.get('conflict_codes') or []:
            conflict_code_counts[code] = conflict_code_counts.get(code, 0) + 1

    top_conflicts = sorted(conflict_code_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return {
        'total_cases': total,
        'expected_direction_mismatches': mismatches,
        'cases_with_internal_conflicts': internal_conflicts,
        'by_timeframe': by_timeframe,
        'range_state_counts': range_state_counts,
        'top_conflicts': [{'code': code, 'count': count} for code, count in top_conflicts],
        'cases': cases,
    }


def render_batch_summary_text(summary: dict[str, Any]) -> str:
    lines = []
    lines.append('BATCH CASE ANALYZER')
    lines.append('')
    lines.append(f"cases total: {summary.get('total_cases', 0)}")
    lines.append(f"expected direction mismatches: {summary.get('expected_direction_mismatches', 0)}")
    lines.append(f"cases with internal conflicts: {summary.get('cases_with_internal_conflicts', 0)}")
    lines.append('')

    lines.append('BY TIMEFRAME:')
    for tf, count in sorted((summary.get('by_timeframe') or {}).items()):
        lines.append(f"- {tf}: {count}")
    lines.append('')

    lines.append('TOP INTERNAL CONFLICTS:')
    top_conflicts = summary.get('top_conflicts') or []
    if top_conflicts:
        for item in top_conflicts[:10]:
            lines.append(f"- {item.get('code')}: {item.get('count')}")
    else:
        lines.append('- none')
    lines.append('')

    lines.append('CASE LIST:')
    for case in summary.get('cases') or []:
        lines.append(f"- {case.get('case_name')} | tf={case.get('timeframe')} | expected={case.get('expected_direction')} | signal={case.get('actual_signal')} | decision={case.get('actual_decision_direction')} | conflicts={case.get('internal_conflict_count')}")
    return '\n'.join(lines).strip() + '\n'
