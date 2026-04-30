from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd

from services.setup_detector.models import Setup, SetupStatus, setup_side
from services.setup_detector.outcomes import ProgressResult, _calc_pnl_usd

logger = logging.getLogger(__name__)

_BAR_INTERVAL_MINUTES = 1  # assumes 1m OHLCV


class HistoricalOutcomeSimulator:
    """Simulate lifecycle outcomes for historical setups using OHLCV look-ahead."""

    def __init__(self, df_1m: pd.DataFrame) -> None:
        """df_1m: 1m OHLCV with DatetimeIndex (UTC), columns: open/high/low/close/volume."""
        if df_1m.index.tz is None:
            df_1m = df_1m.copy()
            df_1m.index = df_1m.index.tz_localize("UTC")
        self._df = df_1m.sort_index()

    def simulate_outcome(self, setup: Setup) -> ProgressResult:
        """Walk OHLCV bars from detected_at to expires_at, apply same rules as live tracker."""
        start_ts = setup.detected_at.replace(tzinfo=timezone.utc) if setup.detected_at.tzinfo is None else setup.detected_at
        end_ts = setup.expires_at.replace(tzinfo=timezone.utc) if setup.expires_at.tzinfo is None else setup.expires_at

        mask = (self._df.index >= pd.Timestamp(start_ts)) & (self._df.index <= pd.Timestamp(end_ts))
        window = self._df[mask]

        if window.empty:
            return ProgressResult(
                status_changed=True,
                new_status=SetupStatus.EXPIRED,
                close_price=setup.current_price,
                time_to_outcome_min=setup.window_minutes,
            )

        side = setup_side(setup)
        current_status = setup.status
        entry_ts: datetime | None = None

        for i, (bar_ts, row) in enumerate(window.iterrows()):
            bar_time = bar_ts.to_pydatetime()
            if bar_time.tzinfo is None:
                bar_time = bar_time.replace(tzinfo=timezone.utc)

            bar_high = float(row["high"])
            bar_low = float(row["low"])

            elapsed_min = int((bar_time - start_ts).total_seconds() / 60)

            # Check entry fill
            if current_status == SetupStatus.DETECTED and setup.entry_price is not None:
                if side == "long" and bar_low <= setup.entry_price:
                    current_status = SetupStatus.ENTRY_HIT
                    entry_ts = bar_time
                elif side == "short" and bar_high >= setup.entry_price:
                    current_status = SetupStatus.ENTRY_HIT
                    entry_ts = bar_time

            # Check TP / Stop after entry
            if current_status == SetupStatus.ENTRY_HIT:
                # Check TP1
                if setup.tp1_price is not None:
                    tp_hit = (side == "long" and bar_high >= setup.tp1_price) or (
                        side == "short" and bar_low <= setup.tp1_price
                    )
                    if tp_hit:
                        pnl, r = _calc_pnl_usd(setup, setup.tp1_price)
                        return ProgressResult(
                            status_changed=True,
                            new_status=SetupStatus.TP1_HIT,
                            close_price=setup.tp1_price,
                            hypothetical_pnl_usd=pnl,
                            hypothetical_r=r,
                            time_to_outcome_min=elapsed_min,
                        )
                # Check Stop
                if setup.stop_price is not None:
                    stop_hit = (side == "long" and bar_low <= setup.stop_price) or (
                        side == "short" and bar_high >= setup.stop_price
                    )
                    if stop_hit:
                        pnl, r = _calc_pnl_usd(setup, setup.stop_price)
                        return ProgressResult(
                            status_changed=True,
                            new_status=SetupStatus.STOP_HIT,
                            close_price=setup.stop_price,
                            hypothetical_pnl_usd=pnl,
                            hypothetical_r=r,
                            time_to_outcome_min=elapsed_min,
                        )

        # Window expired without terminal outcome
        last_price = float(window["close"].iloc[-1]) if not window.empty else setup.current_price
        # If entry was hit but no TP/SL, compute partial PnL
        if current_status == SetupStatus.ENTRY_HIT and setup.entry_price is not None:
            pnl, r = _calc_pnl_usd(setup, last_price)
            return ProgressResult(
                status_changed=True,
                new_status=SetupStatus.EXPIRED,
                close_price=last_price,
                hypothetical_pnl_usd=pnl,
                hypothetical_r=r,
                time_to_outcome_min=setup.window_minutes,
            )
        return ProgressResult(
            status_changed=True,
            new_status=SetupStatus.EXPIRED,
            close_price=last_price,
            time_to_outcome_min=setup.window_minutes,
        )

    def simulate_all(self, setups: list[Setup]) -> list[ProgressResult]:
        return [self.simulate_outcome(s) for s in setups]
