"""Backtest harnesses (P8 expansion research and beyond).

See docs/RESEARCH/P8_RGE_EXPANSION_RESULTS_v0_1.md for the methodology.
"""
from .expansion_research import (
    BacktestResult, run_variant_on_regime, ALL_VARIANTS,
)

__all__ = ["BacktestResult", "run_variant_on_regime", "ALL_VARIANTS"]
