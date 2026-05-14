"""Smoke tests for ForwardProjection.price_at_projection snapshot."""
from __future__ import annotations

import pandas as pd

from services.market_forward_analysis.forward_projection import (
    ForwardProjection, HorizonForecast,
)


def test_projection_holds_price_at_projection():
    p = ForwardProjection(
        generated_at=pd.Timestamp("2026-05-11", tz="UTC"),
        phase_label="markup",
        phase_bias=1,
        confluence_strength=None,
        confluence_signals=[],
        forecasts={"4h": HorizonForecast(
            horizon="4h", direction="up", probability=60.0,
            expected_move_pct=0.5, ci95_low_pct=-0.5,
            ci95_high_pct=1.5, n_episodes=200,
        )},
        key_resistance=None, key_support=None,
        price_at_projection=80000.0,
    )
    assert p.price_at_projection == 80000.0


def test_projection_default_price_is_none():
    p = ForwardProjection(
        generated_at=pd.Timestamp("2026-05-11", tz="UTC"),
        phase_label="markup",
        phase_bias=1,
        confluence_strength=None,
        confluence_signals=[],
        forecasts={},
        key_resistance=None, key_support=None,
    )
    assert p.price_at_projection is None
