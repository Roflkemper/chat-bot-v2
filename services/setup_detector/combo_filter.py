from __future__ import annotations

from .models import Setup, SetupType

# Data-driven from year backtest BTCUSDT 2025-05-01..2026-04-29 (29,224 setups).
# Format: (SetupType, regime_label) → verdict
# ALLOW  = profitable, send to Telegram
# BLOCK  = confirmed loser, suppress (magnitude ≥ $234 loss over year)
# Default for unknown combos: ALLOW (conservative — don't block what we haven't measured)

COMBO_FILTER: dict[tuple[SetupType, str], str] = {
    # ── ALLOW (profitable combos) ─────────────────────────────────────────────
    (SetupType.LONG_PDL_BOUNCE,       "trend_down"):    "ALLOW",   # +$5,165  53.4% WR
    (SetupType.LONG_DUMP_REVERSAL,    "trend_down"):    "ALLOW",   # +$8,851  30.8% WR
    (SetupType.SHORT_PDH_REJECTION,   "trend_up"):      "ALLOW",   # +$2,831  41.8% WR
    (SetupType.SHORT_RALLY_FADE,      "trend_up"):      "ALLOW",   # +$2,675  28.5% WR
    (SetupType.LONG_PDL_BOUNCE,       "consolidation"): "ALLOW",   # +$995    32.3% WR
    (SetupType.SHORT_PDH_REJECTION,   "consolidation"): "ALLOW",   # +$246    28.8% WR

    # ── BLOCK (data-confirmed losers, magnitude ≥ $234 loss) ─────────────────
    (SetupType.LONG_DUMP_REVERSAL,    "consolidation"): "BLOCK",   # -$5,282  19.9% WR
    (SetupType.SHORT_RALLY_FADE,      "consolidation"): "BLOCK",   # -$5,493  17.9% WR
    (SetupType.SHORT_OVERBOUGHT_FADE, "trend_up"):      "BLOCK",   # -$1,637  14.9% WR
    (SetupType.LONG_OVERSOLD_RECLAIM, "trend_down"):    "BLOCK",   # -$1,153  17.6% WR
    (SetupType.SHORT_RALLY_FADE,      "trend_down"):    "BLOCK",   # -$309    mismatched dir
    (SetupType.LONG_DUMP_REVERSAL,    "trend_up"):      "BLOCK",   # -$234    mismatched dir
}

# Grid and defensive types are always allowed — they are protective actions, not
# directional speculation, and were not measured in the backtest.
_EXEMPT_TYPES: frozenset[SetupType] = frozenset({
    SetupType.GRID_BOOSTER_ACTIVATE,
    SetupType.GRID_RAISE_BOUNDARY,
    SetupType.GRID_PAUSE_ENTRIES,
    SetupType.GRID_ADAPTIVE_TIGHTEN,
    SetupType.DEFENSIVE_MARGIN_LOW,
    SetupType.DEFENSIVE_LIQ_PROXIMITY,
})


def is_combo_allowed(setup: Setup) -> tuple[bool, str]:
    """Return (allowed, reason) for a detected setup.

    Grid/defensive types are exempt. Trade setups are checked against
    COMBO_FILTER. Unknown combos default to ALLOW.
    """
    if setup.setup_type in _EXEMPT_TYPES:
        return True, "grid_or_defensive"

    key = (setup.setup_type, setup.regime_label)
    verdict = COMBO_FILTER.get(key, "ALLOW")

    if verdict == "BLOCK":
        return False, f"blocked_combo:{setup.setup_type.value}×{setup.regime_label}"
    return True, f"allowed:{setup.setup_type.value}×{setup.regime_label}"


def filter_setups(setups: list[Setup]) -> tuple[list[Setup], list[Setup]]:
    """Partition setups into (allowed, blocked) according to COMBO_FILTER."""
    allowed: list[Setup] = []
    blocked: list[Setup] = []
    for s in setups:
        ok, _ = is_combo_allowed(s)
        (allowed if ok else blocked).append(s)
    return allowed, blocked
