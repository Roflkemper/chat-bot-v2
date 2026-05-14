from __future__ import annotations

from services.cost_model.fees import compute_fee
from services.cost_model.funding import compute_funding_pnl
from services.cost_model.slippage import estimate_slippage


def test_maker_rebate_negative() -> None:
    fee = compute_fee("bitmex_inverse", "short", 10_000.0, is_maker=True)
    assert fee < 0.0


def test_funding_inverse_short_bull_positive() -> None:
    pnl = compute_funding_pnl(
        position_size_usd=10_000.0,
        side="short",
        contract_type="inverse",
        funding_rate_pct=0.005,
        hours_held=8.0,
    )
    assert pnl > 0.0


def test_slippage_taker_stop_higher() -> None:
    market = estimate_slippage("taker_market", 10_000.0, 500.0)
    stop = estimate_slippage("taker_stop", 10_000.0, 500.0)
    assert stop > market
