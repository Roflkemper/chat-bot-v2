from __future__ import annotations

from collections import namedtuple
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from services.managed_grid_sim.models import MarketSnapshot, RegimeLabel, TrendType


OHLCBar = namedtuple("OHLCBar", ["ts", "open", "high", "low", "close", "volume"])


class FakeSide:
    def __init__(self, name: str) -> None:
        self.name = name.upper()
        self.value = name.lower()


class FakeContractType:
    def __init__(self, value: str) -> None:
        self.value = value


class FakeContract:
    def __init__(self, contract_type: str) -> None:
        self.contract_type = FakeContractType(contract_type)

    def notional_usd(self, qty: float, price: float) -> float:
        if self.contract_type.value == "inverse":
            return qty
        return qty * price

    def unrealized_pnl(self, side: Any, qty: float, entry: float, current: float) -> float:
        is_short = getattr(side, "name", "").upper() == "SHORT"
        if self.contract_type.value == "inverse":
            if is_short:
                return qty * (1.0 / current - 1.0 / entry) * current
            return qty * (1.0 / entry - 1.0 / current) * current
        if is_short:
            return qty * (entry - current)
        return qty * (current - entry)


@dataclass
class FakeCfg:
    bot_id: str
    alias: str
    side: Any
    contract: Any
    order_size: float
    order_count: int
    grid_step_pct: float
    target_profit_pct: float
    min_stop_pct: float
    max_stop_pct: float
    instop_pct: float
    boundaries_lower: float
    boundaries_upper: float
    indicator_period: int
    indicator_threshold_pct: float
    dsblin: bool = False
    leverage: int = 100
    cap_pos_btc: float | None = None


@dataclass
class FakeOrder:
    qty: float
    entry_price: float
    opened_bar_idx: int = 0
    closed_pnl: float = 0.0
    closed_at_price: float = 0.0


class FakeBot:
    def __init__(self, cfg: FakeCfg) -> None:
        self.cfg = cfg
        self.is_active = not cfg.dsblin
        self.realized_pnl = 0.0
        self.in_qty_notional = 0.0
        self.out_qty_notional = 0.0
        self.active_orders: list[FakeOrder] = []
        self.closed_orders: list[FakeOrder] = []

    def step(self, bar: Any, bar_idx: int) -> None:
        if self.is_active and not self.active_orders:
            self.active_orders.append(FakeOrder(qty=float(self.cfg.order_size), entry_price=float(bar.close), opened_bar_idx=bar_idx))
            self.in_qty_notional += self.cfg.contract.notional_usd(float(self.cfg.order_size), float(bar.close))

    def position_size(self) -> float:
        return sum(order.qty for order in self.active_orders)

    def avg_entry(self) -> float:
        if not self.active_orders:
            return 0.0
        total = sum(order.qty for order in self.active_orders)
        return sum(order.entry_price * order.qty for order in self.active_orders) / total

    def unrealized_pnl(self, price: float) -> float:
        return sum(self.cfg.contract.unrealized_pnl(self.cfg.side, order.qty, order.entry_price, price) for order in self.active_orders)


def fake_engine_loader() -> tuple[Any, Any, Any, Any, Any]:
    class Side:
        SHORT = FakeSide("short")
        LONG = FakeSide("long")

    contracts = {"linear": FakeContract("linear"), "inverse": FakeContract("inverse")}
    return FakeCfg, FakeBot, OHLCBar, Side, contracts


@pytest.fixture
def sample_bars() -> list[Any]:
    start = datetime(2026, 4, 1, tzinfo=timezone.utc)
    bars = []
    price = 100.0
    for idx in range(80):
        close = price + 0.5
        bars.append(
            OHLCBar(
                ts=(start + timedelta(minutes=5 * idx)).isoformat().replace("+00:00", "Z"),
                open=price,
                high=close + 0.4,
                low=price - 0.3,
                close=close,
                volume=100.0 + idx,
            )
        )
        price = close
    return bars


@pytest.fixture
def base_bot_config() -> dict[str, Any]:
    return {
        "bot_id": "short_main",
        "alias": "short_main",
        "side": "short",
        "contract_type": "linear",
        "order_size": 1.0,
        "order_count": 10,
        "grid_step_pct": 0.03,
        "target_profit_pct": 0.21,
        "min_stop_pct": 0.01,
        "max_stop_pct": 0.04,
        "instop_pct": 0.01,
        "boundaries_lower": 0.0,
        "boundaries_upper": 999999.0,
        "indicator_period": 30,
        "indicator_threshold_pct": 0.3,
    }


@pytest.fixture
def sample_snapshot() -> MarketSnapshot:
    return MarketSnapshot(
        bar_idx=10,
        ts=datetime(2026, 4, 1, tzinfo=timezone.utc),
        ohlcv=(100.0, 102.0, 99.0, 101.0, 500.0),
        regime=RegimeLabel.TREND_UP,
        trend_type=TrendType.VOLATILE_TRENDING,
        delta_price_5m_pct=0.01,
        delta_price_1h_pct=0.03,
        delta_price_4h_pct=0.05,
        atr_normalized=0.003,
        pdh=101.2,
        pdl=98.5,
        volume_ratio_to_avg=3.5,
        bars_since_last_pivot=5,
    )


@pytest.fixture
def sweep_fixture_path() -> Path:
    return Path("C:/bot7/tests/services/managed_grid_sim/fixtures/synthetic_ohlcv_case.json")
