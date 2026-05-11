"""Tests for services.common.rotation."""
from __future__ import annotations

import time

from services.common.rotation import rotate_if_large


def test_rotate_skips_when_small(tmp_path):
    p = tmp_path / "small.jsonl"
    p.write_text("just a few bytes\n", encoding="utf-8")
    result = rotate_if_large(p, max_bytes=1024)
    assert result == "skipped"
    assert p.exists()
    assert p.read_text(encoding="utf-8") == "just a few bytes\n"


def test_rotate_skips_when_missing(tmp_path):
    p = tmp_path / "absent.jsonl"
    result = rotate_if_large(p, max_bytes=1024)
    assert result == "skipped"


def test_rotate_moves_when_oversized(tmp_path):
    p = tmp_path / "big.jsonl"
    p.write_text("x" * 2048, encoding="utf-8")
    result = rotate_if_large(p, max_bytes=1024, keep_days=30)
    assert result == "rotated"
    assert not p.exists()
    archives = list(tmp_path.glob("big_*.jsonl"))
    assert len(archives) == 1


def test_rotate_appends_when_archive_exists(tmp_path):
    """If today's archive already exists, second rotation appends instead
    of overwriting."""
    p = tmp_path / "j.jsonl"
    p.write_text("first batch\n" * 200, encoding="utf-8")
    rotate_if_large(p, max_bytes=100)
    # Recreate the file and rotate again.
    p.write_text("second batch\n" * 200, encoding="utf-8")
    result = rotate_if_large(p, max_bytes=100)
    assert result == "appended_to_existing_archive"
    archives = list(tmp_path.glob("j_*.jsonl"))
    assert len(archives) == 1
    content = archives[0].read_text(encoding="utf-8")
    assert "first batch" in content
    assert "second batch" in content


def test_rotate_prunes_old_archives(tmp_path):
    """Archives older than keep_days are deleted on next rotation."""
    p = tmp_path / "j.jsonl"
    # Create an old-looking archive.
    old = tmp_path / "j_2020-01-01.jsonl"
    old.write_text("ancient", encoding="utf-8")
    # Backdate it 60 days.
    sixty_days_ago = time.time() - 60 * 86400
    import os
    os.utime(old, (sixty_days_ago, sixty_days_ago))

    # Now trigger rotation on a fresh oversized file.
    p.write_text("y" * 2048, encoding="utf-8")
    rotate_if_large(p, max_bytes=1024, keep_days=30)

    assert not old.exists()
