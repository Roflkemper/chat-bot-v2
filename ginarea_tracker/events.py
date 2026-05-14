"""Event detector: compares consecutive bot stat snapshots."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

EventType = Literal["IN_FILLED", "OUT_FILLED"]


@dataclass
class BotEvent:
    event_type: EventType
    delta_count: int
    delta_qty: float
    price_last: float
    position_after: float
    profit_after: float


def detect_events(prev: dict, curr: dict) -> list[BotEvent]:
    """Return events based on diff between two consecutive stat snapshots.

    Emits IN_FILLED if inFilledCount grew, OUT_FILLED if outFilledCount grew.
    """
    events: list[BotEvent] = []

    in_delta = int(curr.get("inFilledCount", 0) or 0) - int(prev.get("inFilledCount", 0) or 0)
    out_delta = int(curr.get("outFilledCount", 0) or 0) - int(prev.get("outFilledCount", 0) or 0)

    price = float(curr.get("averagePrice", 0) or 0)
    position = float(curr.get("position", 0) or 0)
    profit = float(curr.get("profit", 0) or 0)

    if in_delta > 0:
        in_qty_delta = (
            float(curr.get("inFilledQty", 0) or 0)
            - float(prev.get("inFilledQty", 0) or 0)
        )
        events.append(BotEvent(
            event_type="IN_FILLED",
            delta_count=in_delta,
            delta_qty=in_qty_delta,
            price_last=price,
            position_after=position,
            profit_after=profit,
        ))

    if out_delta > 0:
        out_qty_delta = (
            float(curr.get("outFilledQty", 0) or 0)
            - float(prev.get("outFilledQty", 0) or 0)
        )
        events.append(BotEvent(
            event_type="OUT_FILLED",
            delta_count=out_delta,
            delta_qty=out_qty_delta,
            price_last=price,
            position_after=position,
            profit_after=profit,
        ))

    return events
