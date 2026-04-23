from __future__ import annotations

import os
from pathlib import Path

from telegram_runtime import state as runtime_state
from telegram_ui.keyboards import build_main_keyboard, build_dynamic_keyboard


def test_runtime_state_registers_and_toggles(tmp_path, monkeypatch):
    state_file = tmp_path / 'telegram_runtime_state.json'
    monkeypatch.setattr(runtime_state, 'STATE_FILE', str(state_file))

    runtime_state.ensure_chat_registered(123)
    assert runtime_state.alerts_enabled(123) is True

    runtime_state.set_alerts_enabled(123, False)
    assert runtime_state.alerts_enabled(123) is False

    runtime_state.set_alerts_enabled(123, True)
    assert runtime_state.alerts_enabled(123) is True
    assert runtime_state.iter_alert_chat_ids() == [123]


def test_runtime_state_tracks_last_alert_text(tmp_path, monkeypatch):
    state_file = tmp_path / 'telegram_runtime_state.json'
    monkeypatch.setattr(runtime_state, 'STATE_FILE', str(state_file))

    runtime_state.ensure_chat_registered(555)
    runtime_state.set_last_alert_text(555, 'hello')
    assert runtime_state.last_alert_text(555) == 'hello'


def test_keyboards_build_without_telebot_dependency():
    main = build_main_keyboard()
    dynamic = build_dynamic_keyboard({'has_position': True, 'position_side': 'LONG'})
    assert hasattr(main, 'keyboard') or hasattr(main, 'to_dict')
    assert hasattr(dynamic, 'keyboard') or hasattr(dynamic, 'to_dict')
