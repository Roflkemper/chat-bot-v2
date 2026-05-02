"""Instrumented wrapper for MultiGridSim that captures trim events.

Does NOT modify simulator.py — subclasses MultiGridSim and overrides feed_bar
to log every asymmetric_trim call with full context.
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

from services.calibration.sim import load_ohlcv_bars
from services.coordinated_grid.models import BotConfig, CoordinatedConfig, CoordinatedRunResult
from services.coordinated_grid.simulator import (
    MultiGridSim,
    _combined_pnl_usd,
    _trim_losing_side,
)

ROOT = Path(__file__).resolve().parents[2]
OHLCV_PATH = ROOT / "backtests" / "frozen" / "BTCUSDT_1m_2y.csv"
SIM_START = "2025-05-01T00:00:00+00:00"
SIM_END   = "2026-04-29T23:59:59+00:00"


@dataclass
class TrimEvent:
    bar_idx: int
    ts: str
    price: float
    side: str
    n_orders_before: int
    n_orders_cancelled: int
    losing_unrealized_usd: float
    combined_notional: float
    loss_pct: float
    combined_pnl_before: float
    combined_pnl_after: float | None = None


class InstrumentedMultiGridSim(MultiGridSim):
    """MultiGridSim subclass — records trim events. Core sim logic unchanged."""

    def __init__(self, config: CoordinatedConfig, bar_timestamps: list[str] | None = None) -> None:
        super().__init__(config)
        self._bar_timestamps: list[str] = bar_timestamps or []
        self.trim_events: list[TrimEvent] = []

    def feed_bar(self, o: float, h: float, l: float, c: float) -> None:
        self._bar_idx += 1
        self._prices.append(c)

        if self._pause_bars > 0:
            self._pause_bars -= 1
            if self._price_offset_met(c):
                self._pause_bars = 0
            else:
                return

        self.long_bot.feed_bar(o, h, l, c, "raw")
        self.short_bot.feed_bar(o, h, l, c, "raw")

        combined = _combined_pnl_usd(self.long_bot, self.short_bot, c)
        self._update_dd(combined)

        if combined >= self.config.combined_close_threshold_usd:
            self._do_coordinated_close(c, combined)
            return

        if self.config.asymmetric_trim_enabled:
            notional = self._combined_notional()
            if notional > 0:
                for bot, label in [(self.long_bot, "LONG"), (self.short_bot, "SHORT")]:
                    unreal = bot._unrealized(c)
                    if unreal >= 0:
                        continue
                    loss_usd = abs(unreal * c) if bot.side == "LONG" else abs(unreal)
                    loss_pct = loss_usd / notional * 100
                    if loss_pct < self.config.asymmetric_trim_threshold_pct or not bot.open_orders:
                        continue
                    n_before = len(bot.open_orders)
                    did_trim = _trim_losing_side(
                        bot, c, notional,
                        self.config.asymmetric_trim_threshold_pct,
                        self.config.asymmetric_trim_size_pct,
                    )
                    if did_trim:
                        n_after = len(bot.open_orders)
                        ts = (self._bar_timestamps[self._bar_idx - 1]
                              if self._bar_idx <= len(self._bar_timestamps) else "")
                        combined_after = _combined_pnl_usd(self.long_bot, self.short_bot, c)
                        self.trim_events.append(TrimEvent(
                            bar_idx=self._bar_idx,
                            ts=ts,
                            price=c,
                            side=label,
                            n_orders_before=n_before,
                            n_orders_cancelled=n_before - n_after,
                            losing_unrealized_usd=-loss_usd,
                            combined_notional=notional,
                            loss_pct=loss_pct,
                            combined_pnl_before=combined,
                            combined_pnl_after=combined_after,
                        ))


def _load_bars_with_ts(path: Path, start: str, end: str) -> tuple[list[tuple], list[str]]:
    """Load OHLCV bars + ISO timestamps within [start, end].
    CSV format: ts column is Unix milliseconds.
    """
    bars: list[tuple] = []
    timestamps: list[str] = []
    start_ms = int(datetime.fromisoformat(start).timestamp() * 1000)
    end_ms   = int(datetime.fromisoformat(end).timestamp()   * 1000)
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            try:
                ts_ms = int(float(row["ts"]))
            except (KeyError, ValueError):
                continue
            if ts_ms < start_ms:
                continue
            if ts_ms > end_ms:
                break
            try:
                o = float(row["open"])
                h = float(row["high"])
                l = float(row["low"])
                c = float(row["close"])
            except (KeyError, ValueError):
                continue
            bars.append((o, h, l, c))
            # Convert ms → ISO string for human-readable event log
            ts_iso = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
            timestamps.append(ts_iso)
    return bars, timestamps


def run_instrumented(config: CoordinatedConfig) -> tuple[CoordinatedRunResult, list[TrimEvent]]:
    """Run winning config with full trim event logging."""
    bars, timestamps = _load_bars_with_ts(OHLCV_PATH, SIM_START, SIM_END)
    sim = InstrumentedMultiGridSim(config, bar_timestamps=timestamps)
    for o, h, l, c in bars:
        sim.feed_bar(o, h, l, c)
    return sim.result(), sim.trim_events


def winning_config() -> CoordinatedConfig:
    """Exact winning config from grid_search results."""
    long_bot = BotConfig(
        side="LONG", order_size=200.0, grid_step_pct=0.03, target_pct=0.25, max_orders=800
    )
    short_bot = BotConfig(
        side="SHORT", order_size=0.003, grid_step_pct=0.03, target_pct=0.25, max_orders=800
    )
    return CoordinatedConfig(
        long_bot=long_bot,
        short_bot=short_bot,
        combined_close_threshold_usd=2000.0,
        re_entry_delay_bars=0,
        re_entry_price_offset_pct=0.0,
        asymmetric_trim_enabled=True,
        asymmetric_trim_threshold_pct=1.0,
        asymmetric_trim_size_pct=50.0,
    )


if __name__ == "__main__":
    import sys
    print("Running instrumented sim on winning config...", flush=True)
    result, trims = run_instrumented(winning_config())
    print(f"combined_realized_usd = ${result.combined_realized_usd:,.2f}")
    print(f"n_coordinated_closes  = {result.n_coordinated_closes}")
    print(f"n_trim_events         = {len(trims)}")
    out = ROOT / "reports" / "trim_events_raw.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(
        [
            {
                "bar_idx": t.bar_idx, "ts": t.ts, "price": t.price, "side": t.side,
                "n_orders_before": t.n_orders_before, "n_orders_cancelled": t.n_orders_cancelled,
                "losing_unrealized_usd": round(t.losing_unrealized_usd, 2),
                "combined_notional": round(t.combined_notional, 2),
                "loss_pct": round(t.loss_pct, 4),
                "combined_pnl_before": round(t.combined_pnl_before, 2),
                "combined_pnl_after": round(t.combined_pnl_after or 0.0, 2),
            }
            for t in trims
        ],
        indent=2,
    ), encoding="utf-8")
    print(f"Raw trim events saved to: {out}")
