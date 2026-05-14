from __future__ import annotations

import importlib
from typing import Any, Callable, Dict, Iterable, List, Optional


def safe_get(d: Any, key: str, default: Any = None) -> Any:
    if isinstance(d, dict):
        return d.get(key, default)
    return default


def first_not_none(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def deep_get(d: Any, path: Iterable[str], default: Any = None) -> Any:
    cur = d
    for key in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
        if cur is None:
            return default
    return cur


def to_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    if value is None:
        return default
    try:
        return float(value)
    except Exception:
        try:
            s = str(value).replace(" ", "").replace(",", ".")
            return float(s)
        except Exception:
            return default


def try_import_module(module_names: List[str]) -> Optional[Any]:
    for module_name in module_names:
        try:
            return importlib.import_module(module_name)
        except Exception:
            continue
    return None


def try_import_attr(module_names: List[str], attr_names: List[str]) -> Optional[Callable]:
    for module_name in module_names:
        try:
            module = importlib.import_module(module_name)
        except Exception:
            continue
        for attr_name in attr_names:
            if hasattr(module, attr_name):
                attr = getattr(module, attr_name)
                if callable(attr):
                    return attr
    return None


def normalize_direction(value: Any) -> str:
    if value is None:
        return "НЕЙТРАЛЬНО"
    s = str(value).strip().upper()
    mapping = {
        "BUY": "ЛОНГ", "LONG": "ЛОНГ", "BULLISH": "ЛОНГ", "UP": "ВВЕРХ", "UPWARD": "ВВЕРХ",
        "SELL": "ШОРТ", "SHORT": "ШОРТ", "BEARISH": "ШОРТ", "DOWN": "ВНИЗ", "DOWNWARD": "ВНИЗ",
        "FLAT": "ФЛЭТ", "RANGE": "ФЛЭТ", "NEUTRAL": "НЕЙТРАЛЬНО", "NO TRADE": "БЕЗ СДЕЛКИ",
        "NOTRADE": "БЕЗ СДЕЛКИ", "WAIT": "ЖДАТЬ", "HOLD": "ДЕРЖАТЬ", "CLOSE": "ЗАКРЫТЬ",
    }
    return mapping.get(s, str(value))


def normalize_confidence(value: Any) -> Optional[float]:
    v = to_float(value)
    if v is None:
        return None
    if v > 1.0:
        if v <= 100.0:
            return v / 100.0
        return 1.0
    if v < 0.0:
        return 0.0
    return v


def normalize_analysis_payload(raw: Any, symbol: str = "BTCUSDT", timeframe: str = "1h") -> Dict[str, Any]:
    if raw is None:
        return {"symbol": symbol, "timeframe": timeframe, "error": "empty_analysis"}
    data = dict(raw) if isinstance(raw, dict) else {"raw_analysis": raw}
    data.setdefault("symbol", symbol)
    data.setdefault("timeframe", timeframe)
    data["price"] = first_not_none(data.get("price"), data.get("last_price"), data.get("current_price"), data.get("close"), deep_get(data, ["market", "price"]))
    data["signal"] = first_not_none(data.get("signal"), data.get("final_signal"), data.get("decision"), data.get("direction"), data.get("market_bias"))
    data["final_decision"] = first_not_none(data.get("final_decision"), data.get("decision_text"), data.get("final_signal"), data.get("signal"))
    data["forecast_direction"] = first_not_none(data.get("forecast_direction"), data.get("probable_direction"), data.get("market_direction"), data.get("direction"))
    data["forecast_confidence"] = first_not_none(data.get("forecast_confidence"), data.get("confidence"), data.get("probability"), data.get("ml_probability"), data.get("prob"))
    data["entry_zone"] = first_not_none(data.get("entry_zone"), data.get("entry"), data.get("recommended_entry"))
    data["take_profit"] = first_not_none(data.get("take_profit"), data.get("tp"), data.get("target"), data.get("targets"))
    data["stop_loss"] = first_not_none(data.get("stop_loss"), data.get("sl"), data.get("invalidation"))
    data["range_low"] = first_not_none(data.get("range_low"), deep_get(data, ["range", "range_low"]), deep_get(data, ["range", "low"]), deep_get(data, ["range_info", "range_low"]))
    data["range_high"] = first_not_none(data.get("range_high"), deep_get(data, ["range", "range_high"]), deep_get(data, ["range", "high"]), deep_get(data, ["range_info", "range_high"]))
    data["range_mid"] = first_not_none(data.get("range_mid"), deep_get(data, ["range", "range_mid"]), deep_get(data, ["range", "mid"]), deep_get(data, ["range_info", "range_mid"]))
    data["range_state"] = first_not_none(data.get("range_state"), data.get("range_mode"), data.get("market_state"), deep_get(data, ["range", "state"]), deep_get(data, ["range", "mode"]))
    data["ct_now"] = first_not_none(data.get("ct_now"), data.get("countertrend_now"), data.get("countertrend_advice"))
    data["ginarea_advice"] = first_not_none(data.get("ginarea_advice"), data.get("ginarea"), data.get("ginarea_now"), data.get("advisor_text"))
    data["price"] = to_float(data.get("price"), data.get("price"))
    data["range_low"] = to_float(data.get("range_low"), data.get("range_low"))
    data["range_mid"] = to_float(data.get("range_mid"), data.get("range_mid"))
    data["range_high"] = to_float(data.get("range_high"), data.get("range_high"))
    data["forecast_confidence"] = normalize_confidence(data.get("forecast_confidence"))
    data["signal"] = normalize_direction(data.get("signal"))
    data["final_decision"] = normalize_direction(data.get("final_decision"))
    data["forecast_direction"] = normalize_direction(data.get("forecast_direction"))
    return data


def load_btc_analyzer() -> Optional[Callable]:
    return try_import_attr(["core.signal_engine", "signal_engine"], ["analyze_btc", "analyze_market", "analyze"])


def load_range_analyzer() -> Optional[Callable]:
    return try_import_attr(["core.range_detector", "range_detector"], ["analyze_range", "get_range_analysis", "build_range_analysis"])


def load_ginarea_analyzer() -> Optional[Callable]:
    return try_import_attr(["core.ginarea_advisor", "ginarea_advisor"], ["analyze_ginarea", "get_ginarea_advice", "build_ginarea_advice", "analyze"])
