"""Portfolio state reader from snapshots_v2.csv with TTL cache."""
from __future__ import annotations

import csv
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SNAPSHOTS_PATH = ROOT / "ginarea_tracker" / "ginarea_live" / "snapshots_v2.csv"
_CACHE_TTL_S: float = 10.0

# Tolerance for grouping bots into the same balance pool (cross-margin shared balance).
_BALANCE_GROUP_TOL = 5.0  # USDT


@dataclass
class BotState:
    bot_id: str
    name: str
    alias: str
    status: str
    position: str  # "LONG" | "SHORT" | "" | "NONE"
    profit: float
    current_profit: float
    average_price: float
    balance: float
    liquidation_price: float


@dataclass
class PortfolioState:
    ts_utc: str
    bots: list[BotState] = field(default_factory=list)

    # Primary cross-margin pool wallet balance (max balance among active bots).
    primary_balance: float = 0.0

    # depo_available = primary_balance + unrealized PnL of primary pool bots.
    # This is the equity (funds available for new positions).
    depo_available: float = 0.0

    # depo_total = operator-configured total portfolio value (from GinArea UI).
    # If not configured (0) → equal to depo_available.
    depo_total: float = 0.0

    # Legacy alias kept for backward compat with existing callers.
    @property
    def balance(self) -> float:
        return self.primary_balance

    @property
    def total_unrealized_pnl(self) -> float:
        return sum(b.current_profit for b in self.bots)

    @property
    def has_open_dd(self) -> bool:
        """True only if any active position has unrealized loss > DD threshold (filters noise)."""
        try:
            from config import ADVISOR_DD_THRESHOLD_USD
            threshold = float(ADVISOR_DD_THRESHOLD_USD)
        except Exception:
            threshold = 10.0
        return any(
            b.current_profit < -threshold
            for b in self.bots
            if b.position not in ("", "NONE")
        )

    @property
    def dd_pct(self) -> float:
        """Unrealized losses as % of depo_available."""
        if self.depo_available <= 0:
            return 0.0
        losses = sum(b.current_profit for b in self.bots if b.current_profit < 0)
        return abs(losses) / self.depo_available * 100

    @property
    def free_margin_pct(self) -> float:
        """Available margin as % of total portfolio: depo_available / depo_total × 100."""
        if self.depo_total <= 0:
            return 100.0
        return min(100.0, max(0.0, self.depo_available / self.depo_total * 100))

    def min_liq_distance_pct(self, current_price: float) -> float:
        """Minimum distance from current price to any active liquidation price (%)."""
        if current_price <= 0:
            return 100.0
        distances = [
            abs(current_price - b.liquidation_price) / current_price * 100
            for b in self.bots
            if b.liquidation_price > 0 and b.position not in ("", "NONE")
        ]
        return min(distances) if distances else 100.0


_cache: tuple[float, PortfolioState] | None = None


def read_portfolio_state(path: Path = SNAPSHOTS_PATH) -> PortfolioState:
    global _cache
    now = time.monotonic()
    if _cache is not None and (now - _cache[0]) < _CACHE_TTL_S:
        return _cache[1]
    state = _load(path)
    _cache = (now, state)
    return state


def _load(path: Path) -> PortfolioState:
    if not path.exists():
        return PortfolioState(ts_utc="")

    latest: dict[str, dict] = {}
    try:
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                bot_id = row.get("bot_id", "")
                if bot_id:
                    latest[bot_id] = row
    except OSError:
        return PortfolioState(ts_utc="")

    if not latest:
        return PortfolioState(ts_utc="")

    bots: list[BotState] = []
    ts_utc = ""

    for row in latest.values():
        try:
            b = BotState(
                bot_id=row.get("bot_id", ""),
                name=row.get("bot_name", ""),
                alias=row.get("alias", ""),
                status=row.get("status", ""),
                position=row.get("position", ""),
                profit=float(row.get("profit") or 0),
                current_profit=float(row.get("current_profit") or 0),
                average_price=float(row.get("average_price") or 0),
                balance=float(row.get("balance") or 0),
                liquidation_price=float(row.get("liquidation_price") or 0),
            )
            bots.append(b)
            row_ts = row.get("ts_utc", "")
            if row_ts > ts_utc:
                ts_utc = row_ts
        except (ValueError, KeyError):
            continue

    # Primary balance = max balance across all bots (cross-margin shared pool).
    primary_balance = max((b.balance for b in bots), default=0.0)

    # Primary pool = bots whose balance is within tolerance of primary_balance.
    # These share a cross-margin USDT pool; their cur_profit adds to pool equity.
    primary_pool_cur_profit = sum(
        b.current_profit
        for b in bots
        if abs(b.balance - primary_balance) <= _BALANCE_GROUP_TOL
    )
    depo_available = primary_balance + primary_pool_cur_profit

    # depo_total: use operator config if set, otherwise fall back to depo_available.
    try:
        from config import ADVISOR_DEPO_TOTAL
        cfg_total = float(ADVISOR_DEPO_TOTAL)
    except Exception:
        cfg_total = 0.0
    depo_total = cfg_total if cfg_total > 0 else depo_available

    return PortfolioState(
        ts_utc=ts_utc,
        bots=bots,
        primary_balance=primary_balance,
        depo_available=round(depo_available, 2),
        depo_total=round(depo_total, 2),
    )
