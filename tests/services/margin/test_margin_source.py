"""Tests for services.margin.margin_source.

Covers:
- /margin command parsing & validation (valid args, bad ranges, bad format).
- append_override creates and appends.
- read_latest_margin source resolution: newer wins, missing handled, both empty.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from services.margin import (
    MarginCommandError,
    MarginRecord,
    append_override,
    parse_override_command,
    read_latest_margin,
)


# ── /margin parsing ─────────────────────────────────────────────────────────


def test_parse_valid_three_args() -> None:
    rec = parse_override_command("/margin 0.97 20434 18.0")
    assert rec.coefficient == 0.97
    assert rec.available_margin_usd == 20434.0
    assert rec.distance_to_liquidation_pct == 18.0
    assert rec.source == "telegram_operator"
    assert rec.ts.endswith("Z")


def test_parse_accepts_comma_decimals() -> None:
    rec = parse_override_command("/margin 0,97 20434 18,0")
    assert rec.coefficient == 0.97
    assert rec.distance_to_liquidation_pct == 18.0


def test_parse_without_command_token() -> None:
    rec = parse_override_command("0.5 1000 50")
    assert rec.coefficient == 0.5


def test_parse_wrong_arg_count() -> None:
    with pytest.raises(MarginCommandError, match="Использование"):
        parse_override_command("/margin 0.97 20434")


def test_parse_non_numeric() -> None:
    # Flex parser (c280b3b) extracts 'abc' as zero numbers — only 2 numbers
    # remain (20434, 18.0), so we get the 'Нужно 3 числа' error.
    with pytest.raises(MarginCommandError, match="Нужно 3 числа"):
        parse_override_command("/margin abc 20434 18.0")


def test_parse_coefficient_above_one() -> None:
    # Flex parser treats 1.0 < x ≤ 100 as percent (1.5 → 0.015), so 1.5 is
    # accepted. The reject path is now coefficient > 100 only.
    with pytest.raises(MarginCommandError, match="coefficient"):
        parse_override_command("/margin 150 20434 18.0")


def test_parse_coefficient_negative() -> None:
    with pytest.raises(MarginCommandError, match="coefficient"):
        parse_override_command("/margin -0.1 20434 18.0")


def test_parse_available_negative() -> None:
    with pytest.raises(MarginCommandError, match="available"):
        parse_override_command("/margin 0.5 -100 18.0")


def test_parse_distance_above_hundred() -> None:
    with pytest.raises(MarginCommandError, match="distance"):
        parse_override_command("/margin 0.5 1000 150")


def test_parse_distance_negative() -> None:
    with pytest.raises(MarginCommandError, match="distance"):
        parse_override_command("/margin 0.5 1000 -1")


def test_parse_empty() -> None:
    with pytest.raises(MarginCommandError):
        parse_override_command("")


# ── append_override ─────────────────────────────────────────────────────────


def test_append_creates_file_and_writes_jsonl(tmp_path: Path) -> None:
    p = tmp_path / "subdir" / "margin_overrides.jsonl"
    rec = parse_override_command("/margin 0.97 20434 18.0")
    append_override(rec, path=p)
    assert p.exists()
    line = p.read_text(encoding="utf-8").strip()
    parsed = json.loads(line)
    assert parsed["coefficient"] == 0.97
    assert parsed["source"] == "telegram_operator"


def test_append_multiple_calls_append_not_overwrite(tmp_path: Path) -> None:
    p = tmp_path / "margin_overrides.jsonl"
    rec1 = parse_override_command("/margin 0.5 10000 30.0")
    rec2 = parse_override_command("/margin 0.6 9000 25.0")
    append_override(rec1, path=p)
    append_override(rec2, path=p)
    lines = p.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2


# ── read_latest_margin source resolution ────────────────────────────────────


def _write_jsonl(p: Path, recs: list[dict]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fh:
        for r in recs:
            fh.write(json.dumps(r) + "\n")


def _rec(ts: str, coef: float = 0.5, source: str = "telegram_operator") -> dict:
    return {
        "ts": ts,
        "coefficient": coef,
        "available_margin_usd": 1000.0,
        "distance_to_liquidation_pct": 50.0,
        "source": source,
    }


def test_resolve_both_missing_returns_none(tmp_path: Path) -> None:
    out = read_latest_margin(
        override_path=tmp_path / "ovr.jsonl",
        automated_path=tmp_path / "auto.jsonl",
    )
    assert out is None


def test_resolve_only_override(tmp_path: Path) -> None:
    o = tmp_path / "ovr.jsonl"
    _write_jsonl(o, [_rec("2026-05-06T10:00:00Z", 0.9)])
    out = read_latest_margin(override_path=o, automated_path=tmp_path / "auto.jsonl")
    assert out is not None and out.coefficient == 0.9


def test_resolve_only_automated(tmp_path: Path) -> None:
    a = tmp_path / "auto.jsonl"
    _write_jsonl(a, [_rec("2026-05-06T10:00:00Z", 0.7, source="exchange_api")])
    out = read_latest_margin(override_path=tmp_path / "ovr.jsonl", automated_path=a)
    assert out is not None and out.source == "exchange_api"


def test_resolve_override_newer_than_automated(tmp_path: Path) -> None:
    o = tmp_path / "ovr.jsonl"
    a = tmp_path / "auto.jsonl"
    _write_jsonl(o, [_rec("2026-05-06T11:00:00Z", 0.9)])
    _write_jsonl(a, [_rec("2026-05-06T10:00:00Z", 0.7, source="exchange_api")])
    out = read_latest_margin(override_path=o, automated_path=a)
    assert out is not None and out.coefficient == 0.9
    assert out.source == "telegram_operator"


def test_resolve_automated_newer_than_override(tmp_path: Path) -> None:
    o = tmp_path / "ovr.jsonl"
    a = tmp_path / "auto.jsonl"
    _write_jsonl(o, [_rec("2026-05-06T10:00:00Z", 0.9)])
    _write_jsonl(a, [_rec("2026-05-06T11:00:00Z", 0.7, source="exchange_api")])
    out = read_latest_margin(override_path=o, automated_path=a)
    assert out is not None and out.source == "exchange_api"


def test_resolve_takes_last_record_within_file(tmp_path: Path) -> None:
    """Within a file, the last appended record (newest in jsonl order) is used."""
    o = tmp_path / "ovr.jsonl"
    _write_jsonl(o, [
        _rec("2026-05-06T09:00:00Z", 0.5),
        _rec("2026-05-06T10:00:00Z", 0.7),
        _rec("2026-05-06T11:00:00Z", 0.9),
    ])
    out = read_latest_margin(override_path=o, automated_path=tmp_path / "auto.jsonl")
    assert out is not None and out.coefficient == 0.9


def test_resolve_skips_corrupted_lines(tmp_path: Path) -> None:
    o = tmp_path / "ovr.jsonl"
    o.parent.mkdir(parents=True, exist_ok=True)
    o.write_text(
        json.dumps(_rec("2026-05-06T09:00:00Z", 0.5)) + "\n"
        + "this is not json\n"
        + json.dumps(_rec("2026-05-06T11:00:00Z", 0.9)) + "\n",
        encoding="utf-8",
    )
    out = read_latest_margin(override_path=o, automated_path=tmp_path / "auto.jsonl")
    assert out is not None and out.coefficient == 0.9
