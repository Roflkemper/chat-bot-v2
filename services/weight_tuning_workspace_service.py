from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from services.batch_case_analyzer_service import build_batch_summary, discover_case_dirs


RULES = {
    "REVERSAL_NEUTRAL_SIGNAL": {
        "component": "reversal",
        "problem": "reversal виден, но главный signal остаётся neutral",
        "recommendation": "поднять приоритет reversal перед neutral-gating и уменьшить порог force-direction для сильного rejection",
    },
    "REVERSAL_NEUTRAL_FINAL": {
        "component": "decision",
        "problem": "reversal виден, но final_decision остаётся neutral",
        "recommendation": "дать decision engine override от reversal при confidence выше рабочего порога",
    },
    "FORECAST_DECISION_NEUTRAL": {
        "component": "decision",
        "problem": "forecast уже направленный, а decision ещё neutral",
        "recommendation": "ослабить neutral gate внутри decision layer и использовать forecast как вторичный directional voter",
    },
    "SIGNAL_FINAL_DISAGREE": {
        "component": "decision",
        "problem": "signal и final_decision расходятся",
        "recommendation": "нормализовать иерархию signal → decision и логировать, какой слой перебил другой",
    },
    "REVERSAL_FORECAST_CONFLICT": {
        "component": "reversal_vs_forecast",
        "problem": "reversal конфликтует с forecast",
        "recommendation": "ввести penalty matrix: early reversal должен ослаблять continuation forecast, а не просто конфликтовать без вывода",
    },
    "REVERSAL_DECISION_CONFLICT": {
        "component": "reversal_vs_decision",
        "problem": "reversal конфликтует с decision.direction",
        "recommendation": "добавить явный confluence weight для reversal внутри decision/confluence engine",
    },
    "RANGE_MID_SUPPRESSION": {
        "component": "range",
        "problem": "range mid слишком часто гасит направленный контекст",
        "recommendation": "снизить силу neutral suppression от range mid или разрешить override от reversal/setup/structure",
    },
    "CT_VS_REVERSAL_SHORT": {
        "component": "countertrend",
        "problem": "CT bounce конфликтует с short reversal",
        "recommendation": "уменьшить влияние bounce-эвристики при наличии bearish rejection / false breakout up",
    },
    "CT_VS_REVERSAL_LONG": {
        "component": "countertrend",
        "problem": "CT bearish bias конфликтует с long reversal",
        "recommendation": "уменьшить медвежий CT bias при bullish rejection / false breakout down",
    },
    "REVERSAL_PATTERNS_NO_BIAS": {
        "component": "reversal",
        "problem": "паттерны reversal есть, но явный bias не формируется",
        "recommendation": "нормализовать mapping паттернов в long/short bias и ввести минимальный score floor для сильных паттернов",
    },
}


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {}


def _normalize_conflict_codes(case_dir: Path) -> list[str]:
    pack = _load_json(case_dir / 'comparison_pack.json')
    codes: list[str] = []
    for entry in (pack.get('conflicts') or []):
        if isinstance(entry, dict):
            code = str(entry.get('code') or '').strip()
            if code:
                codes.append(code)
    if codes:
        return codes

    # fallback for older comparison packs without top-level conflict objects
    for tf_data in (pack.get('timeframes') or {}).values():
        for text in tf_data.get('internal_conflicts') or []:
            t = str(text).lower()
            if 'reversal' in t and 'signal' in t and 'нейтраль' in t:
                codes.append('REVERSAL_NEUTRAL_SIGNAL')
            elif 'reversal' in t and 'final_decision' in t and 'нейтраль' in t:
                codes.append('REVERSAL_NEUTRAL_FINAL')
            elif 'forecast' in t and 'decision' in t and 'нейтраль' in t:
                codes.append('FORECAST_DECISION_NEUTRAL')
            elif 'signal' in t and 'final_decision' in t and 'разные стороны' in t:
                codes.append('SIGNAL_FINAL_DISAGREE')
            elif 'reversal и forecast' in t:
                codes.append('REVERSAL_FORECAST_CONFLICT')
            elif 'reversal и decision' in t:
                codes.append('REVERSAL_DECISION_CONFLICT')
            elif 'range mid' in t or 'середина диапазона' in t:
                codes.append('RANGE_MID_SUPPRESSION')
            elif 'bounce' in t and 'short-rejection' in t:
                codes.append('CT_VS_REVERSAL_SHORT')
            elif 'медвеж' in t and 'long-rejection' in t:
                codes.append('CT_VS_REVERSAL_LONG')
            elif 'patterns' in t and 'bias' in t:
                codes.append('REVERSAL_PATTERNS_NO_BIAS')
    return codes


def build_weight_tuning_workspace(cases_dir: str | Path) -> dict[str, Any]:
    base_dir = Path(cases_dir)
    case_dirs = discover_case_dirs(base_dir)
    batch_summary = build_batch_summary(case_dirs)

    code_counts: dict[str, int] = {}
    component_counts: dict[str, int] = {}
    affected_cases: dict[str, list[str]] = {}

    for case_dir in case_dirs:
        seen_in_case: set[str] = set()
        for code in _normalize_conflict_codes(case_dir):
            code_counts[code] = code_counts.get(code, 0) + 1
            rule = RULES.get(code)
            component = (rule or {}).get('component', 'other')
            if component not in seen_in_case:
                component_counts[component] = component_counts.get(component, 0) + 1
                seen_in_case.add(component)
            affected_cases.setdefault(code, []).append(case_dir.name)

    total_cases = max(len(case_dirs), 1)
    ranked_issues: list[dict[str, Any]] = []
    for code, count in sorted(code_counts.items(), key=lambda kv: (-kv[1], kv[0])):
        rule = RULES.get(code, {})
        pressure = round((count / total_cases) * 100.0, 1)
        ranked_issues.append({
            'code': code,
            'count': count,
            'pressure_pct': pressure,
            'component': rule.get('component', 'other'),
            'problem': rule.get('problem', 'unclassified conflict'),
            'recommendation': rule.get('recommendation', 'review this conflict manually'),
            'sample_cases': affected_cases.get(code, [])[:5],
        })

    component_pressure = [
        {
            'component': component,
            'cases': count,
            'pressure_pct': round((count / total_cases) * 100.0, 1),
        }
        for component, count in sorted(component_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]

    tuning_board = {
        'range_mid_suppression': 'reduce' if code_counts.get('RANGE_MID_SUPPRESSION', 0) else 'keep',
        'reversal_priority': 'increase' if (code_counts.get('REVERSAL_NEUTRAL_SIGNAL', 0) + code_counts.get('REVERSAL_NEUTRAL_FINAL', 0)) else 'keep',
        'countertrend_influence': 'reduce' if (code_counts.get('CT_VS_REVERSAL_SHORT', 0) + code_counts.get('CT_VS_REVERSAL_LONG', 0)) else 'keep',
        'decision_neutral_gate': 'reduce' if code_counts.get('FORECAST_DECISION_NEUTRAL', 0) else 'keep',
        'signal_decision_alignment': 'tighten' if code_counts.get('SIGNAL_FINAL_DISAGREE', 0) else 'keep',
        'reversal_pattern_mapping': 'tighten' if code_counts.get('REVERSAL_PATTERNS_NO_BIAS', 0) else 'keep',
    }

    return {
        'workspace_version': '4.5',
        'cases_dir': str(base_dir),
        'total_cases': len(case_dirs),
        'batch_summary': batch_summary,
        'component_pressure': component_pressure,
        'ranked_issues': ranked_issues,
        'tuning_board': tuning_board,
        'next_actions': [
            'Сначала исправляй компоненты с самым высоким pressure_pct.',
            'После каждой серии правок прогони replay по спорным кейсам и затем batch analyzer по всей папке кейсов.',
            'Не меняй больше 1-2 блоков весов за один цикл, иначе будет сложно понять, что реально помогло.',
        ],
    }


def render_weight_tuning_workspace_text(workspace: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append('WEIGHT TUNING WORKSPACE')
    lines.append('')
    lines.append(f"workspace version: {workspace.get('workspace_version')}")
    lines.append(f"cases dir: {workspace.get('cases_dir')}")
    lines.append(f"total cases: {workspace.get('total_cases', 0)}")
    lines.append('')

    lines.append('TUNING BOARD:')
    for key, value in (workspace.get('tuning_board') or {}).items():
        lines.append(f"- {key}: {value}")
    lines.append('')

    lines.append('COMPONENT PRESSURE:')
    component_pressure = workspace.get('component_pressure') or []
    if component_pressure:
        for item in component_pressure:
            lines.append(f"- {item.get('component')}: {item.get('cases')} cases ({item.get('pressure_pct')}%)")
    else:
        lines.append('- no recurring pressure found yet')
    lines.append('')

    lines.append('TOP ISSUES:')
    ranked = workspace.get('ranked_issues') or []
    if ranked:
        for item in ranked[:10]:
            lines.append(f"- {item.get('code')}: {item.get('count')} cases ({item.get('pressure_pct')}%)")
            lines.append(f"  component: {item.get('component')}")
            lines.append(f"  problem: {item.get('problem')}")
            lines.append(f"  recommendation: {item.get('recommendation')}")
            sample_cases = item.get('sample_cases') or []
            if sample_cases:
                lines.append(f"  sample cases: {', '.join(sample_cases)}")
    else:
        lines.append('- not enough recurring conflicts yet')
    lines.append('')

    lines.append('NEXT ACTIONS:')
    for item in workspace.get('next_actions') or []:
        lines.append(f"- {item}")
    return '\n'.join(lines).strip() + '\n'
