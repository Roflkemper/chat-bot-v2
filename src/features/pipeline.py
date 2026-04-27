"""Feature pipeline: loads raw parquets, aligns to 1m, runs all modules, partitions output.

Input layout (data_dir):
  {data_dir}/{symbol}/klines_1m.parquet   — OHLCV, ts_col='open_time' (ms epoch or datetime)
  {data_dir}/{symbol}/metrics_5m.parquet  — OI/L-S/taker, ts_col='open_time'
  {data_dir}/{symbol}/funding_8h.parquet  — funding rate, ts_col='funding_time'

Output layout (output_dir):
  {output_dir}/{symbol}/{date}.parquet    — one file per UTC day, all feature columns

Manifest:
  {output_dir}/manifest.json              — hash-based stale detection

Computed delta columns (before module chain, on 1m close per symbol):
  delta_5m_pct   = close.pct_change(5)  * 100
  delta_15m_pct  = close.pct_change(15) * 100
  delta_1h_pct   = close.pct_change(60) * 100
  delta_24h_pct  = close.pct_change(1440) * 100

After per-symbol features are computed, cross_asset runs on the merged dataframe
with columns prefixed: btc_{col}, eth_{col}, xrp_{col}.
Cross-asset output columns are NOT prefixed (added directly to merged df).

Performance target: full rebuild 1yr × 3 symbols < 30 min (parallelized by symbol).
"""
from __future__ import annotations

import logging
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

from src.features import calendar, killzones, dwm, technical, derivatives, cross_asset
from src.features.manifest import Manifest

logger = logging.getLogger(__name__)

_DELTA_WINDOWS = {"delta_5m_pct": 5, "delta_15m_pct": 15, "delta_1h_pct": 60, "delta_24h_pct": 1440}
_CROSS_ASSET_SYMBOLS = ("btc", "eth", "xrp")

# ── Loaders ───────────────────────────────────────────────────────────────────

def _parse_timestamps(series: pd.Series) -> pd.Series:
    """Coerce ms-epoch int or datetime strings to UTC datetime64."""
    if pd.api.types.is_integer_dtype(series):
        return pd.to_datetime(series, unit="ms", utc=True)
    return pd.to_datetime(series, utc=True)


def _load_parquet(path: Path, ts_col: str) -> pd.DataFrame | None:
    if not path.exists():
        logger.debug("Missing parquet: %s", path)
        return None
    df = pd.read_parquet(path)
    if ts_col not in df.columns:
        logger.warning("ts_col '%s' not found in %s", ts_col, path)
        return None
    df[ts_col] = _parse_timestamps(df[ts_col])
    df = df.set_index(ts_col).sort_index()
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    return df


# ── Column normalization ──────────────────────────────────────────────────────

_METRICS_RENAME = {
    "sum_open_interest_value":        "oi_value",
    "sum_toptrader_long_short_ratio": "ls_ratio_top",
    "count_long_short_ratio":         "ls_ratio_retail",
}
_FUNDING_RENAME = {
    "last_funding_rate": "funding_rate",
}


def _normalize_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """Rename raw Binance metric columns to names derivatives.py expects."""
    df = df.rename(columns={k: v for k, v in _METRICS_RENAME.items() if k in df.columns})
    # taker: only ratio available → synthesize buy=ratio, sell=1 (ratio math is identical)
    if "taker_buy_volume" not in df.columns and "sum_taker_long_short_vol_ratio" in df.columns:
        df["taker_buy_volume"]  = df["sum_taker_long_short_vol_ratio"]
        df["taker_sell_volume"] = 1.0
    return df


def _normalize_funding(df: pd.DataFrame) -> pd.DataFrame:
    return df.rename(columns={k: v for k, v in _FUNDING_RENAME.items() if k in df.columns})


# ── Alignment ─────────────────────────────────────────────────────────────────

def _align_to_1m(
    klines: pd.DataFrame,
    metrics: pd.DataFrame | None,
    funding: pd.DataFrame | None,
) -> pd.DataFrame:
    """Merge metrics_5m and funding_8h onto the 1m klines index via ffill."""
    base = klines.copy()

    if metrics is not None:
        metrics_ff = metrics.reindex(base.index, method="ffill")
        for col in metrics_ff.columns:
            if col not in base.columns:
                base[col] = metrics_ff[col]

    if funding is not None:
        funding_ff = funding.reindex(base.index, method="ffill")
        for col in funding_ff.columns:
            if col not in base.columns:
                base[col] = funding_ff[col]

    return base


# ── Delta columns ─────────────────────────────────────────────────────────────

def _compute_deltas(df: pd.DataFrame) -> pd.DataFrame:
    """Add delta_Xm_pct columns based on 'close'."""
    if "close" not in df.columns:
        return df
    close = df["close"].astype(float)
    for col, window in _DELTA_WINDOWS.items():
        df[col] = close.pct_change(window) * 100.0
    return df


# ── Per-symbol feature chain ──────────────────────────────────────────────────

def _run_symbol_features(df: pd.DataFrame) -> pd.DataFrame:
    """Run feature modules 1-5 on a single-symbol 1m DataFrame."""
    df = calendar.compute(df)
    df = killzones.compute(df)
    df = dwm.compute(df)
    df = technical.compute(df)
    df = derivatives.compute(df)
    df = _compute_deltas(df)
    return df


# ── Output partitioning ───────────────────────────────────────────────────────

def _partition_and_save(df: pd.DataFrame, symbol_dir: Path) -> list[str]:
    """Split df by UTC date, save each partition, return list of date strings."""
    symbol_dir.mkdir(parents=True, exist_ok=True)
    date_col = df.index.normalize()
    saved: list[str] = []
    for date, group in df.groupby(date_col):
        date_str = str(date.date())
        out_path = symbol_dir / f"{date_str}.parquet"
        group.to_parquet(out_path)
        saved.append(date_str)
    return saved


# ── Symbol-level orchestration ────────────────────────────────────────────────

def _process_symbol(
    symbol: str,
    data_dir: Path,
    output_dir: Path,
    force_rebuild: bool,
    manifest_params: dict,
) -> dict[str, list[str]]:
    """Load raw data, run features, save partitions for one symbol.

    Returns {symbol: [date_str, ...]} of newly written partitions.
    """
    def _try(*candidates: tuple[Path, str]) -> pd.DataFrame | None:
        for path, ts_col in candidates:
            result = _load_parquet(path, ts_col=ts_col)
            if result is not None:
                return result
        return None

    sym_data = data_dir / symbol
    klines = _try(
        (sym_data / "klines_1m.parquet",           "open_time"),
        (sym_data / "_combined_klines_1m.parquet", "open_time"),
    )
    if klines is None:
        logger.error("No klines for %s — skipping", symbol)
        return {symbol: []}

    metrics = _try(
        (sym_data / "metrics_5m.parquet",       "open_time"),
        (sym_data / "_combined_metrics.parquet", "create_time"),
    )
    funding = _try(
        (sym_data / "funding_8h.parquet",            "funding_time"),
        (sym_data / "_combined_fundingRate.parquet", "calc_time"),
    )

    if metrics is not None:
        metrics = _normalize_metrics(metrics)
    if funding is not None:
        funding = _normalize_funding(funding)

    df = _align_to_1m(klines, metrics, funding)
    df = _run_symbol_features(df)

    sym_out = output_dir / symbol
    manifest = Manifest(output_dir, Path(__file__).parent, manifest_params)
    if force_rebuild:
        manifest.invalidate()

    date_strs_all = sorted({str(ts.date()) for ts in df.index})
    dates_to_write = [
        d for d in date_strs_all
        if not manifest.is_fresh(symbol, d, parquet_path=sym_out / f"{d}.parquet")
    ]

    if not dates_to_write:
        logger.info("[%s] All partitions fresh — skipping", symbol)
        return {symbol: []}

    write_set = set(dates_to_write)
    mask = pd.Series(df.index).apply(lambda ts: str(ts.date()) in write_set).values
    subset = df[mask]
    saved = _partition_and_save(subset, sym_out)
    for date_str in saved:
        manifest.mark_done(symbol, date_str)

    logger.info("[%s] Wrote %d partitions", symbol, len(saved))
    return {symbol: saved}


# ── Cross-asset pass ──────────────────────────────────────────────────────────

def _run_cross_asset_pass(
    output_dir: Path,
    symbols: Sequence[str],
    date_strs: list[str],
) -> None:
    """For each date where all 3 cross-asset symbols are available, compute
    cross_asset features and append them to each symbol's parquet."""
    sym_set = set(s.lower() for s in symbols)
    ca_symbols = [s for s in _CROSS_ASSET_SYMBOLS if s in sym_set]
    if len(ca_symbols) < 2:
        return

    for date_str in date_strs:
        frames: dict[str, pd.DataFrame] = {}
        for sym in ca_symbols:
            path = output_dir / sym / f"{date_str}.parquet"
            if path.exists():
                frames[sym] = pd.read_parquet(path)

        if len(frames) < 2:
            continue

        # Build merged df with prefixed columns
        ref_sym = ca_symbols[0]
        merged = frames[ref_sym].add_prefix(f"{ref_sym}_")
        common_idx = merged.index
        for sym in ca_symbols[1:]:
            prefixed = frames[sym].add_prefix(f"{sym}_").reindex(common_idx)
            merged = merged.join(prefixed, how="left")

        merged = cross_asset.compute(merged)

        # Distribute cross-asset-only columns back to each symbol file
        ca_cols = [c for c in merged.columns if not any(
            c.startswith(f"{s}_") for s in ca_symbols
        )]
        if not ca_cols:
            continue

        ca_slice = merged[ca_cols]
        for sym in ca_symbols:
            if sym not in frames:
                continue
            path = output_dir / sym / f"{date_str}.parquet"
            existing = pd.read_parquet(path)
            for col in ca_cols:
                existing[col] = ca_slice[col].reindex(existing.index)
            existing.to_parquet(path)


# ── Public entry point ────────────────────────────────────────────────────────

def build_features(
    data_dir: str | Path,
    output_dir: str | Path,
    symbols: Sequence[str],
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    force_rebuild: bool = False,
    n_workers: int | None = None,
) -> dict[str, list[str]]:
    """Build feature parquets for all symbols.

    Args:
        data_dir:      Root directory with raw parquets per symbol.
        output_dir:    Root directory for feature output.
        symbols:       List of symbol names (e.g. ['btc', 'eth', 'xrp']).
        start_date:    ISO date string filter (inclusive). None = no filter.
        end_date:      ISO date string filter (inclusive). None = no filter.
        force_rebuild: If True, ignore manifest and rebuild everything.
        n_workers:     Parallel workers. None = cpu_count.

    Returns:
        {symbol: [date_str, ...]} of written partitions per symbol.
    """
    data_dir   = Path(data_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest_params = {
        "symbols": sorted(symbols),
        "start_date": start_date,
        "end_date": end_date,
    }

    workers = n_workers if n_workers is not None else min(len(symbols), mp.cpu_count())

    results: dict[str, list[str]] = {}

    if workers <= 1 or len(symbols) == 1:
        for sym in symbols:
            r = _process_symbol(sym, data_dir, output_dir, force_rebuild, manifest_params)
            results.update(r)
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(
                    _process_symbol, sym, data_dir, output_dir, force_rebuild, manifest_params
                ): sym
                for sym in symbols
            }
            for fut in as_completed(futures):
                sym = futures[fut]
                try:
                    results.update(fut.result())
                except Exception:
                    logger.exception("[%s] Failed", sym)
                    results[sym] = []

    # Collect all dates that were written (union across symbols)
    all_written_dates = sorted({d for dates in results.values() for d in dates})

    if all_written_dates:
        _run_cross_asset_pass(output_dir, symbols, all_written_dates)

    total = sum(len(v) for v in results.values())
    logger.info("build_features done: %d partitions across %d symbols", total, len(symbols))
    return results
