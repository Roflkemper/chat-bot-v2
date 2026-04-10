from __future__ import annotations

import os

from renderers.grid_view import render_grid_view
from renderers.trader_view import render_trader_view


def render_full_report(snapshot, mode: str | None = None):
    selected_mode = (mode or os.getenv("OUTPUT_MODE", "FULL")).strip().upper()
    header = f"⚡ {snapshot['symbol']} [{snapshot['tf']} | {snapshot['timestamp']}]"

    if selected_mode == "TRADER":
        return "\n\n".join([header, render_trader_view(snapshot)])
    if selected_mode == "GRID":
        return "\n\n".join([header, render_grid_view(snapshot)])

    return "\n\n".join([
        header,
        render_trader_view(snapshot),
        "────────────────────",
        render_grid_view(snapshot),
    ])
