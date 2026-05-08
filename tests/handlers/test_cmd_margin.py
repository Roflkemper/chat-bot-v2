"""Telegram /margin command — handler-level test.

Exercises the actions.margin() method end-to-end on the real ctx wiring,
verifying happy path + rejection paths produce the expected reply text and
side effects (jsonl append).
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from handlers.command_actions import CommandActions, CommandActionContext


def _make_ctx(command: str) -> CommandActionContext:
    return CommandActionContext(
        command=command,
        timeframe="1H",
        snapshot_loader=MagicMock(),
    )


def _extract_text(payload) -> str:
    """Pull the body text out of a BotResponsePayload regardless of its concrete shape."""
    for attr in ("text", "body", "message", "content"):
        v = getattr(payload, attr, None)
        if isinstance(v, str) and v:
            return v
    # Fall back to str() — payload likely formats itself
    return str(payload)


def test_margin_happy_path_appends_record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    actions = CommandActions(_make_ctx("/margin 0.97 20434 18.0"))
    payload = actions.margin()
    text = _extract_text(payload)
    assert "MARGIN OVERRIDE" in text
    p = tmp_path / "state" / "manual_overrides" / "margin_overrides.jsonl"
    assert p.exists()
    rec = json.loads(p.read_text(encoding="utf-8").strip())
    assert rec["coefficient"] == 0.97
    assert rec["available_margin_usd"] == 20434.0
    assert rec["distance_to_liquidation_pct"] == 18.0
    assert rec["source"] == "telegram_operator"


def test_margin_invalid_format_rejects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    actions = CommandActions(_make_ctx("/margin 0.97 20434"))
    payload = actions.margin()
    text = _extract_text(payload)
    assert "❌" in text
    assert "Использование" in text
    # No file written on rejection
    p = tmp_path / "state" / "manual_overrides" / "margin_overrides.jsonl"
    assert not p.exists()


def test_margin_invalid_coefficient_rejects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    # Flex parser (c280b3b) interprets 1<x≤100 as percent; reject path is now >100.
    actions = CommandActions(_make_ctx("/margin 150 20434 18.0"))
    payload = actions.margin()
    text = _extract_text(payload)
    assert "❌" in text
    assert "coefficient" in text
    p = tmp_path / "state" / "manual_overrides" / "margin_overrides.jsonl"
    assert not p.exists()


def test_margin_two_calls_append_not_overwrite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    CommandActions(_make_ctx("/margin 0.5 10000 30.0")).margin()
    CommandActions(_make_ctx("/margin 0.6 9500 25.0")).margin()
    p = tmp_path / "state" / "manual_overrides" / "margin_overrides.jsonl"
    lines = p.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
