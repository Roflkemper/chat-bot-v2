"""Smoke test: portfolio handler doesn't crash after ICT + decision_command + cost_model integrations.

Root cause history: on 2026-05-01 the /portfolio command appeared to fail with a
system error. Investigation showed it was a transient Telegram API network disconnect
(RemoteDisconnected) during send — the handler itself ran successfully.
This test guards against future import-level or runtime regressions.
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch


def test_portfolio_handler_imports():
    """All imports in portfolio command chain resolve without error."""
    from telegram_ui.portfolio.command import handle_portfolio_command  # noqa: F401
    from telegram_ui.portfolio.data_source import load_portfolio_data    # noqa: F401
    from telegram_ui.portfolio.formatter import format_portfolio          # noqa: F401


def test_portfolio_handler_returns_string(tmp_path):
    """handle_portfolio_command() returns a non-empty string on any data."""
    from telegram_ui.portfolio.command import handle_portfolio_command
    result = handle_portfolio_command()
    assert isinstance(result, str), f"Expected str, got {type(result)}"
    assert len(result) > 0, "Portfolio response was empty"


def test_portfolio_handler_no_exception_on_missing_snapshots(monkeypatch, tmp_path):
    """handler doesn't raise even when snapshots.csv is absent.

    NOTE: We mock _load_from_api to avoid it inserting ginarea_tracker/ into sys.path,
    which would shadow c:/bot7/storage/ with ginarea_tracker/storage.py and break
    subsequent imports of storage.position_store in the same test session.
    """
    import telegram_ui.portfolio.data_source as ds
    monkeypatch.setattr(ds, "SNAPSHOTS_CSV", tmp_path / "nonexistent.csv")
    monkeypatch.setattr(ds, "_load_from_api", lambda: [])
    from telegram_ui.portfolio.command import handle_portfolio_command
    result = handle_portfolio_command()
    assert isinstance(result, str)


def test_command_action_context_has_original_command_field():
    """CommandActionContext dataclass has original_command field (regression guard for decision_command integration)."""
    from handlers.command_actions import CommandActionContext
    import inspect
    fields = {f.name for f in __import__('dataclasses').fields(CommandActionContext)}
    assert "original_command" in fields, (
        "CommandActionContext.original_command field missing — breaks /decision notes preservation"
    )


def test_portfolio_registry_resolves():
    """CommandHandler registry resolves /portfolio without error."""
    from handlers.command_handler import CommandHandler
    registry = CommandHandler._build_registry()
    resolution = registry.resolve("/PORTFOLIO")
    assert resolution is not None, "/portfolio command not registered in dispatcher"
    assert resolution.entry.handler_name == "_cmd_portfolio"
