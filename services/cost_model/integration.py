from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .fees import VENUES, compute_fee
from .funding import compute_funding_pnl
from .slippage import estimate_slippage

_FUNDING_PATH = Path("backtests/frozen/BTCUSDT_funding.parquet")


@dataclass(frozen=True)
class CostBreakdown:
    fees_usd: float
    slippage_usd: float
    funding_usd: float

    @property
    def net_adjustment_usd(self) -> float:
        return -self.fees_usd - self.slippage_usd + self.funding_usd


def infer_venue_contract_side(
    *,
    symbol: str,
    action_name: str | None = None,
    setup_side: str | None = None,
    position_size_btc: float | None = None,
) -> tuple[str, str, str]:
    side = setup_side or ("short" if (position_size_btc or 0.0) < 0 else "long")
    if side not in {"long", "short"}:
        side = "long"
    action = str(action_name or "").upper()
    if side == "short" or "SHORT" in action:
        return "ginarea_inverse", "inverse", "short"
    return "ginarea_linear", "linear", "long"


def load_funding_rate_pct(
    ts: pd.Timestamp,
    symbol: str,
    *,
    default_positive_pct: float = 0.005,
    bias_hint: float | None = None,
) -> float:
    path = _FUNDING_PATH
    if path.exists():
        try:
            df = pd.read_parquet(path)
            ts_col = None
            for candidate in ("calc_time", "funding_time", "ts"):
                if candidate in df.columns:
                    ts_col = candidate
                    break
            rate_col = None
            for candidate in ("last_funding_rate", "funding_rate"):
                if candidate in df.columns:
                    rate_col = candidate
                    break
            if ts_col and rate_col:
                df[ts_col] = pd.to_datetime(df[ts_col], utc=True, errors="coerce")
                df = df.dropna(subset=[ts_col]).sort_values(ts_col)
                if "symbol" in df.columns:
                    df = df[df["symbol"].astype(str).str.upper() == symbol.upper()]
                past = df[df[ts_col] <= ts]
                if not past.empty:
                    raw = float(past.iloc[-1][rate_col])
                    return raw * 100.0 if abs(raw) < 1 else raw
        except Exception:
            pass
    if bias_hint is not None and bias_hint < 0:
        return -default_positive_pct
    return default_positive_pct


def estimate_setup_costs(
    *,
    pair: str,
    side: str,
    entry_price: float,
    close_price: float,
    size_btc: float,
    atr_1h: float,
    detected_at: pd.Timestamp,
    close_ts: pd.Timestamp,
) -> CostBreakdown:
    venue, contract_type, normalized_side = infer_venue_contract_side(symbol=pair, setup_side=side)
    entry_notional = abs(size_btc) * entry_price
    close_notional = abs(size_btc) * close_price
    fees = 0.0
    fees += max(compute_fee(venue, normalized_side, entry_notional, is_maker=True), 0.0)
    fees += max(compute_fee(venue, normalized_side, close_notional, is_maker=False), 0.0)
    rebate = min(compute_fee(venue, normalized_side, entry_notional, is_maker=True), 0.0)
    slippage = estimate_slippage("taker_market", close_notional, atr_1h)
    funding_rate_pct = load_funding_rate_pct(close_ts, pair)
    hours_held = max((close_ts - detected_at).total_seconds() / 3600.0, 0.0)
    funding = compute_funding_pnl(close_notional, normalized_side, contract_type, funding_rate_pct, hours_held)
    return CostBreakdown(fees_usd=fees + abs(rebate) * 0.0, slippage_usd=slippage, funding_usd=funding + rebate)


def estimate_whatif_costs(
    *,
    play_id: str | None,
    action_name: str,
    snapshot_symbol: str,
    snapshot_ts: pd.Timestamp,
    close_price: float,
    atr_1h: float,
    roc_4h_pct: float,
    main_position_notional_usd: float,
    initial_action_notional_usd: float,
    maker_fill_notionals: list[float],
    taker_fill_notionals: list[tuple[str, float]],
    hours_held: float,
) -> CostBreakdown:
    venue, contract_type, side = infer_venue_contract_side(
        symbol=snapshot_symbol,
        action_name=action_name,
        position_size_btc=-1.0 if "SHORT" in action_name.upper() else 1.0,
    )
    fees = 0.0
    funding = 0.0
    slippage = 0.0

    for notional in maker_fill_notionals:
        fee = compute_fee(venue, side, notional, is_maker=True)
        if fee >= 0:
            fees += fee
        else:
            funding += abs(fee)

    if initial_action_notional_usd > 0:
        fees += max(compute_fee(venue, side, initial_action_notional_usd, is_maker=False), 0.0)
        slippage += estimate_slippage("taker_market", initial_action_notional_usd, atr_1h)

    for order_type, notional in taker_fill_notionals:
        fees += max(compute_fee(venue, side, notional, is_maker=False), 0.0)
        slippage += estimate_slippage(order_type, notional, atr_1h)

    base_notional = max(main_position_notional_usd, initial_action_notional_usd, close_price)
    funding_rate_pct = load_funding_rate_pct(snapshot_ts, snapshot_symbol, bias_hint=roc_4h_pct)
    funding += compute_funding_pnl(base_notional, side, contract_type, funding_rate_pct, hours_held)
    return CostBreakdown(fees_usd=fees, slippage_usd=slippage, funding_usd=funding)


def parse_param_values(param_values: str) -> dict[str, Any]:
    try:
        loaded = json.loads(param_values)
        return loaded if isinstance(loaded, dict) else {}
    except json.JSONDecodeError:
        return {}
