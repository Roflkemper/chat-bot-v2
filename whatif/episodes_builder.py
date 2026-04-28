from __future__ import annotations

import argparse
import logging
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.whatif.runner import PLAY_CONFIGS
from whatif.episodes_window import EpisodesWindow, compute_tracker_window, write_window_json


logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
FEATURES_DIR = ROOT / "features_out"
EPISODES_PATH = ROOT / "frozen" / "labels" / "episodes.parquet"
EPISODES_ARCHIVE_DIR = ROOT / "whatif" / "episodes_archive" / "pre_tz041"


@dataclass(frozen=True)
class BuildResult:
    window: EpisodesWindow
    episodes_path: Path
    n_episodes: int


def _episode_types_for_plays(plays: list[str]) -> list[str]:
    types: set[str] = set()
    for play in plays:
        cfg = PLAY_CONFIGS.get(play)
        if cfg is None:
            raise ValueError(f"Unknown play: {play}")
        types.update(cfg.episode_types)
    return sorted(types)


def _archive_existing_episodes(path: Path) -> Path | None:
    if not path.exists():
        return None
    EPISODES_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dst = EPISODES_ARCHIVE_DIR / f"episodes_{stamp}.parquet"
    shutil.copy2(path, dst)
    return dst


def build_episodes(
    *,
    plays: list[str],
    bots: list[str],
    output_path: Path = EPISODES_PATH,
    window_json_path: Path = ROOT / "whatif" / "episodes_window.json",
) -> BuildResult:
    window = compute_tracker_window(bots)
    write_window_json(window, window_json_path)

    _archive_existing_episodes(output_path)

    # Delegate extraction to existing extractor (TZ-022/TZ-041 requirement).
    from src.episodes.extractor import extract_episodes

    episode_types = _episode_types_for_plays(plays)
    df, warnings = extract_episodes(
        features_dir=FEATURES_DIR,
        symbols=["BTCUSDT"],
        start=window.start_ts.isoformat(),
        end=window.end_ts.isoformat(),
        episode_types=episode_types,
        dry_run=True,
    )
    for w in warnings:
        logger.warning("extract_episodes: %s", w)

    if df.empty:
        raise ValueError(
            "No episodes extracted for tracker window. "
            f"window=[{window.start_ts.isoformat()} .. {window.end_ts.isoformat()}], "
            f"episode_types={episode_types}"
        )

    # Only write after we know the result is non-empty, to avoid clobbering prior episodes.parquet.
    df, warnings = extract_episodes(
        features_dir=FEATURES_DIR,
        symbols=["BTCUSDT"],
        output=output_path,
        start=window.start_ts.isoformat(),
        end=window.end_ts.isoformat(),
        episode_types=episode_types,
        dry_run=False,
    )
    for w in warnings:
        logger.warning("extract_episodes: %s", w)

    return BuildResult(window=window, episodes_path=output_path, n_episodes=int(len(df)))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Regenerate episodes.parquet for tracker coverage window.")
    p.add_argument("--plays", required=True, help="Comma-separated play ids, e.g. P-1,P-2,P-6,P-7")
    p.add_argument("--bots", required=True, help="Comma-separated bot selectors, e.g. TEST_3,BTC-LONG-B")
    p.add_argument("--output", type=Path, default=EPISODES_PATH)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s")
    args = parse_args(argv)
    plays = [x.strip() for x in args.plays.split(",") if x.strip()]
    bots = [x.strip() for x in args.bots.split(",") if x.strip()]
    result = build_episodes(plays=plays, bots=bots, output_path=args.output)
    logger.info(
        "episodes built: n=%d window=[%s .. %s] output=%s",
        result.n_episodes,
        result.window.start_ts,
        result.window.end_ts,
        result.episodes_path,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
