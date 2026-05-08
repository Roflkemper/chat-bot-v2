from __future__ import annotations

from services.telegram.dedup_layer import DedupConfig


POSITION_CHANGE_DEDUP_CONFIG = DedupConfig(
    cooldown_sec=300,
    value_delta_min=0.05,
    cluster_enabled=False,
)


BOUNDARY_BREACH_DEDUP_CONFIG = DedupConfig(
    cooldown_sec=600,
    value_delta_min=0.0,
    cluster_enabled=False,
)


# ── P3 of TZ-DASHBOARD-AND-TELEGRAM-USABILITY-PHASE-1 ──────────────────────
#
# Tier-1 high-pressure emitters. Per DEDUP_DRY_RUN_2026-05-04 §6: defaults
# suppress 88-99 % which is too aggressive. Loosened thresholds below give a
# meaningful state-change signal while still cutting the obvious noise floor.
#
# All thresholds reviewed by operator before commit.

# PNL_EVENT (delta-PnL alerts) — value_delta_min in USD.
# Loosened from default 5.0 to 25.0 USD: only emit when realized PnL changed
# by at least $25 since the last emit.
# Cooldown 600s = 10 min: prevents tight bursts during fast PnL moves.
PNL_EVENT_DEDUP_CONFIG = DedupConfig(
    cooldown_sec=600,
    value_delta_min=25.0,
    cluster_enabled=False,
)


# PNL_EXTREME — same family but for absolute extreme thresholds.
# Same 25 USD delta + 600s cooldown.
PNL_EXTREME_DEDUP_CONFIG = DedupConfig(
    cooldown_sec=600,
    value_delta_min=25.0,
    cluster_enabled=False,
)


# AUTO_EDGE_ALERT (RSI extremes from auto_edge_alerts.py). Cluster collapse
# enabled: bursts of RSI events within 30 min and within ±0.5 % price collapse
# into one summary message.
# value_delta_min applies to RSI points (e.g. 5 RSI-points change).
AUTO_EDGE_ALERTS_DEDUP_CONFIG = DedupConfig(
    cooldown_sec=1800,             # 30 min
    value_delta_min=5.0,           # 5 RSI points = meaningful state change
    cluster_window_sec=1800,       # 30 min cluster window
    cluster_price_delta_pct=0.5,
    cluster_enabled=True,
)
