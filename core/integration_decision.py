from __future__ import annotations

from typing import Dict, Any, Optional

import pandas as pd

from core.decision_engine import build_decision_from_dataframe
from core.telegram_formatter import (
    format_final_decision_telegram,
    format_btc_summary_telegram,
    format_forecast_telegram,
    format_ginarea_telegram,
)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _fmt_price(value: float) -> str:
    return f"{value:,.2f}".replace(",", " ")


def normalize_symbol(symbol: str) -> str:
    s = str(symbol).upper().strip()
    if s == "BTC":
        return "BTCUSDT"
    return s


def build_range_payload(range_info: Optional[Dict[str, Any]]) -> Dict[str, float]:
    if not isinstance(range_info, dict):
        return {
            "range_low": 0.0,
            "range_mid": 0.0,
            "range_high": 0.0,
        }

    low = _safe_float(range_info.get("low"))
    mid = _safe_float(range_info.get("mid"))
    high = _safe_float(range_info.get("high"))

    return {
        "range_low": low,
        "range_mid": mid,
        "range_high": high,
    }


def extract_last_price(df: pd.DataFrame) -> float:
    if df is None or df.empty:
        return 0.0
    if "close" not in df.columns:
        return 0.0
    return _safe_float(df.iloc[-1].get("close"))


def detect_range_state_label(decision: Dict[str, Any], range_low: float, range_mid: float, range_high: float) -> str:
    pos = str(decision.get("range_position", "UNKNOWN"))

    if pos == "LOW_EDGE":
        return "низ диапазона / реакция поддержки"
    if pos == "LOWER_PART":
        return "нижняя часть диапазона"
    if pos == "MID":
        return "середина диапазона"
    if pos == "UPPER_PART":
        return "верхняя часть диапазона"
    if pos == "HIGH_EDGE":
        return "верх диапазона / реакция сопротивления"
    return "позиция не определена"


def pressure_to_ct_now(decision: Dict[str, Any], timeframe: str) -> str:
    direction = str(decision.get("direction", "NEUTRAL"))
    reason = str(decision.get("pressure_reason", "")).lower()
    action = str(decision.get("action", ""))

    if direction == "LONG":
        if "перепродан" in reason:
            return "контртренд: рынок локально перепродан, возможен отскок"
        return "контекст: локальный перевес в лонг"
    if direction == "SHORT":
        if action == "WAIT_PULLBACK":
            return "контекст: рынок под давлением продавца, но вход лучше искать после отката"
        return "контекст: локальный перевес в шорт"
    return "контртренд: явного перекоса нет"


def build_ginarea_advice(range_low: float, range_mid: float, range_high: float, decision: Dict[str, Any]) -> str:
    direction = str(decision.get("direction", "NEUTRAL"))
    pos = str(decision.get("range_position", "UNKNOWN"))

    if direction == "LONG" and pos in ("LOW_EDGE", "LOWER_PART"):
        return f"ближе поддержка в районе {int(range_low)}, при реакции возможен ход к середине {int(range_mid)}"
    if direction == "SHORT" and pos in ("HIGH_EDGE", "UPPER_PART"):
        return f"ближе сопротивление в районе {int(range_high)}, при слабости возможен откат к середине {int(range_mid)}"

    if range_low > 0 and range_mid > 0:
        return f"ближе поддержка в районе {int(range_low)}, середина {int(range_mid)}"

    return "ключевые зоны range пока не определены"


def build_analysis_package(
    symbol: str,
    timeframe: str,
    df: pd.DataFrame,
    range_info: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Возвращает единый пакет анализа, который можно использовать во всех командах.
    """
    normalized_symbol = normalize_symbol(symbol)
    range_payload = build_range_payload(range_info)

    decision = build_decision_from_dataframe(
        df=df,
        timeframe=timeframe,
        range_low=range_payload["range_low"],
        range_mid=range_payload["range_mid"],
        range_high=range_payload["range_high"],
    )

    price = extract_last_price(df)
    range_state = detect_range_state_label(
        decision=decision,
        range_low=range_payload["range_low"],
        range_mid=range_payload["range_mid"],
        range_high=range_payload["range_high"],
    )
    ct_now = pressure_to_ct_now(decision, timeframe)
    ginarea_advice = build_ginarea_advice(
        range_low=range_payload["range_low"],
        range_mid=range_payload["range_mid"],
        range_high=range_payload["range_high"],
        decision=decision,
    )

    return {
        "symbol": normalized_symbol,
        "timeframe": timeframe,
        "price": price,
        "decision": decision,
        "range_info": {
            "low": range_payload["range_low"],
            "mid": range_payload["range_mid"],
            "high": range_payload["range_high"],
            "state": range_state,
        },
        "ct_now": ct_now,
        "ginarea_advice": ginarea_advice,
    }


def format_analysis_message(package: Dict[str, Any]) -> str:
    symbol = str(package["symbol"])
    timeframe = str(package["timeframe"])
    price = _safe_float(package["price"])
    decision = package["decision"]
    range_info = package["range_info"]
    ct_now = str(package["ct_now"])
    ginarea_advice = str(package["ginarea_advice"])

    direction_map = {
        "LONG": "ЛОНГ",
        "SHORT": "ШОРТ",
        "NEUTRAL": "НЕЙТРАЛЬНО",
    }
    action_map = {
        "ENTER_LONG": "ВХОД В ЛОНГ",
        "ENTER_SHORT": "ВХОД В ШОРТ",
        "WAIT_CONFIRMATION": "ЖДАТЬ ПОДТВЕРЖДЕНИЕ",
        "WAIT_PULLBACK": "ЖДАТЬ ОТКАТ",
        "WAIT_RANGE_EDGE": "ЖДАТЬ КРАЙ ДИАПАЗОНА",
        "NO_TRADE": "БЕЗ СДЕЛКИ",
    }

    direction_ru = direction_map.get(str(decision.get("direction", "NEUTRAL")), "НЕЙТРАЛЬНО")
    action_ru = action_map.get(str(decision.get("action", "NO_TRADE")), "БЕЗ СДЕЛКИ")

    lines = [
        f"📊 {symbol.replace('USDT', '')} ANALYSIS [{timeframe}]",
        "",
        f"Инструмент: {symbol}",
        f"Цена: {_fmt_price(price)}",
        "",
        "Главное сейчас:",
        f"• сигнал: {direction_ru}",
        f"• финальное решение: {direction_ru}",
        f"• куда вероятнее пойдёт рынок: {direction_ru}",
        f"• уверенность: {decision.get('confidence', 0)}%",
        f"• reversal: NO_REVERSAL",
        f"• reversal confidence: 0.0%",
        "",
        "FINAL DECISION:",
        f"• направление: {direction_ru}",
        f"• действие: {action_ru}",
        f"• режим: {decision.get('regime', 'MIXED')}",
        f"• confidence: {decision.get('confidence', 0)}%",
        f"• risk: {decision.get('risk', 'HIGH')}",
        f"• edge score: {float(decision.get('edge_score') or 0.0):.1f}% | {str(decision.get('edge_label') or 'NO_EDGE').upper()}",
        f"• edge action: {decision.get('edge_action') or 'WAIT'}",
        "",
        "RANGE NOW:",
        f"• состояние: {range_info.get('state', '-')}",
        f"• low: {_fmt_price(range_info.get('low', 0))}",
        f"• mid: {_fmt_price(range_info.get('mid', 0))}",
        f"• high: {_fmt_price(range_info.get('high', 0))}",
        "",
        f"CT NOW: {ct_now}",
        f"GINAREA ADVICE: {ginarea_advice}",
        "",
        f"Итог: {decision.get('summary', '-')}",
    ]

    return "\n".join(lines)


def format_summary_message(package: Dict[str, Any]) -> str:
    return format_btc_summary_telegram(
        decision=package["decision"],
        symbol=package["symbol"].replace("USDT", ""),
        timeframe=package["timeframe"],
        price=package["price"],
    )


def format_forecast_message(package: Dict[str, Any]) -> str:
    return format_forecast_telegram(
        decision=package["decision"],
        symbol=package["symbol"].replace("USDT", ""),
        timeframe=package["timeframe"],
    )


def format_ginarea_message(package: Dict[str, Any]) -> str:
    return format_ginarea_telegram(
        decision=package["decision"],
        symbol=package["symbol"].replace("USDT", ""),
        timeframe=package["timeframe"],
        range_low=package["range_info"].get("low"),
        range_mid=package["range_info"].get("mid"),
        range_high=package["range_info"].get("high"),
    )


def format_decision_message(package: Dict[str, Any]) -> str:
    return format_final_decision_telegram(
        decision=package["decision"],
        symbol=package["symbol"],
        timeframe=package["timeframe"],
        price=package["price"],
    )