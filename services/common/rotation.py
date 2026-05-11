"""Generic rotation helper for append-only jsonl state files.

Pattern used by setups.jsonl, gc_confirmation_audit.jsonl, p15_equity.jsonl,
pipeline_metrics.jsonl — all grow without bound. Without rotation, after a
year they become slow to read and waste disk.

Strategy:
  When file exceeds `max_bytes` (default 10MB), rename it to
  <name>_<YYYY-MM-DD>.jsonl and start a fresh file. Archives older
  than `keep_days` are deleted.

Idempotent: re-running rotation on a small file is a no-op.

Used by:
  - pipeline_metrics.py (built-in, ROTATE_AT_BYTES=5MB)
  - scripts/rotate_state_journals.py (cron-driven, this module)
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)


def rotate_if_large(
    path: Path,
    *,
    max_bytes: int = 10 * 1024 * 1024,
    keep_days: int = 30,
    archive_suffix: str = "%Y-%m-%d",
) -> str:
    """If `path` exceeds `max_bytes`, rename to dated archive + prune old.

    Returns one of: "skipped", "rotated", "appended_to_existing_archive".
    Never raises on filesystem errors — logs and returns "error".
    """
    try:
        if not path.exists():
            return "skipped"
        if path.stat().st_size < max_bytes:
            return "skipped"
        today = time.strftime(archive_suffix, time.gmtime())
        archive = path.with_name(f"{path.stem}_{today}{path.suffix}")

        if archive.exists():
            # Already rotated today — append current → existing archive.
            with path.open("rb") as src, archive.open("ab") as dst:
                dst.write(src.read())
            path.unlink()
            result = "appended_to_existing_archive"
        else:
            path.rename(archive)
            result = "rotated"

        # Prune archives older than keep_days.
        cutoff = time.time() - keep_days * 86400
        for old in path.parent.glob(f"{path.stem}_*{path.suffix}"):
            try:
                if old.stat().st_mtime < cutoff:
                    old.unlink()
                    logger.info("rotation.pruned %s", old.name)
            except OSError:
                pass

        return result
    except OSError as exc:
        logger.exception("rotation.failed path=%s error=%s", path, exc)
        return "error"
