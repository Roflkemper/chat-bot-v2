from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, is_dataclass
from typing import cast
from typing import Any, Protocol

from .intervention_rules import InterventionDecision
from .models import InterventionEvent, InterventionType, MarketSnapshot


class SupportsManagedBot(Protocol):
    cfg: Any
    is_active: bool
    realized_pnl: float
    active_orders: list[Any]
    closed_orders: list[Any]

    def position_size(self) -> float: ...
    def avg_entry(self) -> float: ...
    def unrealized_pnl(self, price: float) -> float: ...


def _cfg_to_dict(cfg: Any) -> dict[str, Any]:
    if is_dataclass(cfg):
        data = asdict(cast(Any, cfg))
    else:
        data = dict(vars(cfg))
    contract = data.get("contract")
    side = data.get("side")
    if "contract_type" not in data and contract is not None:
        contract_type = getattr(getattr(contract, "contract_type", None), "value", None)
        if contract_type is not None:
            data["contract_type"] = contract_type
    if contract is not None and not isinstance(contract, (str, int, float, bool, type(None))):
        contract_value = getattr(getattr(contract, "contract_type", None), "value", None)
        data["contract"] = contract_value if contract_value is not None else str(contract)
    if side is not None and not isinstance(side, (str, int, float, bool, type(None))):
        data["side"] = getattr(side, "name", str(side)).lower()
    return data


def _set_nested_attr(obj: Any, path: str, value: Any) -> None:
    setattr(obj, path, value)


class InterventionExecutor:
    def __init__(self, bots: dict[str, SupportsManagedBot], bot_factory: Any | None = None) -> None:
        self.bots = bots
        self.bot_factory = bot_factory

    def apply(
        self,
        bot_id: str,
        decision: InterventionDecision,
        current_bar: Any,
        *,
        snapshot: MarketSnapshot,
    ) -> InterventionEvent:
        bot = self.bots[bot_id]
        before = _cfg_to_dict(bot.cfg)
        price = float(current_bar.close)
        pnl_usd = float(bot.unrealized_pnl(price))

        if decision.intervention_type == InterventionType.PAUSE_NEW_ENTRIES:
            bot.is_active = False
        elif decision.intervention_type == InterventionType.RESUME_NEW_ENTRIES:
            bot.is_active = True
        elif decision.intervention_type == InterventionType.MODIFY_PARAMS:
            for key, value in (decision.params_modification or {}).items():
                _set_nested_attr(bot.cfg, key, value)
        elif decision.intervention_type == InterventionType.RAISE_BOUNDARY:
            for key, value in (decision.params_modification or {}).items():
                _set_nested_attr(bot.cfg, key, value)
        elif decision.intervention_type == InterventionType.PARTIAL_UNLOAD:
            self._apply_partial_unload(bot, price, decision.partial_unload_fraction or 0.0)
        elif decision.intervention_type == InterventionType.ACTIVATE_BOOSTER:
            self._apply_activate_booster(bot_id, bot, decision, price)

        after = _cfg_to_dict(bot.cfg)
        return InterventionEvent(
            bar_idx=snapshot.bar_idx,
            ts=snapshot.ts,
            bot_id=bot_id,
            intervention_type=decision.intervention_type,
            params_before=before,
            params_after=after,
            reason=decision.reason,
            market_snapshot=snapshot,
            pnl_usd_at_event=pnl_usd,
        )

    def _apply_partial_unload(self, bot: SupportsManagedBot, price: float, fraction: float) -> None:
        if fraction <= 0.0:
            return
        reduce_ratio = max(0.0, min(1.0, fraction))
        remaining_orders: list[Any] = []
        for order in list(bot.active_orders):
            close_qty = getattr(order, "qty", 0.0) * reduce_ratio
            keep_qty = getattr(order, "qty", 0.0) - close_qty
            if close_qty > 0.0:
                entry = float(getattr(order, "entry_price", price))
                side = getattr(bot.cfg, "side", None)
                contract = getattr(bot.cfg, "contract", None)
                pnl = 0.0
                if contract is not None and side is not None:
                    pnl = float(contract.unrealized_pnl(side, close_qty, entry, price))
                bot.realized_pnl += pnl
                closed = deepcopy(order)
                closed.qty = close_qty
                closed.closed_pnl = pnl
                closed.closed_at_price = price
                bot.closed_orders.append(closed)
            if keep_qty > 0.0:
                order.qty = keep_qty
                remaining_orders.append(order)
        bot.active_orders = remaining_orders

    def _apply_activate_booster(
        self,
        bot_id: str,
        bot: SupportsManagedBot,
        decision: InterventionDecision,
        price: float,
    ) -> None:
        if self.bot_factory is None:
            return
        booster_cfg = _cfg_to_dict(bot.cfg)
        booster_cfg["bot_id"] = f"{bot_id}_booster"
        booster_cfg["alias"] = f"{booster_cfg.get('alias', bot_id)}_booster"
        booster_cfg["order_size"] = float(booster_cfg.get("order_size", 0.0)) * float(
            (decision.booster_config or {}).get("qty_factor", 1.0)
        )
        booster_cfg["boundaries_upper"] = price * (
            1.0 + float((decision.booster_config or {}).get("border_top_offset_pct", 0.0)) / 100.0
        )
        booster = self.bot_factory(booster_cfg)
        self.bots[booster_cfg["bot_id"]] = booster
