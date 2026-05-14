"""Grid search over coordinated config parameters.

Generates 256 unique configs (deduplicates trim=False × trim_threshold combos)
and runs all against frozen 1-year BTCUSDT 1m bars.

Fixed bot params: TD=0.25, GS=0.03%, matching calibration ground truth.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass
from pathlib import Path

from services.calibration.sim import load_ohlcv_bars
from .models import BotConfig, CoordinatedConfig, CoordinatedRunResult
from .simulator import run_sim

ROOT      = Path(__file__).resolve().parents[2]
OHLCV_PATH = ROOT / "backtests" / "frozen" / "BTCUSDT_1m_2y.csv"
SIM_START  = "2025-05-01T00:00:00+00:00"
SIM_END    = "2026-04-29T23:59:59+00:00"

# Fixed bot params matching calibration ground truth (TD=0.25)
LONG_BOT = BotConfig(
    side="LONG",
    order_size=200.0,
    grid_step_pct=0.03,
    target_pct=0.25,
    max_orders=800,
)
SHORT_BOT = BotConfig(
    side="SHORT",
    order_size=0.003,
    grid_step_pct=0.03,
    target_pct=0.25,
    max_orders=800,
)

# --- Search space ---
COMBINED_THRESHOLDS = [500.0, 1000.0, 2000.0, 5000.0]
RE_ENTRY_DELAYS_H   = [0, 4, 12, 24]      # hours → convert to bars (×60)
RE_ENTRY_OFFSETS    = [0.0, 0.5, 1.0, 2.0]
TRIM_THRESHOLDS     = [1.0, 2.0, 5.0]
TRIM_SIZE_PCT       = 50.0

# Baseline: no coordination (threshold=inf)
BASELINE_CONFIG = CoordinatedConfig(
    long_bot=LONG_BOT,
    short_bot=SHORT_BOT,
    combined_close_threshold_usd=math.inf,
    re_entry_delay_bars=0,
    re_entry_price_offset_pct=0.0,
    asymmetric_trim_enabled=False,
    asymmetric_trim_threshold_pct=0.0,
)


def generate_configs(full: bool = False) -> list[CoordinatedConfig]:
    """Return param combinations.

    full=False (default): focused 24-config sweep covering the key axes.
    full=True: complete 257-config sweep (all combinations + baseline).
    """
    if full:
        return _generate_full_configs()
    return _generate_focused_configs()


def _generate_focused_configs() -> list[CoordinatedConfig]:
    """24 focused configs + baseline.

    Tier 1 (16): all threshold × delay combos, offset=0, trim=off
    Tier 2 (6): best offsets at fixed threshold×delay, trim=off
    Tier 3 (6): trim sweep at fixed threshold×delay, offset=0
    + baseline = 29 total
    """
    configs: list[CoordinatedConfig] = [BASELINE_CONFIG]

    # Tier 1: threshold × delay sweep (core hypothesis)
    for thr in COMBINED_THRESHOLDS:
        for delay_h in RE_ENTRY_DELAYS_H:
            configs.append(CoordinatedConfig(
                long_bot=LONG_BOT, short_bot=SHORT_BOT,
                combined_close_threshold_usd=thr,
                re_entry_delay_bars=delay_h * 60,
                re_entry_price_offset_pct=0.0,
                asymmetric_trim_enabled=False,
                asymmetric_trim_threshold_pct=0.0,
            ))

    # Tier 2: offset sweep at mid threshold (2000) + 12h delay
    for offset in RE_ENTRY_OFFSETS[1:]:   # skip 0.0 (already in tier 1)
        configs.append(CoordinatedConfig(
            long_bot=LONG_BOT, short_bot=SHORT_BOT,
            combined_close_threshold_usd=2000.0,
            re_entry_delay_bars=12 * 60,
            re_entry_price_offset_pct=offset,
            asymmetric_trim_enabled=False,
            asymmetric_trim_threshold_pct=0.0,
        ))

    # Tier 3: trim sensitivity at mid threshold (2000) + 0h delay
    for trim_thr in TRIM_THRESHOLDS:
        configs.append(CoordinatedConfig(
            long_bot=LONG_BOT, short_bot=SHORT_BOT,
            combined_close_threshold_usd=2000.0,
            re_entry_delay_bars=0,
            re_entry_price_offset_pct=0.0,
            asymmetric_trim_enabled=True,
            asymmetric_trim_threshold_pct=trim_thr,
            asymmetric_trim_size_pct=TRIM_SIZE_PCT,
        ))

    return configs


def _generate_full_configs() -> list[CoordinatedConfig]:
    """257 configs: full cartesian product (deduplicated) + baseline."""
    configs: list[CoordinatedConfig] = [BASELINE_CONFIG]
    for thr in COMBINED_THRESHOLDS:
        for delay_h in RE_ENTRY_DELAYS_H:
            delay_bars = delay_h * 60
            for offset in RE_ENTRY_OFFSETS:
                configs.append(CoordinatedConfig(
                    long_bot=LONG_BOT, short_bot=SHORT_BOT,
                    combined_close_threshold_usd=thr,
                    re_entry_delay_bars=delay_bars,
                    re_entry_price_offset_pct=offset,
                    asymmetric_trim_enabled=False,
                    asymmetric_trim_threshold_pct=0.0,
                ))
                for trim_thr in TRIM_THRESHOLDS:
                    configs.append(CoordinatedConfig(
                        long_bot=LONG_BOT, short_bot=SHORT_BOT,
                        combined_close_threshold_usd=thr,
                        re_entry_delay_bars=delay_bars,
                        re_entry_price_offset_pct=offset,
                        asymmetric_trim_enabled=True,
                        asymmetric_trim_threshold_pct=trim_thr,
                        asymmetric_trim_size_pct=TRIM_SIZE_PCT,
                    ))
    return configs


def run_grid_search(
    full: bool = False,
    progress_every: int = 10,
) -> tuple[list[CoordinatedRunResult], CoordinatedRunResult]:
    """Run full grid search. Returns (all_results, baseline_result)."""
    print(f"[grid_search] Loading bars {SIM_START} → {SIM_END} ...")
    bars = load_ohlcv_bars(OHLCV_PATH, SIM_START, SIM_END)
    if len(bars) < 100_000:
        raise RuntimeError(f"Too few bars: {len(bars)}")
    print(f"[grid_search] {len(bars):,} bars loaded.")

    configs = generate_configs(full=full)
    mode_str = "FULL 257-config" if full else "focused 29-config"
    print(f"[grid_search] Running {mode_str} sweep ({len(configs)} configs) ...")

    t0 = time.perf_counter()
    results: list[CoordinatedRunResult] = []
    baseline: CoordinatedRunResult | None = None

    for i, cfg in enumerate(configs, 1):
        r = run_sim(bars, cfg)
        results.append(r)
        if cfg is BASELINE_CONFIG:
            baseline = r
        if i % progress_every == 0:
            elapsed = time.perf_counter() - t0
            eta = elapsed / i * (len(configs) - i)
            print(f"[grid_search]  {i}/{len(configs)}  elapsed={elapsed:.0f}s  eta={eta:.0f}s")

    if baseline is None:
        baseline = results[0]  # fallback

    elapsed = time.perf_counter() - t0
    print(f"[grid_search] Done in {elapsed:.1f}s. {len(results)} results.")
    return results, baseline
