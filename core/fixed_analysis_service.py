from __future__ import annotations

import logging
import time
import traceback
from typing import Any, Callable, Dict, List

from utils.observability import RequestTrace
from models.snapshots import AnalysisSnapshot
from core.data_loader import get_klines_cache_info
from core.import_compat import (
    load_btc_analyzer,
    load_ginarea_analyzer,
    load_range_analyzer,
    normalize_analysis_payload,
)

try:
    from core.decision_engine import combine_trade_decision
except Exception:
    combine_trade_decision = None

logger = logging.getLogger(__name__)
DEFAULT_TF = "1h"


class AnalysisRequestContext:
    def __init__(self, trace: RequestTrace | None = None) -> None:
        self._analysis_cache: Dict[str, AnalysisSnapshot] = {}
        self.started_at = time.time()
        self.trace = trace

    def get_snapshot(self, timeframe: str) -> AnalysisSnapshot:
        tf = timeframe or DEFAULT_TF
        if tf not in self._analysis_cache:
            self._analysis_cache[tf] = call_btc_analysis(tf)
            if self.trace is not None:
                self.trace.mark(f"analysis:{tf}")
        return self._analysis_cache[tf]

    def get_analysis(self, timeframe: str) -> Dict[str, Any]:
        return self.get_snapshot(timeframe).to_dict()

    def has_snapshot(self, timeframe: str) -> bool:
        tf = timeframe or DEFAULT_TF
        return tf in self._analysis_cache

    def summary_lines(self) -> List[str]:
        elapsed_ms = int((time.time() - self.started_at) * 1000)
        cache_info = get_klines_cache_info()
        lines = [
            f"request time: {elapsed_ms} ms",
            f"analysis snapshots in request: {len(self._analysis_cache)}",
            f"market cache ttl: {int(cache_info.get('ttl_seconds') or 0)} sec",
            f"market cache entries: {int(cache_info.get('entries') or 0)}",
        ]
        if self.trace is not None:
            lines.insert(0, f"request id: {self.trace.request_id}")
            lines.append(f"request marks: {self.trace.marks_text()}")
        return lines


def normalize_tf(text: str) -> str:
    t = (text or "").lower()
    if "5m" in t:
        return "5m"
    if "15m" in t:
        return "15m"
    if "4h" in t:
        return "4h"
    if "1d" in t:
        return "1d"
    return "1h"


def try_call_variants(func: Callable, variants: List[Callable[[], Any]]) -> Dict[str, Any]:
    last_error = None
    for caller in variants:
        try:
            return {"ok": True, "result": caller(), "error": None}
        except Exception as exc:
            last_error = exc
    return {
        "ok": False,
        "result": None,
        "error": f"{type(last_error).__name__}: {last_error}" if last_error else "unknown error",
    }


def build_minimal_fallback(symbol: str, timeframe: str) -> Dict[str, Any]:
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "price": None,
        "signal": "НЕЙТРАЛЬНО",
        "final_decision": "ЖДАТЬ",
        "forecast_direction": "НЕЙТРАЛЬНО",
        "forecast_confidence": None,
        "reversal_signal": "NO_REVERSAL",
        "reversal_confidence": 0.0,
        "reversal_patterns": [],
        "range_state": "не определено",
        "range_low": None,
        "range_mid": None,
        "range_high": None,
        "ct_now": "нет данных",
        "ginarea_advice": "нет данных",
        "decision_summary": "",
        "analysis": {},
        "stats": {},
    }


def enrich_range_fallback(data: Dict[str, Any]) -> Dict[str, Any]:
    low = data.get("range_low")
    mid = data.get("range_mid")
    high = data.get("range_high")
    price = data.get("price")
    if mid is None and low is not None and high is not None:
        data["range_mid"] = (float(low) + float(high)) / 2.0
    if low is None and mid is None and high is None and price is not None:
        p = float(price)
        data["range_low"] = p * 0.992
        data["range_mid"] = p
        data["range_high"] = p * 1.008
        data.setdefault("range_state", "fallback range")
    data.setdefault("range_state", "не определено")
    return data


def enrich_with_decision(data: Dict[str, Any]) -> Dict[str, Any]:
    normalized = normalize_analysis_payload(data)
    if combine_trade_decision is None:
        return normalized
    try:
        return combine_trade_decision(normalized)
    except Exception:
        normalized["decision_engine_error"] = traceback.format_exc()[:1000]
        return normalized


def call_btc_analysis(timeframe: str) -> AnalysisSnapshot:
    symbol = "BTCUSDT"
    logger.info("analysis.start symbol=%s timeframe=%s", symbol, timeframe)
    merged = build_minimal_fallback(symbol, timeframe)

    loaders = [
        (load_btc_analyzer(), None),
        (
            load_range_analyzer(),
            ["range_low", "range_mid", "range_high", "range_state", "range_position"],
        ),
        (
            load_ginarea_analyzer(),
            [
                "ginarea_advice",
                "ct_now",
                "final_decision",
                "forecast_direction",
                "forecast_confidence",
                "signal",
                "entry_zone",
                "stop_loss",
                "take_profit",
                "range_low",
                "range_mid",
                "range_high",
                "range_state",
                "decision_summary",
            ],
        ),
    ]

    for loader, keys in loaders:
        if loader is None:
            continue

        res = try_call_variants(
            loader,
            [
                lambda l=loader: l(symbol, timeframe),
                lambda l=loader: l(symbol=symbol, timeframe=timeframe),
                lambda l=loader: l(timeframe=timeframe),
                lambda l=loader: l(symbol),
                lambda l=loader: l(),
            ],
        )

        if not res["ok"]:
            logger.warning(
                "analysis.loader_failed symbol=%s timeframe=%s loader=%s error=%s",
                symbol,
                timeframe,
                getattr(loader, "__name__", repr(loader)),
                res["error"],
            )
            continue

        payload = normalize_analysis_payload(res["result"], symbol=symbol, timeframe=timeframe)
        if keys is None:
            merged.update(payload)
        else:
            for key in keys:
                if payload.get(key) is not None:
                    merged[key] = payload.get(key)

    merged = normalize_analysis_payload(merged, symbol=symbol, timeframe=timeframe)
    merged = enrich_range_fallback(merged)
    merged = enrich_with_decision(merged)

    logger.info(
        "analysis.done symbol=%s timeframe=%s signal=%s final_decision=%s",
        symbol,
        timeframe,
        merged.get("signal"),
        merged.get("final_decision"),
    )
    return AnalysisSnapshot.from_dict(merged, symbol=symbol, timeframe=timeframe)
