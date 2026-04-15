from __future__ import annotations

from typing import Dict


def render_forecast_block(bundle: Dict[str, object], consensus: Dict[str, object]) -> str:
    short_term = bundle.get("short_term", {})
    session = bundle.get("session", {})
    medium = bundle.get("medium", {})

    parts = []
    parts.append("📈 ПРОГНОЗ")
    parts.append("")
    parts.append("СКАЛЬП:")
    parts.append(
        f"• вектор: {short_term.get('vector', 'NEUTRAL')} | сила: {short_term.get('strength_label', 'weak')}"
    )
    parts.append(
        f"• pressure proxy: {short_term.get('pressure_proxy_pct', 0)}% | direction_ratio: {short_term.get('direction_ratio', 0)}"
    )
    parts.append("")
    parts.append("СЕССИЯ:")
    parts.append(
        f"• контекст: {session.get('bias', 'NEUTRAL')} | {session.get('compression_label', 'normal')} ({session.get('compression_ratio', 1.0)})"
    )
    parts.append(
        f"• верхняя зона: {session.get('upper_zone', ('-', '-'))[0]}–{session.get('upper_zone', ('-', '-'))[1]}"
    )
    parts.append(
        f"• нижняя зона: {session.get('lower_zone', ('-', '-'))[0]}–{session.get('lower_zone', ('-', '-'))[1]}"
    )
    parts.append("")
    parts.append("СРЕДНЕСРОК:")
    parts.append(
        f"• фаза: {medium.get('phase', 'NEUTRAL')} | уклон: {medium.get('bias', 'NEUTRAL')}"
    )
    if medium.get("note"):
        parts.append(f"• примечание: {medium['note']}")
    parts.append("")
    parts.append("КОНСЕНСУС:")
    parts.append(
        f"• направление: {consensus.get('dominant', 'NEUTRAL')} | agreement: {consensus.get('agreement', 'CONFLICT')}"
    )
    if consensus.get("veto_note"):
        parts.append(f"• veto: {consensus['veto_note']}")
    if consensus.get("conflict_note"):
        parts.append(f"• конфликт: {consensus['conflict_note']}")
    return "\n".join(parts)
