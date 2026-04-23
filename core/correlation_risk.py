from __future__ import annotations


def classify_cluster_risk(symbol: str, signal: str) -> dict:
    if symbol == "BTCUSDT":
        cluster = "BTC_BETA"
        overload = "low"
    elif symbol in {"ETHUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT", "BNBUSDT"}:
        cluster = "ALT"
        overload = "medium" if signal != "NO TRADE" else "low"
    else:
        cluster = "OTHER"
        overload = "unknown"
    return {"cluster": cluster, "directional_overload": overload}
