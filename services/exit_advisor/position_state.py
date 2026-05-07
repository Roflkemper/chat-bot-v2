"""Real-time position state evaluator for exit advisory.

Reads ginarea_live/snapshots.csv, aggregates per-bot and portfolio-level
metrics, classifies the scenario, and returns a PositionStateSnapshot.

Scenario classes (from COUNTERTREND_PLAYBOOK §8):
  monitoring          — DD < -3%: nothing critical yet
  early_intervention  — DD > -3%, duration < 4h
  cycle_death         — DD > -3%, duration >= 4h  (playbook v1 trigger)
  moderate            — DD > -7%, duration >= 4h
  severe              — DD > -12%, any duration
  critical            — DD > -20%, any duration
  urgent_protection   — distance_to_liq < 15% (overrides all)
"""
from __future__ import annotations

import csv
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[2]
_SNAPSHOTS_CSV = _ROOT / "ginarea_live" / "snapshots.csv"

# Thresholds (% of deposit)
_DD_EARLY = -3.0
_DD_MODERATE = -7.0
_DD_SEVERE = -12.0
_DD_CRITICAL = -20.0
_EARLY_DURATION_H = 4.0
_LIQ_URGENT_PCT = 5.0  # 2026-05-07: was 15 — too liberal. 14% distance to liq на inverse означает 14% движение цены ВВЕРХ — это далеко не URGENT. Реальный риск только при <5%.


class ScenarioClass(str, Enum):
    MONITORING = "monitoring"
    EARLY_INTERVENTION = "early_intervention"
    CYCLE_DEATH = "cycle_death"
    MODERATE = "moderate"
    SEVERE = "severe"
    CRITICAL = "critical"
    URGENT_PROTECTION = "urgent_protection"


@dataclass
class BotState:
    bot_id: str
    alias: str
    status: int                       # 2 = active
    position_btc: float               # negative = short
    unrealized_usd: float             # current_profit
    realized_24h_usd: float           # profit (24h realized)
    avg_entry_price: float
    liquidation_price: float
    balance_usd: float
    distance_to_liq_pct: float        # abs % from price to liq

    # derived
    unrealized_pct_deposit: float = 0.0   # unrealized / balance * 100
    duration_in_dd_h: float = 0.0         # hours continuously below DD_EARLY threshold


@dataclass
class PortfolioSide:
    side: str                         # "SHORT" | "LONG"
    bot_count: int = 0
    total_unrealized_usd: float = 0.0
    total_position_btc: float = 0.0
    worst_bot: Optional[BotState] = None


@dataclass
class PositionStateSnapshot:
    captured_at: datetime
    current_price: float

    bots: list[BotState] = field(default_factory=list)
    short_side: PortfolioSide = field(default_factory=lambda: PortfolioSide("SHORT"))
    long_side: PortfolioSide = field(default_factory=lambda: PortfolioSide("LONG"))

    total_unrealized_usd: float = 0.0
    free_margin_usd: float = 0.0
    free_margin_pct: float = 100.0
    total_balance_usd: float = 0.0

    scenario_class: ScenarioClass = ScenarioClass.MONITORING
    scenario_notes: list[str] = field(default_factory=list)

    # convenience flags
    has_active_position: bool = False
    worst_bot: Optional[BotState] = None
    worst_dd_pct: float = 0.0
    min_distance_to_liq_pct: float = 100.0


def _safe_float(v: str, default: float = 0.0) -> float:
    try:
        return float(v) if v not in ("", "None", "nan") else default
    except (ValueError, TypeError):
        return default


def _normalize_bot_id(bid: str) -> str:
    """Strip legacy '.0' suffix from bot_id (TZ-Y dedup, 2026-05-07).

    snapshots.csv содержит ОДНОГО бота под двумя ключами:
      '5196832375'    (новый, актуальный)
      '5196832375.0'  (legacy, устаревшие данные)

    Без normalize они попадали в latest{} как разные ботa → SHORT total
    дублировался / показывал старые цены. Исправлено в dashboard
    (commit 5e9864f), теперь и здесь.
    """
    bid = (bid or "").strip()
    if bid.endswith(".0"):
        bid = bid[:-2]
    return bid


def _read_latest_snapshot(csv_path: Path) -> list[dict]:
    """Read last row per bot_id from snapshots CSV.

    Uses normalized bot_id so '5196832375' and '5196832375.0' merge into one
    bot. Within duplicates the row with **latest ts_utc** wins.
    """
    if not csv_path.exists():
        return []
    try:
        with csv_path.open(encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            latest: dict[str, dict] = {}
            for row in reader:
                bid = _normalize_bot_id(row.get("bot_id", ""))
                if not bid:
                    continue
                # Сохраняем normalized bid в самой записи для downstream
                row["bot_id"] = bid
                # Берём более свежий по ts_utc
                prev = latest.get(bid)
                if prev is None:
                    latest[bid] = row
                else:
                    if (row.get("ts_utc") or "") > (prev.get("ts_utc") or ""):
                        latest[bid] = row
        return list(latest.values())
    except Exception:
        logger.exception("exit_advisor.position_state: failed to read snapshots")
        return []


def _classify_scenario(
    bots: list[BotState],
    total_balance_usd: float,
) -> tuple[ScenarioClass, list[str]]:
    """Classify portfolio into scenario class based on aggregated metrics."""
    if not bots:
        return ScenarioClass.MONITORING, ["no_active_bots"]

    active = [b for b in bots if b.status == 2 and abs(b.position_btc) > 0]
    if not active:
        return ScenarioClass.MONITORING, ["no_active_positions"]

    notes: list[str] = []

    # Worst position metrics
    worst_dd_pct = min(b.unrealized_pct_deposit for b in active)
    min_liq_dist = min(b.distance_to_liq_pct for b in active)
    max_dur_h = max(b.duration_in_dd_h for b in active)

    notes.append(f"worst_dd={worst_dd_pct:.1f}%")
    notes.append(f"min_liq_dist={min_liq_dist:.1f}%")
    notes.append(f"max_dur_in_dd={max_dur_h:.1f}h")

    # Override: urgent liq proximity
    if min_liq_dist < _LIQ_URGENT_PCT:
        notes.append(f"liq_danger:{min_liq_dist:.1f}%<{_LIQ_URGENT_PCT}%")
        return ScenarioClass.URGENT_PROTECTION, notes

    # Severity-based classification (worst DD)
    if worst_dd_pct > _DD_EARLY:
        return ScenarioClass.MONITORING, notes

    if worst_dd_pct <= _DD_CRITICAL:
        notes.append("severity=critical")
        return ScenarioClass.CRITICAL, notes

    if worst_dd_pct <= _DD_SEVERE:
        notes.append("severity=severe")
        return ScenarioClass.SEVERE, notes

    if worst_dd_pct <= _DD_MODERATE:
        if max_dur_h >= _EARLY_DURATION_H:
            notes.append("severity=moderate_prolonged")
            return ScenarioClass.MODERATE, notes
        notes.append("severity=moderate_early")
        return ScenarioClass.EARLY_INTERVENTION, notes

    # DD between -3% and -7%
    if max_dur_h >= _EARLY_DURATION_H:
        notes.append("severity=cycle_death")
        return ScenarioClass.CYCLE_DEATH, notes
    notes.append("severity=early")
    return ScenarioClass.EARLY_INTERVENTION, notes


def build_position_state(
    csv_path: Path = _SNAPSHOTS_CSV,
    current_price: float = 0.0,
    dd_onset_cache: dict[str, datetime] | None = None,
) -> PositionStateSnapshot:
    """Build PositionStateSnapshot from latest ginarea snapshots.

    dd_onset_cache: mutable dict {bot_id: first_ts_entered_DD} maintained
    by caller across ticks for duration_in_dd_h computation.
    """
    rows = _read_latest_snapshot(csv_path)
    now = datetime.now(timezone.utc)

    if dd_onset_cache is None:
        dd_onset_cache = {}

    bots: list[BotState] = []

    # 2026-05-07: snapshots.csv содержит multiple exchange accounts
    # (BitMEX inverse + Binance USDT-M + ...). Каждый bot_id имеет свой
    # последний row, но balance этих rows фиксируется в разное время.
    # Раньше код брал первый non-zero balance — давал случайное значение.
    # Сейчас: берём balance только из rows с timestamp == latest_ts (это
    # обеспечивает что balance актуальные именно на текущий момент).
    latest_ts = max((r.get("ts_utc", "") for r in rows), default="")
    unique_balances: set[float] = set()

    for row in rows:
        bot_id = row.get("bot_id", "").strip()
        alias = row.get("alias", "").strip() or row.get("bot_name", "").strip()
        status = int(_safe_float(row.get("status", "0")))
        position_btc = _safe_float(row.get("position", "0"))
        unrealized_usd = _safe_float(row.get("current_profit", "0"))
        realized_24h = _safe_float(row.get("profit", "0"))
        avg_entry = _safe_float(row.get("average_price", "0"))
        liq_price = _safe_float(row.get("liquidation_price", "0"))
        balance = _safe_float(row.get("balance", "0"))
        row_ts = row.get("ts_utc", "")

        # Балансы только из rows с актуальным ts (свежий snapshot, не из
        # архивных rows для других bot_id). Накапливаем uniq значения
        # (округляем чтобы свернуть мелкие флуктуации в одну группу).
        if balance > 0 and row_ts == latest_ts:
            unique_balances.add(round(balance, 0))  # round to dollar — exchange accounts отличаются на сотни

        # Distance to liq
        if liq_price > 0 and current_price > 0:
            dist_pct = abs(current_price - liq_price) / current_price * 100
        else:
            dist_pct = 100.0

        # Unrealized as % of deposit
        unrealized_pct = (unrealized_usd / balance * 100) if balance > 0 else 0.0

        # Duration in DD
        is_in_dd = unrealized_pct <= _DD_EARLY
        if is_in_dd:
            if bot_id not in dd_onset_cache:
                dd_onset_cache[bot_id] = now
            dur_h = (now - dd_onset_cache[bot_id]).total_seconds() / 3600
        else:
            dd_onset_cache.pop(bot_id, None)
            dur_h = 0.0

        bot = BotState(
            bot_id=bot_id,
            alias=alias,
            status=status,
            position_btc=position_btc,
            unrealized_usd=unrealized_usd,
            realized_24h_usd=realized_24h,
            avg_entry_price=avg_entry,
            liquidation_price=liq_price,
            balance_usd=balance,
            distance_to_liq_pct=dist_pct,
            unrealized_pct_deposit=unrealized_pct,
            duration_in_dd_h=dur_h,
        )
        bots.append(bot)

    # Portfolio aggregation
    short_side = PortfolioSide("SHORT")
    long_side = PortfolioSide("LONG")

    for b in bots:
        if b.status != 2 or b.position_btc == 0:
            continue
        side = short_side if b.position_btc < 0 else long_side
        side.bot_count += 1
        side.total_unrealized_usd += b.unrealized_usd
        side.total_position_btc += b.position_btc
        if side.worst_bot is None or b.unrealized_pct_deposit < side.worst_bot.unrealized_pct_deposit:
            side.worst_bot = b

    total_unrealized = sum(b.unrealized_usd for b in bots if b.status == 2)

    # Sum unique balance values per exchange account (BitMEX + Binance + ...)
    total_balance = sum(unique_balances) if unique_balances else 0.0
    free_margin_pct = ((total_balance + total_unrealized) / total_balance * 100) if total_balance > 0 else 100.0

    scenario, notes = _classify_scenario(bots, total_balance)

    active = [b for b in bots if b.status == 2 and b.position_btc != 0]
    worst = min(active, key=lambda b: b.unrealized_pct_deposit) if active else None
    worst_dd = worst.unrealized_pct_deposit if worst else 0.0
    min_liq = min((b.distance_to_liq_pct for b in active), default=100.0)

    return PositionStateSnapshot(
        captured_at=now,
        current_price=current_price,
        bots=bots,
        short_side=short_side,
        long_side=long_side,
        total_unrealized_usd=total_unrealized,
        free_margin_usd=total_balance + total_unrealized,
        free_margin_pct=free_margin_pct,
        total_balance_usd=total_balance,
        scenario_class=scenario,
        scenario_notes=notes,
        has_active_position=bool(active),
        worst_bot=worst,
        worst_dd_pct=worst_dd,
        min_distance_to_liq_pct=min_liq,
    )
