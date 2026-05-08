"""Tests for services.telegram.send_dedup."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from services.telegram import send_dedup


def test_first_send_allowed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(send_dedup, "DEDUP_PATH", tmp_path / "dedup.json")
    assert send_dedup.should_send(1, "LEVEL_BREAK level=80000") is True


def test_duplicate_within_ttl_blocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(send_dedup, "DEDUP_PATH", tmp_path / "dedup.json")
    chat = 574716090
    text = "🎯 LEVEL_BREAK [16:52:11] level=81695.0 direction=up price=81705.5"
    assert send_dedup.should_send(chat, text) is True
    send_dedup.mark_sent(chat, text)
    # Within TTL — should be blocked
    assert send_dedup.should_send(chat, text) is False


def test_after_ttl_allowed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(send_dedup, "DEDUP_PATH", tmp_path / "dedup.json")
    monkeypatch.setattr(send_dedup, "TTL_SECONDS", 1)
    send_dedup.mark_sent(1, "test")
    time.sleep(1.1)
    assert send_dedup.should_send(1, "test") is True


def test_different_text_not_blocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(send_dedup, "DEDUP_PATH", tmp_path / "dedup.json")
    send_dedup.mark_sent(1, "alert A")
    assert send_dedup.should_send(1, "alert B") is True


def test_different_chat_not_blocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(send_dedup, "DEDUP_PATH", tmp_path / "dedup.json")
    send_dedup.mark_sent(1, "alert")
    assert send_dedup.should_send(2, "alert") is True


def test_4x_spam_scenario_blocks_3(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Reproduces operator screenshot — 4 identical LEVEL_BREAK in same second."""
    monkeypatch.setattr(send_dedup, "DEDUP_PATH", tmp_path / "dedup.json")
    chat = 574716090
    text = "🎯 LEVEL_BREAK [16:52:11] level=81695.0 direction=up price=81705.5"
    sent_count = 0
    for _ in range(4):
        if send_dedup.should_send(chat, text):
            send_dedup.mark_sent(chat, text)
            sent_count += 1
    assert sent_count == 1  # only first succeeds


def test_persists_across_load(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Restart-resilient — second instance should see prior dedup state."""
    p = tmp_path / "dedup.json"
    monkeypatch.setattr(send_dedup, "DEDUP_PATH", p)
    send_dedup.mark_sent(1, "msg")
    # Simulate restart — file persists; new should_send sees it
    assert send_dedup.should_send(1, "msg") is False
