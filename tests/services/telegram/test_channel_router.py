"""Tests for channel_router routing logic."""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

from services.telegram.channel_router import build_send_fn, get_routine_chat_ids


def test_routine_chat_ids_parse():
    with patch.dict(os.environ, {"ROUTINE_CHAT_IDS": "111, 222 ;333"}):
        assert sorted(get_routine_chat_ids()) == [111, 222, 333]


def test_routine_chat_ids_empty_when_unset():
    with patch.dict(os.environ, {"ROUTINE_CHAT_IDS": ""}):
        assert get_routine_chat_ids() == []


def test_routine_chat_ids_ignores_garbage():
    with patch.dict(os.environ, {"ROUTINE_CHAT_IDS": "111,abc,222"}):
        assert sorted(get_routine_chat_ids()) == [111, 222]


def _make_app(allowed=(100, 200)):
    app = MagicMock()
    app.allowed_chat_ids = list(allowed)
    app.bot = MagicMock()
    return app


def test_primary_emitter_sent_to_primary_chats():
    app = _make_app()
    with patch.dict(os.environ, {"ROUTINE_CHAT_IDS": "999"}):
        send = build_send_fn(app, "LIQ_CASCADE")
    send("hello", meta={"qty_btc": 5})
    sent = [call.args[0] for call in app.bot.send_message.call_args_list]
    assert sorted(sent) == [100, 200]


def test_routine_emitter_sent_to_routine_chat():
    app = _make_app()
    with patch.dict(os.environ, {"ROUTINE_CHAT_IDS": "999,888"}):
        send = build_send_fn(app, "P15_REENTRY")
    send("layer #4")
    sent = [call.args[0] for call in app.bot.send_message.call_args_list]
    assert sorted(sent) == [888, 999]


def test_routine_falls_back_to_primary_when_unset():
    app = _make_app()
    with patch.dict(os.environ, {"ROUTINE_CHAT_IDS": ""}):
        send = build_send_fn(app, "P15_REENTRY")
    send("layer #4")
    sent = [call.args[0] for call in app.bot.send_message.call_args_list]
    assert sorted(sent) == [100, 200]


def test_severity_prefix_applied():
    app = _make_app()
    with patch.dict(os.environ, {"ROUTINE_CHAT_IDS": ""}):
        send = build_send_fn(app, "LIQ_CASCADE")
    send("МЕГА-СПАЙК", meta={"qty_btc": 13})
    text = app.bot.send_message.call_args_list[0].args[1]
    assert text.startswith("🔴 ")


def test_returns_none_when_no_chats():
    app = MagicMock()
    app.allowed_chat_ids = []
    assert build_send_fn(app, "LIQ_CASCADE") is None
