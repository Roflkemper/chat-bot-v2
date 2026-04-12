from __future__ import annotations

from typing import Dict


def build_expectancy_context(ml_v2: Dict, pattern_ctx: Dict, backtest_v2: Dict, personal_stats: Dict) -> Dict:
    ml_prob = float(ml_v2.get('probability', 0.5))
    pattern_long = float(pattern_ctx.get('long_prob', 50.0)) / 100.0
    pattern_short = float(pattern_ctx.get('short_prob', 50.0)) / 100.0
    mfe = float(backtest_v2.get('mfe', 0.0))
    mae = float(backtest_v2.get('mae', 0.0))
    personal_edge = float(personal_stats.get('avg_rr', 0.0))

    exp_long = ((ml_prob - 0.5) * 1.2) + ((pattern_long - 0.5) * 0.9) + (mfe * 0.08) - (mae * 0.08) + (personal_edge * 0.35)
    exp_short = (((1.0 - ml_prob) - 0.5) * 1.2) + ((pattern_short - 0.5) * 0.9) + (mfe * 0.08) - (mae * 0.08) + (personal_edge * 0.35)

    best_side = 'FLAT'
    if exp_long > exp_short and exp_long > 0:
        best_side = 'LONG'
    elif exp_short > exp_long and exp_short > 0:
        best_side = 'SHORT'

    summary = f"exp_long={exp_long:.3f}, exp_short={exp_short:.3f}, best={best_side}"
    return {'exp_long': round(exp_long, 4), 'exp_short': round(exp_short, 4), 'best_side': best_side, 'summary': summary}
