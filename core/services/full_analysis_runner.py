from __future__ import annotations

from typing import Any, Dict

from services.analysis_service import call_btc_analysis
from renderers.telegram_renderers import build_base_analysis_text


def run_full_analysis(symbol: str = 'BTCUSDT', timeframe: str = '1h', df=None, structure=None, range_info=None) -> Dict[str, Any]:
    snapshot = call_btc_analysis(timeframe)
    analysis = snapshot.to_dict() if hasattr(snapshot, 'to_dict') else dict(snapshot)
    text = build_base_analysis_text(analysis, default_tf=timeframe)
    return {'analysis': analysis, 'decision': analysis.get('decision', {}), 'text': text}
