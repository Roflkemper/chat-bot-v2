"""Stage B4 — pre-cascade liquidation prediction.

Existing cascade_alert fires AFTER the liquidation cascade (post-mortem of edge).
This service tries to fire BEFORE: when crowding indicators flash a warning that
a cascade is statistically likely in the next 10-30 minutes.

Pre-cascade signature (operator hypothesis 2026-05-09 Stage B4):
  OI rising fast       — `oi_change_1h_pct >= +1.5%`
  Funding extreme      — `|funding_rate_8h| >= 0.0006` (≈ 0.06%/8h)
  Crowding extreme     — `global_ls_ratio` deviates from 1.0 by ≥ 30%
                         (i.e. >= 1.30 or <= 0.77)
  Direction match      — long-crowded (LS>1.3 + funding>0): SHORT cascade likely
                         short-crowded (LS<0.77 + funding<0): LONG cascade likely

Sends TG warning, doesn't trade. Cooldown 60min per (symbol, direction).

When a real cascade follows within 30 min — that confirms the signature.
A regular post-mortem in tools/_pre_cascade_audit.py compares pre-cascade
fires against actual cascade_alert fires to compute precision/recall.
"""
from .loop import pre_cascade_alert_loop  # noqa: F401
