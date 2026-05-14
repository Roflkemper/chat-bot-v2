"""Static loader for OPPORTUNITY_MAP_v1 play specifications."""
from __future__ import annotations

from dataclasses import dataclass, field

HARD_BANNED: frozenset[str] = frozenset({"P-5", "P-8", "P-10"})


@dataclass
class PlaySpec:
    play_id: str
    name: str
    trigger_description: str
    expected_pnl: dict[str, float]  # size_mode -> usd
    win_rate: float
    dd_pct: float
    params: dict = field(default_factory=dict)
    hard_banned: bool = False


_MAP: dict[str, PlaySpec] = {
    "P-1": PlaySpec(
        play_id="P-1",
        name="Поднять границу +0.3%",
        trigger_description="Цена выше верхней границы шорта ≥15 мин",
        expected_pnl={"conservative": 0.0, "normal": 0.0, "aggressive": 0.0},
        win_rate=0.13,
        dd_pct=0.0,
        params={"offset_pct": 0.3},
    ),
    "P-2": PlaySpec(
        play_id="P-2",
        name="Стак-шорт на остановке",
        trigger_description="Δ1h 2-3% + признаки потери моментума",
        expected_pnl={"conservative": 10.0, "normal": 26.0, "aggressive": 38.0},
        win_rate=0.59,
        dd_pct=1.5,
        params={},
    ),
    "P-3": PlaySpec(
        play_id="P-3",
        name="Стак-лонг (low_confidence)",
        trigger_description="Liq-каскад лонг + разворот (n=1, экспериментально)",
        expected_pnl={"conservative": 0.0, "normal": 0.0, "aggressive": 0.0},
        win_rate=0.0,
        dd_pct=0.0,
        params={},
    ),
    "P-4": PlaySpec(
        play_id="P-4",
        name="Стоп шорт-ботов",
        trigger_description="3+ часа подряд вверх без отката + шорты в DD",
        expected_pnl={"conservative": 0.0, "normal": 0.0, "aggressive": 0.0},
        win_rate=0.23,
        dd_pct=0.0,
        params={},
    ),
    "P-5": PlaySpec(
        play_id="P-5",
        name="Частичный выход (HARD BAN)",
        trigger_description="HARD BAN — никогда не предлагать",
        expected_pnl={"conservative": -26.0, "normal": -26.0, "aggressive": -26.0},
        win_rate=0.42,
        dd_pct=1.4,
        params={},
        hard_banned=True,
    ),
    "P-6": PlaySpec(
        play_id="P-6",
        name="Стак-шорт + поднять границу",
        trigger_description="Δ1h > 3% (rally_critical)",
        expected_pnl={"conservative": 28.0, "normal": 84.0, "aggressive": 134.0},
        win_rate=0.69,
        dd_pct=1.4,
        params={"offset_pct": 1.0},
    ),
    "P-7": PlaySpec(
        play_id="P-7",
        name="Стак-лонг после дампа",
        trigger_description="Δ1h ≤ -2% + разворот подтверждён",
        expected_pnl={"conservative": 7.0, "normal": 15.0, "aggressive": 26.0},
        win_rate=0.67,
        dd_pct=2.1,
        params={},
    ),
    "P-8": PlaySpec(
        play_id="P-8",
        name="Принудительное закрытие + рестарт (HARD BAN)",
        trigger_description="HARD BAN — никогда не предлагать",
        expected_pnl={"conservative": -192.0, "normal": -192.0, "aggressive": -192.0},
        win_rate=0.25,
        dd_pct=5.9,
        params={},
        hard_banned=True,
    ),
    "P-10": PlaySpec(
        play_id="P-10",
        name="Ребаланс (HARD BAN)",
        trigger_description="HARD BAN — никогда не предлагать",
        expected_pnl={"conservative": -50.0, "normal": -50.0, "aggressive": -50.0},
        win_rate=0.30,
        dd_pct=3.0,
        params={},
        hard_banned=True,
    ),
    "P-12": PlaySpec(
        play_id="P-12",
        name="Adaptive tighten",
        trigger_description="Бот в просадке 4h+, unrealized < -$200",
        expected_pnl={"conservative": 0.0, "normal": 0.0, "aggressive": 0.0},
        win_rate=0.09,
        dd_pct=0.0,
        params={"gs_factor": 0.85, "target_factor": 0.8},
    ),
}


def get_play(play_id: str) -> PlaySpec | None:
    return _MAP.get(play_id)


def get_all_plays() -> dict[str, PlaySpec]:
    return dict(_MAP)


def is_hard_banned(play_id: str) -> bool:
    return play_id in HARD_BANNED
