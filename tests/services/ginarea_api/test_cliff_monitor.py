"""Tests for cliff_monitor."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from services.ginarea_api.cliff_monitor import (
    CLIFF_DANGER_USD,
    CLIFF_WARNING_USD,
    check_short_bag_aggregate,
    check_short_t2_bots,
)


def _mk(bot_id="b1", position_btc=-0.5, unrealized=0.0, alias=""):
    return {
        "bot_id": bot_id,
        "alias": alias,
        "position_btc": position_btc,
        "unrealized_usd": unrealized,
    }


def test_no_alert_when_within_normal_range(tmp_path: Path) -> None:
    send = MagicMock()
    alerts = check_short_t2_bots(
        [_mk(unrealized=-500.0)],
        send_fn=send,
        state_path=tmp_path / "s.json",
    )
    assert alerts == []
    send.assert_not_called()


def test_warning_alert_fires_once(tmp_path: Path) -> None:
    p = tmp_path / "s.json"
    send = MagicMock()
    alerts = check_short_t2_bots(
        [_mk(unrealized=-1_700.0)],
        send_fn=send, state_path=p,
    )
    assert len(alerts) == 1
    assert alerts[0].severity == "warning"
    send.assert_called_once()
    # second tick — no re-notify
    send.reset_mock()
    alerts2 = check_short_t2_bots(
        [_mk(unrealized=-1_700.0)],
        send_fn=send, state_path=p,
    )
    assert alerts2 == []
    send.assert_not_called()


def test_escalation_warning_to_danger(tmp_path: Path) -> None:
    p = tmp_path / "s.json"
    send = MagicMock()
    check_short_t2_bots([_mk(unrealized=-1_700.0)], send_fn=send, state_path=p)
    send.reset_mock()
    alerts = check_short_t2_bots([_mk(unrealized=-3_500.0)], send_fn=send, state_path=p)
    assert len(alerts) == 1
    assert alerts[0].severity == "danger"
    send.assert_called_once()
    assert "DANGER" in send.call_args[0][0]


def test_recovery_resets_state(tmp_path: Path) -> None:
    """Если unrealized вернулся в норму, alert при повторном падении — снова шлётся."""
    p = tmp_path / "s.json"
    send = MagicMock()
    check_short_t2_bots([_mk(unrealized=-1_700.0)], send_fn=send, state_path=p)
    send.reset_mock()
    # Recovery
    check_short_t2_bots([_mk(unrealized=-200.0)], send_fn=send, state_path=p)
    send.assert_not_called()
    # Падение опять — должно сработать
    alerts = check_short_t2_bots([_mk(unrealized=-1_700.0)], send_fn=send, state_path=p)
    assert len(alerts) == 1
    send.assert_called_once()


def test_long_bots_ignored(tmp_path: Path) -> None:
    send = MagicMock()
    alerts = check_short_t2_bots(
        [_mk(position_btc=0.5, unrealized=-2_000.0)],  # positive position = LONG
        send_fn=send, state_path=tmp_path / "s.json",
    )
    assert alerts == []
    send.assert_not_called()


def test_thresholds_match_constants() -> None:
    assert CLIFF_WARNING_USD == -1_500.0
    assert CLIFF_DANGER_USD == -3_000.0


def test_bag_aggregate_warning(tmp_path: Path) -> None:
    """4 бота × −$500 = −$2 000 (warning). Каждый отдельный под порогом."""
    send = MagicMock()
    state_p = tmp_path / "s.json"
    bots = [_mk(bot_id=f"b{i}", unrealized=-500.0) for i in range(4)]
    alert = check_short_bag_aggregate(bots, send_fn=send, state_path=state_p)
    assert alert is not None
    assert alert.severity == "warning"
    assert alert.unrealized_usd == -2_000.0
    send.assert_called_once()
    msg = send.call_args[0][0]
    assert "SHORT-bag" in msg or "SHORT-BAG" in msg


def test_bag_aggregate_danger_at_3000(tmp_path: Path) -> None:
    """Реальная ситуация 13.05: 4 × −$700 = −$2 800, граница warning."""
    send = MagicMock()
    bots = [_mk(bot_id=f"b{i}", unrealized=-800.0) for i in range(4)]  # −$3200
    alert = check_short_bag_aggregate(bots, send_fn=send, state_path=tmp_path / "s.json")
    assert alert is not None
    assert alert.severity == "danger"
    assert "DANGER" in send.call_args[0][0]


def test_bag_aggregate_recovery_resets(tmp_path: Path) -> None:
    send = MagicMock()
    state_p = tmp_path / "s.json"
    # Initial warning
    check_short_bag_aggregate(
        [_mk(bot_id=f"b{i}", unrealized=-500.0) for i in range(4)],
        send_fn=send, state_path=state_p,
    )
    # Recovery
    send.reset_mock()
    check_short_bag_aggregate(
        [_mk(bot_id=f"b{i}", unrealized=-200.0) for i in range(4)],
        send_fn=send, state_path=state_p,
    )
    send.assert_not_called()
    # Same warning again → fires
    alert = check_short_bag_aggregate(
        [_mk(bot_id=f"b{i}", unrealized=-500.0) for i in range(4)],
        send_fn=send, state_path=state_p,
    )
    assert alert is not None


def test_bag_aggregate_long_bots_ignored(tmp_path: Path) -> None:
    """LONG-bots (position_btc > 0) не учитываются в bag."""
    send = MagicMock()
    bots = [_mk(bot_id="long1", position_btc=0.5, unrealized=-2_000.0)]
    alert = check_short_bag_aggregate(bots, send_fn=send, state_path=tmp_path / "s.json")
    assert alert is None
    send.assert_not_called()
