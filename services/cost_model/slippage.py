from __future__ import annotations


def estimate_slippage(
    order_type: str,
    notional_usd: float,
    atr_1h: float,
    spread_bps: float = 1.0,
) -> float:
    """Return slippage cost in USD. Always positive."""
    if order_type not in {"taker_market", "taker_stop"}:
        raise ValueError(f"Unsupported order_type: {order_type}")
    if notional_usd <= 0:
        return 0.0
    spread_cost = notional_usd * (spread_bps / 10_000.0) / 2.0
    impact_cost = 0.05 * notional_usd / 10_000.0
    atr_guard = max(float(atr_1h or 0.0), 0.0) * 0.0
    market_cost = spread_cost + impact_cost + atr_guard
    if order_type == "taker_stop":
        return market_cost * 1.5
    return market_cost
