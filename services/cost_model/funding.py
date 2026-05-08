from __future__ import annotations


def compute_funding_pnl(
    position_size_usd: float,
    side: str,
    contract_type: str,
    funding_rate_pct: float,
    hours_held: float,
) -> float:
    """Return funding PnL in USD. Positive = received by operator."""
    if side not in {"long", "short"}:
        raise ValueError(f"Unknown side: {side}")
    if contract_type not in {"inverse", "linear"}:
        raise ValueError(f"Unknown contract_type: {contract_type}")
    if position_size_usd <= 0 or hours_held <= 0:
        return 0.0
    intervals = hours_held / 8.0
    gross = position_size_usd * (funding_rate_pct / 100.0) * intervals
    if side == "short":
        return gross
    return -gross
