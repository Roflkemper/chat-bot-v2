from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from services.telegram_alert_client import TelegramAlertClient


@pytest.fixture(autouse=True)
def reset_singleton():
    TelegramAlertClient.reset()
    yield
    TelegramAlertClient.reset()


def test_disabled_when_no_token(monkeypatch):
    monkeypatch.setattr("config.BOT_TOKEN", "")
    monkeypatch.setattr("config.CHAT_ID", "123")
    monkeypatch.setattr("config.ENABLE_TELEGRAM", True)
    client = TelegramAlertClient()
    assert client.is_enabled() is False


def test_disabled_when_no_chat_id(monkeypatch):
    monkeypatch.setattr("config.BOT_TOKEN", "123:abc")
    monkeypatch.setattr("config.CHAT_ID", "")
    monkeypatch.setattr("config.ENABLE_TELEGRAM", True)
    client = TelegramAlertClient()
    assert client.is_enabled() is False


def test_disabled_when_telegram_off(monkeypatch):
    monkeypatch.setattr("config.BOT_TOKEN", "123:abc")
    monkeypatch.setattr("config.CHAT_ID", "123")
    monkeypatch.setattr("config.ENABLE_TELEGRAM", False)
    client = TelegramAlertClient()
    assert client.is_enabled() is False


def test_parse_chat_ids():
    assert TelegramAlertClient._parse_chat_ids("123") == [123]
    assert TelegramAlertClient._parse_chat_ids("123,456") == [123, 456]
    assert TelegramAlertClient._parse_chat_ids("123; 456; 123") == [123, 456]
    assert TelegramAlertClient._parse_chat_ids("123, bad, 456") == [123, 456]


def test_send_success(monkeypatch):
    calls: list[tuple[int, str]] = []

    class _Bot:
        def send_message(self, chat_id, text):
            calls.append((chat_id, text))

    fake_telebot = SimpleNamespace(TeleBot=lambda token, parse_mode=None: _Bot())
    monkeypatch.setattr("config.BOT_TOKEN", "123:abc")
    monkeypatch.setattr("config.CHAT_ID", "1,2")
    monkeypatch.setattr("config.ENABLE_TELEGRAM", True)
    monkeypatch.setitem(sys.modules, "telebot", fake_telebot)

    client = TelegramAlertClient()
    assert client.is_enabled() is True
    assert client.send("hello") is True
    assert calls == [(1, "hello"), (2, "hello")]


def test_send_failure_returns_false(monkeypatch):
    class _Bot:
        def send_message(self, chat_id, text):
            raise RuntimeError("fail")

    fake_telebot = SimpleNamespace(TeleBot=lambda token, parse_mode=None: _Bot())
    monkeypatch.setattr("config.BOT_TOKEN", "123:abc")
    monkeypatch.setattr("config.CHAT_ID", "1")
    monkeypatch.setattr("config.ENABLE_TELEGRAM", True)
    monkeypatch.setitem(sys.modules, "telebot", fake_telebot)

    client = TelegramAlertClient()
    assert client.send("hello") is False
