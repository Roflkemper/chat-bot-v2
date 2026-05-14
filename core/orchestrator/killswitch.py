from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from utils.safe_io import atomic_write_json, safe_read_json

logger = logging.getLogger(__name__)


@dataclass
class KillswitchEvent:
    triggered_at: datetime
    reason: str
    reason_value: Any
    disabled_at: datetime | None = None
    disabled_by: str | None = None


class KillswitchStore:
    _instance: "KillswitchStore | None" = None
    _lock = threading.Lock()

    def __init__(self, state_path: Path | str = Path("state/killswitch_state.json")) -> None:
        self._state_path = Path(state_path)
        self._state = self._load()

    @classmethod
    def instance(cls, state_path: Path | str | None = None) -> "KillswitchStore":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(state_path or Path("state/killswitch_state.json"))
        return cls._instance

    def _load(self) -> dict[str, Any]:
        default = {
            "version": 1,
            "active": False,
            "triggered_at": None,
            "reason": None,
            "reason_value": None,
            "manually_disabled_at": None,
            "history": [],
        }
        data = safe_read_json(str(self._state_path), default)
        return data or default

    def _save(self) -> None:
        atomic_write_json(str(self._state_path), self._state)

    def is_active(self) -> bool:
        return bool(self._state.get("active", False))

    def trigger(self, reason: str, reason_value: Any) -> None:
        now = datetime.now(timezone.utc)
        self._state["active"] = True
        self._state["triggered_at"] = now.isoformat()
        self._state["reason"] = reason
        self._state["reason_value"] = reason_value
        self._save()

    def disable(self, operator: str = "operator") -> None:
        if not self.is_active():
            return
        now = datetime.now(timezone.utc)
        event = {
            "triggered_at": self._state.get("triggered_at"),
            "reason": self._state.get("reason"),
            "reason_value": self._state.get("reason_value"),
            "disabled_at": now.isoformat(),
            "disabled_by": operator,
        }
        self._state.setdefault("history", []).append(event)
        self._state["active"] = False
        self._state["triggered_at"] = None
        self._state["reason"] = None
        self._state["reason_value"] = None
        self._state["manually_disabled_at"] = now.isoformat()
        self._save()

    def get_current_event(self) -> dict[str, Any] | None:
        if not self.is_active():
            return None
        return {
            "triggered_at": self._state.get("triggered_at"),
            "reason": self._state.get("reason"),
            "reason_value": self._state.get("reason_value"),
        }

    def get_history(self, limit: int = 5) -> list[dict[str, Any]]:
        history = list(self._state.get("history", []))
        if limit <= 0:
            return history
        return history[-limit:]


def trigger_killswitch(reason: str, reason_value: Any) -> str:
    from core.orchestrator.calibration_log import CalibrationLog
    from core.orchestrator.portfolio_state import PortfolioStore
    from renderers.killswitch_renderer import render_killswitch_alert

    store = KillswitchStore.instance()
    if store.is_active():
        logger.warning("[KILLSWITCH] Повторная активация проигнорирована: %s", reason)
        current = store.get_current_event() or {"reason": reason, "reason_value": reason_value}
        return render_killswitch_alert(str(current.get("reason")), current.get("reason_value"))

    store.trigger(reason, reason_value)
    calibration_log = CalibrationLog.instance()

    portfolio = PortfolioStore.instance()
    snapshot = portfolio.get_snapshot()
    for cat_key in snapshot.categories.keys():
        portfolio.set_category_action(cat_key, "KILLSWITCH", base_reason=f"Killswitch: {reason}")

    current_event = store.get_current_event() or {}
    calibration_log.log_killswitch_trigger(
        reason=reason,
        reason_value=reason_value,
        regime=str(current_event.get("reason") or "KILLSWITCH"),
        modifiers=[],
    )

    alert_text = render_killswitch_alert(reason, reason_value)
    logger.critical("[KILLSWITCH TRIGGERED]\n%s", alert_text)
    return alert_text
