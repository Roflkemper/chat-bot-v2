"""Stage E2 — LLM-based market regime narrator (Anthropic Haiku 4.5).

Hourly briefing: aggregates market state (regime A/B, OI, funding, taker
dominance, recent setups, last 6h price action) and asks Claude Haiku for
a 4-5 sentence Russian narrative. Sends to TG, logs to audit file.

Cost (Haiku 4.5 with prompt caching): ≈ $0.50-0.70/мес at hourly cadence.
Set ANTHROPIC_API_KEY in .env. Disable: set REGIME_NARRATOR_ENABLED=0.
"""
from .loop import regime_narrator_loop  # noqa: F401
