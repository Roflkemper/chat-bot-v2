"""Data models for coordinated two-sided grid research.

Two-sided grid: LONG (COIN-M inverse) + SHORT (USDT-M linear) running simultaneously.
Coordinated logic fires when combined PnL reaches a threshold.

PnL accounting:
  SHORT linear: realized_pnl in USD.
  LONG inverse: realized_pnl in BTC. Convert to USD via current bar close price.
  combined_pnl_usd = short_usd + long_btc * price
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class BotConfig:
    side: str               # "SHORT" or "LONG"
    order_size: float       # BTC for SHORT linear; USD contracts for LONG inverse
    grid_step_pct: float    # e.g. 0.03 → sim divides by 100 → 0.0003 = 0.03%
    target_pct: float       # e.g. 0.25 → sim divides by 100 → 0.0025 = 0.25%
    max_orders: int


@dataclass
class CoordinatedConfig:
    long_bot: BotConfig
    short_bot: BotConfig

    # --- coordinated close trigger ---
    # threshold in USD for combined (realized + unrealized) PnL
    # math.inf means "never trigger" → pure baseline (no coordination)
    combined_close_threshold_usd: float

    # --- re-entry after close ---
    re_entry_delay_bars: int          # 1m bars to wait after coordinated close
    re_entry_price_offset_pct: float  # require price to move N% from close price

    # --- asymmetric trim (cancel orders on losing side) ---
    asymmetric_trim_enabled: bool
    asymmetric_trim_threshold_pct: float  # losing side unrealized / combined_notional %
    asymmetric_trim_size_pct: float = 50.0  # % of losing side orders to cancel

    def config_id(self) -> str:
        trim = f"trim{self.asymmetric_trim_threshold_pct:.0f}" if self.asymmetric_trim_enabled else "notrim"
        return (f"thr{self.combined_close_threshold_usd:.0f}"
                f"_d{self.re_entry_delay_bars}"
                f"_off{self.re_entry_price_offset_pct:.1f}"
                f"_{trim}")


@dataclass
class CloseEvent:
    bar_idx: int
    price: float
    combined_pnl_usd_at_close: float
    short_realized_usd: float
    long_realized_btc: float
    n_short_orders: int
    n_long_orders: int


@dataclass
class CoordinatedRunResult:
    config: CoordinatedConfig
    # raw sim values (NOT K-adjusted)
    short_realized_usd: float
    long_realized_btc: float
    combined_realized_usd: float    # short_usd + long_btc * avg_close_price
    combined_unrealized_usd: float  # at last bar
    total_volume_usd: float
    max_combined_dd_usd: float      # max peak-to-trough of combined_pnl_usd
    n_coordinated_closes: int
    n_short_fills: int
    n_long_fills: int
    avg_close_price: float          # for BTC→USD conversion reference
    close_events: list[CloseEvent] = field(default_factory=list)

    def net_edge_over_baseline(self, baseline: "CoordinatedRunResult") -> float:
        return self.combined_realized_usd - baseline.combined_realized_usd
