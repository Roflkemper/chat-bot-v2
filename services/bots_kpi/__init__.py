"""/bots_kpi — Telegram command + builder.

Computes per-bot KPI from ginarea_live/snapshots.csv over a configurable
window (default last 7d). Produces the same table shape as
docs/ANALYSIS/BOTS_KPI_2026-05-09.md but auto-refreshed.

Aliases come from ginarea_tracker/bot_aliases.json. Bots without an alias
are listed by their raw bot_name string (truncated).

Usage:
  /bots_kpi          — last 7d
  /bots_kpi 1        — last 1d
  /bots_kpi 14       — last 14d (or custom int)
"""
from .builder import build_bots_kpi_report  # noqa: F401
