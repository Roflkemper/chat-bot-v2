"""Regression tests for supervisor.daemon imports."""

from __future__ import annotations

import importlib
import inspect
import config
from _pytest.monkeypatch import MonkeyPatch


def test_supervisor_daemon_imports_without_error() -> None:
    module = importlib.import_module("src.supervisor.daemon")
    assert module is not None


def test_supervisor_daemon_uses_canonical_config_names() -> None:
    assert hasattr(config, "BOT_TOKEN"), "config.BOT_TOKEN missing"
    assert hasattr(config, "CHAT_ID"), "config.CHAT_ID missing"


def test_supervisor_daemon_no_dead_imports() -> None:
    from src.supervisor import daemon

    source = inspect.getsource(daemon)
    for line in source.splitlines():
        stripped = line.strip()
        assert "from config import TELEGRAM_BOT_TOKEN" not in stripped
        assert "from config import AUTHORIZED_CHAT_IDS" not in stripped


def test_alerting_function_callable(monkeypatch: MonkeyPatch) -> None:
    from src.supervisor import daemon

    calls: list[tuple[str, dict[str, object], int]] = []

    class FakeRequests:
        @staticmethod
        def post(url: str, json: dict[str, object], timeout: int) -> None:
            calls.append((url, json, timeout))

    monkeypatch.setattr(config, "BOT_TOKEN", "123:token", raising=False)
    monkeypatch.setattr(config, "CHAT_ID", "1,2", raising=False)
    monkeypatch.setitem(__import__("sys").modules, "requests", FakeRequests)
    daemon._send_telegram_alarm("test message")
    assert len(calls) == 2
