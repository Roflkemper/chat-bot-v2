from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import threading
from typing import Any, Dict, List, Optional

from utils.safe_io import atomic_write_json, safe_read_json


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _dt_to_str(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat()


def _str_to_dt(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _default_portfolio_state() -> Dict[str, Any]:
    now_iso = _dt_to_str(_utc_now())
    return {
        "version": 3,
        "updated_at": now_iso,
        "categories": {
            "btc_short": {
                "asset": "BTC",
                "side": "SHORT",
                "contract_type": "inverse",
                "label_ru": "BTC ШОРТ",
                "orchestrator_action": "RUN",
                "base_reason": "",
                "modifiers_active": [],
                "last_command_at": None,
                "enabled": True,
            },
            "btc_long": {
                "asset": "BTC",
                "side": "LONG",
                "contract_type": "linear",
                "label_ru": "BTC ЛОНГ",
                "orchestrator_action": "RUN",
                "base_reason": "",
                "modifiers_active": [],
                "last_command_at": None,
                "enabled": True,
            },
            "btc_long_l2": {
                "asset": "BTC",
                "side": "LONG",
                "contract_type": "linear",
                "label_ru": "BTC ЛОНГ ИМПУЛЬС",
                "orchestrator_action": "ARM",
                "base_reason": "",
                "modifiers_active": [],
                "last_command_at": None,
                "enabled": True,
            },
        },
        "bots": {
            "btc_short_l1": {
                "category": "btc_short",
                "label": "BTC SHORT L1 (base)",
                "strategy_type": "GRID_L1",
                "stage": "LIVE",
                "state": "ACTIVE",
                "params": {
                    "step_pct": 0.03,
                    "target_pct": 0.19,
                    "max_orders": 110,
                    "order_btc": 0.003,
                    "instop_pct": 0.025,
                },
                "consecutive_stops": 0,
                "killswitch_triggered": False,
                "created_at": now_iso,
            },
        },
        "portfolio_state": {
            "mode": "NORMAL",
            "daily_pnl_usd": 0.0,
            "margin_used_pct": 0.0,
            "last_killswitch_at": None,
        },
    }


@dataclass
class Category:
    key: str
    asset: str
    side: str
    contract_type: str
    label_ru: str
    orchestrator_action: str = "RUN"
    base_reason: str = ""
    modifiers_active: List[str] = field(default_factory=list)
    last_command_at: Optional[datetime] = None
    enabled: bool = True


@dataclass
class Bot:
    key: str
    category: str
    label: str
    strategy_type: str
    stage: str
    state: str = "PLANNED"
    params: Dict[str, Any] = field(default_factory=dict)
    balance_usd: float = 0.0
    consecutive_stops: int = 0
    killswitch_triggered: bool = False
    created_at: datetime = field(default_factory=_utc_now)


@dataclass
class PortfolioSnapshot:
    categories: Dict[str, Category]
    bots: Dict[str, Bot]
    mode: str
    daily_pnl_usd: float
    margin_used_pct: float
    updated_at: datetime


class PortfolioStore:
    _instance: Optional["PortfolioStore"] = None
    _instance_lock = threading.Lock()

    def __init__(self, path: str = "state/grid_portfolio.json") -> None:
        self.path = Path(path)
        self._write_lock = threading.Lock()
        self._state: Dict[str, Any] | None = None

    @classmethod
    def instance(cls) -> "PortfolioStore":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def get_snapshot(self) -> PortfolioSnapshot:
        state = self._ensure_loaded()
        categories = {
            key: self._category_from_dict(key, raw)
            for key, raw in (state.get("categories") or {}).items()
        }
        bots = {
            key: self._bot_from_dict(key, raw)
            for key, raw in (state.get("bots") or {}).items()
        }
        portfolio_state = state.get("portfolio_state") or {}
        return PortfolioSnapshot(
            categories=categories,
            bots=bots,
            mode=str(portfolio_state.get("mode") or "NORMAL"),
            daily_pnl_usd=float(portfolio_state.get("daily_pnl_usd") or 0.0),
            margin_used_pct=float(portfolio_state.get("margin_used_pct") or 0.0),
            updated_at=_str_to_dt(state.get("updated_at")) or _utc_now(),
        )

    def get_category(self, key: str) -> Optional[Category]:
        state = self._ensure_loaded()
        raw = (state.get("categories") or {}).get(key)
        return self._category_from_dict(key, raw) if raw else None

    def get_bot(self, key: str) -> Optional[Bot]:
        state = self._ensure_loaded()
        raw = (state.get("bots") or {}).get(key)
        return self._bot_from_dict(key, raw) if raw else None

    def get_bots_in_category(self, category_key: str) -> List[Bot]:
        state = self._ensure_loaded()
        bots = []
        for key, raw in (state.get("bots") or {}).items():
            if str((raw or {}).get("category") or "") == category_key:
                bots.append(self._bot_from_dict(key, raw))
        return bots

    def list_categories(self) -> List[Category]:
        return list(self.get_snapshot().categories.values())

    def list_bots(self) -> List[Bot]:
        return list(self.get_snapshot().bots.values())

    def set_category_action(
        self,
        key: str,
        action: str,
        base_reason: str = "",
        modifiers: Optional[List[str]] = None,
    ) -> bool:
        from core.orchestrator.killswitch import KillswitchStore

        with self._write_lock:
            state = self._ensure_loaded()
            categories = state.setdefault("categories", {})
            category = categories.get(key)
            if not isinstance(category, dict):
                return False

            action_up = str(action or "").upper()
            ks = KillswitchStore.instance()
            if ks.is_active() and action_up != "KILLSWITCH":
                return False
            category["orchestrator_action"] = action_up
            category["base_reason"] = str(base_reason or "")
            category["modifiers_active"] = list(modifiers or [])
            category["last_command_at"] = _dt_to_str(_utc_now())

            for bot in (state.get("bots") or {}).values():
                if not isinstance(bot, dict) or bot.get("category") != key:
                    continue
                current_state = str(bot.get("state") or "")
                if action_up == "RUN" and current_state == "PAUSED_BY_REGIME":
                    bot["state"] = "ACTIVE"
                    bot["killswitch_triggered"] = False
                elif action_up in {"PAUSE", "STOP"} and current_state == "ACTIVE":
                    bot["state"] = "PAUSED_BY_REGIME"
                    bot["killswitch_triggered"] = False
                elif action_up == "KILLSWITCH" and current_state != "PAUSED_MANUAL":
                    bot["state"] = "KILLSWITCH"
                    bot["killswitch_triggered"] = True

            self._touch_updated_at(state)
            if action_up == "KILLSWITCH":
                state.setdefault("portfolio_state", {})["last_killswitch_at"] = _dt_to_str(_utc_now())
            self._persist_state(state)
            return True

    def set_bot_state(self, key: str, state_value: str) -> bool:
        with self._write_lock:
            state = self._ensure_loaded()
            bot = (state.get("bots") or {}).get(key)
            if not isinstance(bot, dict):
                return False
            bot["state"] = str(state_value or "")
            self._touch_updated_at(state)
            self._persist_state(state)
            return True

    def add_bot(self, bot: Bot) -> bool:
        with self._write_lock:
            state = self._ensure_loaded()
            bots = state.setdefault("bots", {})
            if bot.key in bots:
                return False
            bots[bot.key] = self._bot_to_dict(bot)
            self._touch_updated_at(state)
            self._persist_state(state)
            return True

    def remove_bot(self, key: str) -> bool:
        with self._write_lock:
            state = self._ensure_loaded()
            bot = (state.get("bots") or {}).get(key)
            if not isinstance(bot, dict):
                return False
            bot["state"] = "ARCHIVED"
            bot["stage"] = "ARCHIVED"
            self._touch_updated_at(state)
            self._persist_state(state)
            return True

    def _ensure_loaded(self) -> Dict[str, Any]:
        if self._state is None:
            self._state = self._load_or_create_state()
        return self._state

    def _load_or_create_state(self) -> Dict[str, Any]:
        default = _default_portfolio_state()
        payload = safe_read_json(str(self.path), default)
        if not self.path.exists():
            atomic_write_json(str(self.path), payload)
        return payload

    def _persist_state(self, state: Dict[str, Any]) -> None:
        self._state = deepcopy(state)
        atomic_write_json(str(self.path), self._state)

    @staticmethod
    def _touch_updated_at(state: Dict[str, Any]) -> None:
        state["updated_at"] = _dt_to_str(_utc_now())

    @staticmethod
    def _category_from_dict(key: str, raw: Dict[str, Any]) -> Category:
        return Category(
            key=key,
            asset=str(raw.get("asset") or ""),
            side=str(raw.get("side") or ""),
            contract_type=str(raw.get("contract_type") or ""),
            label_ru=str(raw.get("label_ru") or key),
            orchestrator_action=str(raw.get("orchestrator_action") or "RUN"),
            base_reason=str(raw.get("base_reason") or ""),
            modifiers_active=list(raw.get("modifiers_active") or []),
            last_command_at=_str_to_dt(raw.get("last_command_at")),
            enabled=bool(raw.get("enabled", True)),
        )

    @staticmethod
    def _bot_from_dict(key: str, raw: Dict[str, Any]) -> Bot:
        return Bot(
            key=key,
            category=str(raw.get("category") or ""),
            label=str(raw.get("label") or key),
            strategy_type=str(raw.get("strategy_type") or ""),
            stage=str(raw.get("stage") or "PLANNED"),
            state=str(raw.get("state") or "PLANNED"),
            params=dict(raw.get("params") or {}),
            balance_usd=float(raw.get("balance_usd") or 0.0),
            consecutive_stops=int(raw.get("consecutive_stops") or 0),
            killswitch_triggered=bool(raw.get("killswitch_triggered") or False),
            created_at=_str_to_dt(raw.get("created_at")) or _utc_now(),
        )

    @staticmethod
    def _bot_to_dict(bot: Bot) -> Dict[str, Any]:
        return {
            "category": bot.category,
            "label": bot.label,
            "strategy_type": bot.strategy_type,
            "stage": bot.stage,
            "state": bot.state,
            "params": dict(bot.params),
            "balance_usd": float(bot.balance_usd),
            "consecutive_stops": int(bot.consecutive_stops),
            "killswitch_triggered": bool(bot.killswitch_triggered),
            "created_at": _dt_to_str(bot.created_at),
        }
