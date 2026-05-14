"""What-If runner — end-to-end play execution over episodes.

§10-§11 TZ-022.

Usage:
    python -m src.whatif.runner --play P-1 --horizon-min 240
    python -m src.whatif.runner --play all --n-workers 4 --dry-run
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.whatif.action_simulator import PARAM_GRIDS
from src.whatif.grid_search import Episode, grid_search_play
from src.whatif.snapshot import build_snapshot

logger = logging.getLogger(__name__)

_DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "XRPUSDT"]
_VERSION = "v1"


# ─────────────────────────────────────────────────────────────────────────────
# Play registry
# ─────────────────────────────────────────────────────────────────────────────

_BTC  = ["BTCUSDT"]
_ALL3 = ["BTCUSDT", "ETHUSDT", "XRPUSDT"]


@dataclass
class PlayConfig:
    play_id: str
    episode_types: list[str]   # episode_type values from episodes.parquet / extractor
    action_name: str           # key in ACTIONS / PARAM_GRIDS
    param_grids: list[dict]
    preset: str                # position preset for build_snapshot
    symbols: list[str] = None  # symbols to scan; None → use CLI --symbols or _ALL3


PLAY_CONFIGS: dict[str, PlayConfig] = {
    # BTC-only plays (relate to our BTC short bot)
    "P-1":  PlayConfig("P-1",  ["rally_strong", "rally_critical"],
                       "A-RAISE-BOUNDARY",          PARAM_GRIDS["A-RAISE-BOUNDARY"],          "short_large_drawdown", _BTC),
    "P-2":  PlayConfig("P-2",  ["rally_strong"],
                       "A-LAUNCH-STACK-SHORT",      PARAM_GRIDS["A-LAUNCH-STACK-SHORT"],      "short_large_drawdown", _BTC),
    "P-3":  PlayConfig("P-3",  ["rally_critical"],
                       "A-LAUNCH-COUNTER-LONG",     PARAM_GRIDS["A-LAUNCH-COUNTER-LONG"],     "short_large_drawdown", _BTC),
    "P-4":  PlayConfig("P-4",  ["rally_strong", "rally_critical", "no_pullback_up_3h"],
                       "A-STOP",                    PARAM_GRIDS["A-STOP"],                    "short_large_drawdown", _BTC),
    "P-5":  PlayConfig("P-5",  ["rally_strong", "rally_critical"],
                       "A-CLOSE-PARTIAL",           PARAM_GRIDS["A-CLOSE-PARTIAL"],           "short_critical",       _BTC),
    "P-6":  PlayConfig("P-6",  ["rally_critical"],
                       "A-RAISE-AND-STACK-SHORT",   PARAM_GRIDS["A-RAISE-AND-STACK-SHORT"],   "short_large_drawdown", _BTC),
    "P-7":  PlayConfig("P-7",  ["dump_strong", "dump_critical"],
                       "A-LAUNCH-STACK-LONG",       PARAM_GRIDS["A-LAUNCH-STACK-LONG"],       "flat",                 _BTC),
    "P-8":  PlayConfig("P-8",  ["rally_critical", "dump_critical"],
                       "A-RESTART-WITH-NEW-PARAMS", PARAM_GRIDS["A-RESTART-WITH-NEW-PARAMS"], "short_critical",       _BTC),
    "P-9":  PlayConfig("P-9",  ["rally_strong"],
                       "A-CLOSE-PARTIAL",           PARAM_GRIDS["A-CLOSE-PARTIAL"],           "long_small_position",  _BTC),
    "P-10": PlayConfig("P-10", ["rally_critical", "dump_critical"],
                       "A-RESTART-WITH-NEW-PARAMS", PARAM_GRIDS["A-RESTART-WITH-NEW-PARAMS"], "short_large_drawdown", _BTC),
    "P-11": PlayConfig("P-11", ["rally_strong", "rally_critical"],
                       "A-LAUNCH-STACK-SHORT",      PARAM_GRIDS["A-LAUNCH-STACK-SHORT"],      "short_large_drawdown", _BTC),
    "P-12": PlayConfig("P-12", ["rally_strong", "no_pullback_up_3h"],
                       "A-ADAPTIVE-GRID",           PARAM_GRIDS["A-ADAPTIVE-GRID"],           "short_large_drawdown", _BTC),
}


# ─────────────────────────────────────────────────────────────────────────────
# Episode loading — two paths
# ─────────────────────────────────────────────────────────────────────────────

def _load_episodes_from_parquet(path: Path, episode_types: list[str]) -> pd.DataFrame:
    df = pd.read_parquet(path)
    if not episode_types:
        return df.reset_index(drop=True)
    mask = df["episode_type"].isin(episode_types)
    return df[mask].reset_index(drop=True)


def _load_episodes_fallback(
    episode_types: list[str],
    features_dir: Path,
    symbols: list[str],
) -> pd.DataFrame:
    """Scan features_out via extractor (TZ-019). Imports lazily to avoid heavy dep."""
    from src.episodes.extractor import extract_episodes

    types = episode_types or None
    df, warnings = extract_episodes(
        features_dir=features_dir,
        symbols=symbols,
        episode_types=types,
        dry_run=True,
    )
    for w in warnings:
        logger.warning("extractor: %s", w)
    return df


def load_episodes(
    config: PlayConfig,
    episodes_parquet: Path | None,
    features_dir: Path,
    symbols: list[str],
) -> pd.DataFrame:
    """Load episodes for play: from pre-extracted parquet or feature scan fallback.

    config.symbols overrides the caller's symbols list when set.
    """
    effective_symbols = config.symbols if config.symbols else symbols

    if episodes_parquet is not None and episodes_parquet.exists():
        logger.info("Loading episodes from %s (symbols=%s)", episodes_parquet, effective_symbols)
        df = _load_episodes_from_parquet(episodes_parquet, config.episode_types)
        return df[df["symbol"].isin(effective_symbols)].reset_index(drop=True)

    logger.info("episodes.parquet not found — scanning features_out (%s, symbols=%s)",
                features_dir, effective_symbols)
    return _load_episodes_fallback(config.episode_types, features_dir, effective_symbols)


# ─────────────────────────────────────────────────────────────────────────────
# Snapshot building
# ─────────────────────────────────────────────────────────────────────────────

def _build_episode_list(
    episodes_df: pd.DataFrame,
    features_dir: Path,
    horizon_min: int,
    preset: str,
) -> list[Episode]:
    """Build Episode objects from episodes DataFrame rows."""
    episodes: list[Episode] = []
    for _, row in episodes_df.iterrows():
        ts_raw = row["ts_start"]
        ts = pd.Timestamp(ts_raw)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        symbol = str(row["symbol"])
        try:
            snap = build_snapshot(
                timestamp=ts,
                symbol=symbol,
                features_dir=features_dir,
                preset=preset,
            )
        except Exception as exc:
            logger.warning("Skipping %s @ %s: %s", symbol, ts, exc)
            continue
        ep_type = str(row.get("episode_type", "")) if hasattr(row, "get") else str(getattr(row, "episode_type", ""))
        episodes.append(Episode(
            snapshot=snap,
            horizon_min=horizon_min,
            features_dir=features_dir,
            episode_type=ep_type,
        ))
    return episodes


# ─────────────────────────────────────────────────────────────────────────────
# Manifest
# ─────────────────────────────────────────────────────────────────────────────

def write_manifest(
    output_dir: Path,
    plays_processed: list[str],
    horizon_min: int,
    n_workers: int,
    features_dir: Path,
) -> Path:
    params_str = json.dumps(
        {"horizon_min": horizon_min, "n_workers": n_workers, "features_dir": str(features_dir)},
        sort_keys=True,
    )
    params_hash = hashlib.md5(params_str.encode()).hexdigest()[:8]
    manifest = {
        "version": _VERSION,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "plays_processed": plays_processed,
        "horizon_min": horizon_min,
        "n_workers": n_workers,
        "params_hash": params_hash,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    logger.info("Manifest written: %s", path)
    return path


# ─────────────────────────────────────────────────────────────────────────────
# Run one play
# ─────────────────────────────────────────────────────────────────────────────

def run_play(
    play_id: str,
    features_dir: Path,
    output_dir: Path,
    horizon_min: int = 240,
    episodes_parquet: Path | None = None,
    symbols: list[str] | None = None,
    n_workers: int = 4,
    dry_run: bool = False,
) -> pd.DataFrame:
    """Run grid search for one play over all matching episodes.

    Returns aggregated result DataFrame (one row per param_combo).
    """
    if play_id not in PLAY_CONFIGS:
        raise ValueError(f"Unknown play: {play_id!r}. Valid: {sorted(PLAY_CONFIGS)}")

    config = PLAY_CONFIGS[play_id]
    syms = symbols or _DEFAULT_SYMBOLS

    episodes_df = load_episodes(config, episodes_parquet, features_dir, syms)
    logger.info("%s: %d episodes found (types=%s)", play_id, len(episodes_df), config.episode_types)

    if episodes_df.empty:
        logger.warning("%s: no episodes — skipping", play_id)
        return pd.DataFrame()

    episodes = _build_episode_list(episodes_df, features_dir, horizon_min, config.preset)
    if not episodes:
        logger.warning("%s: all snapshot builds failed", play_id)
        return pd.DataFrame()

    logger.info(
        "%s: %d episodes × %d param combos (action=%s)",
        play_id, len(episodes), len(config.param_grids), config.action_name,
    )

    date_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

    result_df = grid_search_play(
        action_name=config.action_name,
        episodes=episodes,
        param_grids=config.param_grids,
        n_workers=n_workers,
        raw_output_path=None if dry_run else output_dir / f"{play_id}_{date_str}_raw.parquet",
    )

    if dry_run:
        logger.info("%s: --dry-run, skipping disk write (%d rows)", play_id, len(result_df))
        return result_df

    if not result_df.empty:
        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / f"{play_id}_{date_str}.parquet"
        result_df.to_parquet(out_path, compression="zstd", index=False)
        logger.info("%s: wrote %d rows → %s", play_id, len(result_df), out_path)

    return result_df


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m src.whatif.runner",
        description="What-If grid search runner (TZ-022 §11)",
    )
    p.add_argument("--play", default="P-1",
                   help='Play ID (P-1..P-12) or "all". Default: P-1')
    p.add_argument("--horizon-min", type=int, default=240,
                   help="Horizon in minutes. Default: 240")
    p.add_argument("--episodes", type=Path, default=None,
                   help="Path to episodes.parquet (TZ-021). Falls back to feature scan.")
    p.add_argument("--features-dir", type=Path, default=Path("features_out"),
                   help="Features directory. Default: features_out")
    p.add_argument("--output", type=Path, default=Path("whatif_results"),
                   help="Output directory. Default: whatif_results/")
    p.add_argument("--n-workers", type=int, default=4,
                   help="Parallel workers. Default: 4")
    p.add_argument("--dry-run", action="store_true",
                   help="Skip writing output to disk.")
    p.add_argument("--symbols", nargs="+", default=None,
                   help="Symbols to process. Default: BTCUSDT ETHUSDT XRPUSDT")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args(argv)

    plays = list(PLAY_CONFIGS.keys()) if args.play == "all" else [args.play]
    for play_id in plays:
        if play_id not in PLAY_CONFIGS:
            logger.error("Unknown play: %s. Valid: %s", play_id, sorted(PLAY_CONFIGS.keys()))
            return 1

    processed: list[str] = []
    for play_id in plays:
        try:
            df = run_play(
                play_id=play_id,
                features_dir=args.features_dir,
                output_dir=args.output,
                horizon_min=args.horizon_min,
                episodes_parquet=args.episodes,
                symbols=args.symbols,
                n_workers=args.n_workers,
                dry_run=args.dry_run,
            )
            if not df.empty:
                processed.append(play_id)
        except Exception:
            logger.exception("Failed to run play %s", play_id)

    if not args.dry_run:
        write_manifest(
            output_dir=args.output,
            plays_processed=processed,
            horizon_min=args.horizon_min,
            n_workers=args.n_workers,
            features_dir=args.features_dir,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
