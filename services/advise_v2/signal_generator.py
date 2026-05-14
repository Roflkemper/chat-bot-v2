from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from .ban_filter import filter_banned_patterns
from .recommendation_builder import build_recommendation
from .schemas import (
    AlternativeAction,
    CurrentExposure,
    MarketContext,
    PlaybookCheck,
    SignalEnvelope,
)
from .setup_matcher import SetupMatch, match_setups
from .trend_handler import compute_trend_handling

MIN_CONFIDENCE_THRESHOLD = 0.5


def generate_signal(
    market_context: MarketContext,
    current_exposure: CurrentExposure,
    *,
    signal_counter: int = 1,
) -> Optional[SignalEnvelope]:
    """
    Orchestrate the 4-layer signal generation pipeline.

    Note: this function is pure except for `datetime.now(timezone.utc)`,
    which is used to stamp `ts` and `signal_id`.
    """
    all_matches = match_setups(market_context, current_exposure)
    legal_matches = filter_banned_patterns(all_matches)
    if not legal_matches:
        return None

    top = legal_matches[0]
    if top.confidence < MIN_CONFIDENCE_THRESHOLD:
        return None

    trend = compute_trend_handling(market_context, current_exposure)
    recommendation = build_recommendation(
        top_match=top,
        market_context=market_context,
        current_exposure=current_exposure,
        trend_handling=trend,
    )

    now = datetime.now(timezone.utc)
    signal_id = f"adv_{now.strftime('%Y-%m-%d_%H%M%S')}_{signal_counter:03d}"

    setup_name_map = {
        "P-1": "Range fade short",
        "P-2": "Reversal long after liq cascade",
        "P-3": "Trend continuation short after pullback",
        "P-4": "Trend continuation long after pullback",
        "P-6": "Reversal short after liq cascade up",
        "P-7": "Range fade long",
        "P-9": "Breakout long",
        "P-11": "Range continuation long",
        "P-12": "Range continuation short",
    }
    setup_name = setup_name_map.get(top.pattern_id, "Unknown")

    playbook_check = PlaybookCheck(
        matched_pattern=top.pattern_id,
        hard_ban_check="passed",
        similar_setups_last_30d=[],
        note=(
            "expected_outcome не указан — manual setup parameters "
            "не валидированы по backtest. См. TZ-ADVISE-PARAMS-VALIDATION."
        ),
    )

    alternatives = [
        AlternativeAction(
            action=f"consider_{match.pattern_id}",
            rationale=f"alternative pattern, confidence {match.confidence:.2f}",
            score=match.confidence,
        )
        for match in legal_matches[1:5]
    ]
    if not alternatives:
        alternatives = [
            AlternativeAction(
                action="do_nothing",
                rationale="no other patterns matched above threshold",
                score=0.5,
            )
        ]

    return SignalEnvelope(
        signal_id=signal_id,
        ts=now,
        setup_id=top.pattern_id,
        setup_name=setup_name,
        market_context=market_context,
        current_exposure=current_exposure,
        recommendation=recommendation,
        playbook_check=playbook_check,
        alternatives_considered=alternatives,
        trend_handling=trend,
    )
