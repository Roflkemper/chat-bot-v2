"""Multi-objective scorer для GinArea-конфигов из V5-sweep.

Учитывает 4 фактора:
1. Profit (USD за 3 мес)
2. Rebate от BitMEX maker-объёма (~$50-60 на каждый +$1M volume/мес)
3. Стоимость капитала (peak exposure × cost_of_capital × months)
4. Drawdown penalty (DD × dd_weight, потому что DD выгорает депо нелинейно)

Веса по умолчанию подобраны под оператора (риск-лимит 100k, депо $25-30k).
Можно тюнить через CLI: --rebate-per-m, --dd-weight, --capital-rate.

CLI: python scripts/score_configs.py [--top 10]
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

# BitMEX maker rebate: ~0.015% от объёма (orators feedback "+5M vol = +$1000-1500 rebate"
# → 1500 / 5_000_000 = 0.030% ≈ 0.025-0.030%, берём среднюю $250/M).
DEFAULT_REBATE_PER_VOL_MUSD = 250.0  # $ per $1M of volume per period

# Стоимость капитала: 2% годовых на залоченный депозит (alt: depo в стейблах
# приносит ~5%, но мы берём conservative 2% как opportunity cost).
DEFAULT_CAPITAL_RATE_PER_MONTH = 0.02 / 12  # 0.167%/мес

# DD penalty: каждый $1 просадки стоит $1 в score (нейтрально). Если хочешь
# консервативнее — поставь 1.5-2.0 (DD выгорает депо психологически).
DEFAULT_DD_WEIGHT = 1.0

DEFAULT_PERIOD_MONTHS = 3.0


@dataclass
class GinAreaConfig:
    name: str
    gs: float
    thresh: float
    td: float
    mult: float
    tp: str  # "off" or "X/X"
    max_size: int | str  # int (USD contracts) для LONG, str (BTC sizes) для SHORT
    profit_usd: float
    vol_musd: float        # USD volume in millions over the period
    peak_exposure_usd: float  # peak USD-экспозиция (07.02 LIBERATION для LONG)
    dd_usd: float = 0.0    # realized drawdown if known, else 0
    side: str = "long"
    notes: str = ""
    tier: str = ""         # "T1" / "T2" / "T3" tier label
    bitmex_id: str = ""


@dataclass
class ScoredConfig:
    cfg: GinAreaConfig
    profit: float
    rebate: float
    capital_cost: float
    dd_penalty: float
    total: float
    breakdown: dict[str, float] = field(default_factory=dict)


def score_config(
    cfg: GinAreaConfig,
    *,
    rebate_per_m: float = DEFAULT_REBATE_PER_VOL_MUSD,
    capital_rate_per_month: float = DEFAULT_CAPITAL_RATE_PER_MONTH,
    dd_weight: float = DEFAULT_DD_WEIGHT,
    period_months: float = DEFAULT_PERIOD_MONTHS,
    risk_limit_usd: float | None = 100_000.0,
) -> ScoredConfig:
    """Returns score components + total. Configs exceeding risk_limit get
    score=-inf автоматически (если limit задан).
    """
    if risk_limit_usd is not None and cfg.peak_exposure_usd > risk_limit_usd:
        return ScoredConfig(
            cfg=cfg, profit=cfg.profit_usd, rebate=0.0,
            capital_cost=0.0, dd_penalty=0.0,
            total=float("-inf"),
            breakdown={"risk_violation": cfg.peak_exposure_usd - risk_limit_usd},
        )
    rebate = cfg.vol_musd * rebate_per_m
    capital_cost = cfg.peak_exposure_usd * capital_rate_per_month * period_months
    dd_penalty = cfg.dd_usd * dd_weight
    total = cfg.profit_usd + rebate - capital_cost - dd_penalty
    return ScoredConfig(
        cfg=cfg,
        profit=cfg.profit_usd,
        rebate=rebate,
        capital_cost=capital_cost,
        dd_penalty=dd_penalty,
        total=total,
        breakdown={
            "profit": cfg.profit_usd,
            "rebate": rebate,
            "-capital_cost": -capital_cost,
            "-dd_penalty": -dd_penalty,
        },
    )


def rank_configs(
    configs: Iterable[GinAreaConfig],
    **kwargs,
) -> list[ScoredConfig]:
    """Сортировка по total убыванию. Configs с -inf (risk violation) идут в конец."""
    scored = [score_config(c, **kwargs) for c in configs]
    return sorted(scored, key=lambda s: s.total, reverse=True)


# ──────────────────────────────────────────────────────────────────────────
# Каталог конфигов из CASCADE_GINAREA_V5_SWEEP.md (пачки #14-#21)
# Все одна сторона LONG, период 3 мес BTCUSDT 1m
# ──────────────────────────────────────────────────────────────────────────

V5_CONFIGS_LONG: list[GinAreaConfig] = [
    GinAreaConfig(
        name="T2-MEGA (действующий лидер)",
        gs=0.04, thresh=1.5, td=0.9, mult=1.3, tp="off", max_size=300,
        profit_usd=22_672, vol_musd=4.08, peak_exposure_usd=80_000, dd_usd=2_400,
        notes="чемпион ≤100k риск-лимита",
    ),
    GinAreaConfig(
        name="T2-FREQ (volume-режим)",
        gs=0.04, thresh=0.3, td=0.7, mult=1.2, tp="off", max_size=300,
        profit_usd=21_478, vol_musd=5.61, peak_exposure_usd=80_000, dd_usd=2_400,
        notes="vol +37%, profit -5%",
    ),
    GinAreaConfig(
        name="T2-FREQ TD=0.8",
        gs=0.04, thresh=0.3, td=0.8, mult=1.2, tp="off", max_size=300,
        profit_usd=21_424, vol_musd=4.93, peak_exposure_usd=80_000, dd_usd=2_400,
    ),
    GinAreaConfig(
        name="T2-FREQ TD=0.55",
        gs=0.04, thresh=0.3, td=0.55, mult=1.2, tp="off", max_size=300,
        profit_usd=19_808, vol_musd=6.73, peak_exposure_usd=80_000, dd_usd=2_400,
    ),
    GinAreaConfig(
        name="T2-FREQ TD=0.4",
        gs=0.04, thresh=0.3, td=0.4, mult=1.2, tp="off", max_size=300,
        profit_usd=18_484, vol_musd=8.95, peak_exposure_usd=80_000, dd_usd=2_400,
    ),
    GinAreaConfig(
        name="T2 t=0.3 TD=1.0 mult=1.3",
        gs=0.04, thresh=0.3, td=1.0, mult=1.3, tp="off", max_size=300,
        profit_usd=22_074, vol_musd=3.97, peak_exposure_usd=80_000, dd_usd=2_400,
    ),
    GinAreaConfig(
        name="T2 t=0.3 TD=0.9 mult=1.3",
        gs=0.04, thresh=0.3, td=0.9, mult=1.3, tp="off", max_size=300,
        profit_usd=21_794, vol_musd=4.39, peak_exposure_usd=80_000, dd_usd=2_400,
    ),
    GinAreaConfig(
        name="T2 TD=0.21 TP=off",
        gs=0.04, thresh=0.3, td=0.21, mult=1.2, tp="off", max_size=300,
        profit_usd=13_867, vol_musd=14.75, peak_exposure_usd=65_000, dd_usd=2_400,
        notes="volume-heavy низкий-TD режим",
    ),
    GinAreaConfig(
        name="T2 TD=0.27 TP=off",
        gs=0.04, thresh=0.3, td=0.27, mult=1.2, tp="off", max_size=300,
        profit_usd=15_290, vol_musd=11.89, peak_exposure_usd=70_000, dd_usd=2_400,
    ),
    GinAreaConfig(
        name="T2 t=1.0 TD=0.4 TP=50",
        gs=0.04, thresh=1.0, td=0.4, mult=1.3, tp="50/50", max_size=300,
        profit_usd=18_530, vol_musd=8.98, peak_exposure_usd=80_000, dd_usd=2_400,
        notes="режим volume-farming (пачка #16)",
    ),
    GinAreaConfig(
        name="R1 gs=0.02 max=200",
        gs=0.02, thresh=0.3, td=0.25, mult=1.2, tp="10/10", max_size=200,
        profit_usd=19_692, vol_musd=16.84, peak_exposure_usd=100_000, dd_usd=4_000,
        notes="на границе риск-лимита",
    ),
    GinAreaConfig(
        name="R4 gs=0.04 t=0.3 TD=0.25",
        gs=0.04, thresh=0.3, td=0.25, mult=1.2, tp="50/50", max_size=300,
        profit_usd=15_020, vol_musd=12.99, peak_exposure_usd=65_000, dd_usd=2_400,
    ),
    # ── Вне лимита (для сравнения, score=-inf по default) ──
    GinAreaConfig(
        name="❌ gs=0.02 max=400 (вне лимита)",
        gs=0.02, thresh=0.3, td=0.25, mult=1.2, tp="off", max_size=400,
        profit_usd=39_236, vol_musd=33.5, peak_exposure_usd=210_000, dd_usd=5_500,
        notes="пик 210k — превышение",
    ),
    GinAreaConfig(
        name="❌ gs=0.03 max=300 (вне лимита)",
        gs=0.03, thresh=0.3, td=1.0, mult=1.3, tp="off", max_size=300,
        profit_usd=30_808, vol_musd=5.52, peak_exposure_usd=115_000, dd_usd=4_000,
    ),
    GinAreaConfig(
        name="❌ gs=0.02 max=300 (вне лимита)",
        gs=0.02, thresh=0.3, td=0.25, mult=1.2, tp="50/50", max_size=300,
        profit_usd=30_153, vol_musd=25.8, peak_exposure_usd=140_000, dd_usd=4_500,
    ),
]


# ──────────────────────────────────────────────────────────────────────────
# SHORT-конфиги из V5 (пачки #3-#8). Linear USDT_FUT BTCUSDT.
# size в формате "BTC_initial/BTC_max" (на платформе: 0.001/0.003).
# peak_exposure_usd оценка: max позиция в bag × текущая цена.
# По TG POS сообщениям: SHORT bot pos обычно -1.5 BTC × $80k ≈ $120k bag,
# но это уже усреднённый bag из 3-4 ботов вместе. На одного SHORT-бота
# реалистично $30-45k peak exposure.
# DD для SHORT: малая просадка (~$500-1000) — bag быстро возвращается,
# поскольку рынок 2024-2026 имел bull-bias.
# ──────────────────────────────────────────────────────────────────────────

V5_CONFIGS_SHORT: list[GinAreaConfig] = [
    # ── Tier-1 SHORT (gs=0.02, быстрый) ──────────────────────────────────
    GinAreaConfig(
        name="SH-T1 TP=10/10",
        side="short", tier="T1",
        gs=0.02, thresh=0.7, td=0.21, mult=1.3, tp="10/10", max_size="0.001/0.003",
        profit_usd=2_027, vol_musd=13.7, peak_exposure_usd=30_000, dd_usd=500,
        notes="самый чистый exit, unreal=0 стабильно",
    ),
    GinAreaConfig(
        name="SH-T1 TP=12/12",
        side="short", tier="T1",
        gs=0.02, thresh=0.7, td=0.21, mult=1.3, tp="12/12", max_size="0.001/0.003",
        profit_usd=1_956, vol_musd=13.87, peak_exposure_usd=35_000, dd_usd=1_000,
        notes="нестабильно: смешанные exit-ы",
    ),
    GinAreaConfig(
        name="SH-T1 TP=15/15 (текущий лидер T1)",
        side="short", tier="T1",
        gs=0.02, thresh=0.7, td=0.21, mult=1.3, tp="15/15", max_size="0.001/0.003",
        profit_usd=2_407, vol_musd=14.1, peak_exposure_usd=35_000, dd_usd=600,
        notes="максимум profit при чистом exit",
    ),
    GinAreaConfig(
        name="SH-T1 TP=25/25",
        side="short", tier="T1",
        gs=0.02, thresh=0.7, td=0.21, mult=1.3, tp="25/25", max_size="0.001/0.003",
        profit_usd=1_866, vol_musd=14.7, peak_exposure_usd=45_000, dd_usd=1_550,
        notes="unreal -1554 = замороз капитал",
    ),
    # ── Tier-2 SHORT (gs=0.03, средний) ──────────────────────────────────
    GinAreaConfig(
        name="SH-T2 TP=40/40",
        side="short", tier="T2",
        gs=0.03, thresh=1.5, td=0.35, mult=1.3, tp="40/40", max_size="0.002/0.004",
        profit_usd=1_713, vol_musd=3.67, peak_exposure_usd=30_000, dd_usd=400,
    ),
    GinAreaConfig(
        name="SH-T2 TP=60/60",
        side="short", tier="T2",
        gs=0.03, thresh=1.5, td=0.35, mult=1.3, tp="60/60", max_size="0.002/0.004",
        profit_usd=2_334, vol_musd=4.44, peak_exposure_usd=32_000, dd_usd=450,
    ),
    GinAreaConfig(
        name="SH-T2 TP=80/80",
        side="short", tier="T2",
        gs=0.03, thresh=1.5, td=0.35, mult=1.3, tp="80/80", max_size="0.002/0.004",
        profit_usd=2_930, vol_musd=4.78, peak_exposure_usd=35_000, dd_usd=500,
    ),
    GinAreaConfig(
        name="SH-T2 TP=99/99",
        side="short", tier="T2",
        gs=0.03, thresh=1.5, td=0.35, mult=1.3, tp="99/99", max_size="0.002/0.004",
        profit_usd=3_306, vol_musd=5.31, peak_exposure_usd=37_000, dd_usd=550,
    ),
    GinAreaConfig(
        name="SH-T2 TP=120/120",
        side="short", tier="T2",
        gs=0.03, thresh=1.5, td=0.35, mult=1.3, tp="120/120", max_size="0.002/0.004",
        profit_usd=3_840, vol_musd=5.69, peak_exposure_usd=40_000, dd_usd=600,
    ),
    GinAreaConfig(
        name="SH-T2 TP=140/140",
        side="short", tier="T2",
        gs=0.03, thresh=1.5, td=0.35, mult=1.3, tp="140/140", max_size="0.002/0.004",
        profit_usd=4_206, vol_musd=5.71, peak_exposure_usd=42_000, dd_usd=650,
    ),
    GinAreaConfig(
        name="SH-T2 TP=160/160",
        side="short", tier="T2",
        gs=0.03, thresh=1.5, td=0.35, mult=1.3, tp="160/160", max_size="0.002/0.004",
        profit_usd=4_335, vol_musd=5.79, peak_exposure_usd=44_000, dd_usd=700,
    ),
    GinAreaConfig(
        name="SH-T2 TP=180/180 (текущий лидер T2)",
        side="short", tier="T2",
        gs=0.03, thresh=1.5, td=0.35, mult=1.3, tp="180/180", max_size="0.002/0.004",
        profit_usd=4_611, vol_musd=5.98, peak_exposure_usd=45_000, dd_usd=750,
        notes="плато перед обвалом TP=220",
    ),
    # ── Tier-3 SHORT (gs=0.05, редкий) ───────────────────────────────────
    GinAreaConfig(
        name="SH-T3 TP=60/60 TD=0.45",
        side="short", tier="T3",
        gs=0.05, thresh=2.0, td=0.45, mult=1.2, tp="60/60", max_size="0.002/0.005",
        profit_usd=1_081, vol_musd=1.33, peak_exposure_usd=22_000, dd_usd=300,
    ),
    GinAreaConfig(
        name="SH-T3 TP=80/80 TD=0.45",
        side="short", tier="T3",
        gs=0.05, thresh=2.0, td=0.45, mult=1.2, tp="80/80", max_size="0.002/0.005",
        profit_usd=1_362, vol_musd=1.62, peak_exposure_usd=23_000, dd_usd=350,
    ),
    GinAreaConfig(
        name="SH-T3 TP=99/99 TD=0.45",
        side="short", tier="T3",
        gs=0.05, thresh=2.0, td=0.45, mult=1.2, tp="99/99", max_size="0.002/0.005",
        profit_usd=1_662, vol_musd=1.77, peak_exposure_usd=24_000, dd_usd=400,
    ),
    GinAreaConfig(
        name="SH-T3 TP=140/140 TD=0.6",
        side="short", tier="T3",
        gs=0.05, thresh=2.0, td=0.6, mult=1.2, tp="140/140", max_size="0.002/0.005",
        profit_usd=2_242, vol_musd=1.57, peak_exposure_usd=25_000, dd_usd=450,
    ),
    GinAreaConfig(
        name="SH-T3 TP=180/180 TD=0.6",
        side="short", tier="T3",
        gs=0.05, thresh=2.0, td=0.6, mult=1.2, tp="180/180", max_size="0.002/0.005",
        profit_usd=2_692, vol_musd=1.70, peak_exposure_usd=27_000, dd_usd=500,
    ),
    GinAreaConfig(
        name="SH-T3 TP=240/240 TD=0.6",
        side="short", tier="T3",
        gs=0.05, thresh=2.0, td=0.6, mult=1.2, tp="240/240", max_size="0.002/0.005",
        profit_usd=3_115, vol_musd=2.06, peak_exposure_usd=29_000, dd_usd=600,
    ),
    GinAreaConfig(
        name="SH-T3 TP=270/270 TD=0.6 (текущий лидер T3)",
        side="short", tier="T3",
        gs=0.05, thresh=2.0, td=0.6, mult=1.2, tp="270/270", max_size="0.002/0.005",
        profit_usd=3_248, vol_musd=2.17, peak_exposure_usd=30_000, dd_usd=650,
        notes="дисперсия 0.06% — очень устойчиво",
    ),
]


def all_long_configs() -> list[GinAreaConfig]:
    return V5_CONFIGS_LONG


def all_short_configs() -> list[GinAreaConfig]:
    return V5_CONFIGS_SHORT


def format_ranking(
    ranked: list[ScoredConfig],
    *,
    top: int = 10,
    period_months: float = DEFAULT_PERIOD_MONTHS,
) -> str:
    lines = [
        "🎯 GinArea-конфиги: multi-objective ranking",
        f"(period {period_months:.0f}мес, score = profit + rebate − capital_cost − dd_penalty)",
        "",
        f"{'#':<3} {'config':<35} {'total':>7} {'profit':>7} {'rebate':>6} {'cap':>5} {'DD':>5}",
        "-" * 75,
    ]
    in_limit = [s for s in ranked if s.total != float("-inf")]
    out_limit = [s for s in ranked if s.total == float("-inf")]
    for i, s in enumerate(in_limit[:top], 1):
        lines.append(
            f"{i:<3} {s.cfg.name[:34]:<35} "
            f"{s.total:>+7.0f} {s.profit:>+7.0f} {s.rebate:>+6.0f} "
            f"{-s.capital_cost:>+5.0f} {-s.dd_penalty:>+5.0f}"
        )
    if out_limit:
        lines += ["", "── Вне риск-лимита (показано для сравнения) ──"]
        for s in out_limit[:5]:
            lines.append(
                f"--- {s.cfg.name[:34]:<35} "
                f"  ---  {s.profit:>+7.0f}  ---    ---   --- "
                f"  peak={s.cfg.peak_exposure_usd / 1000:.0f}k"
            )
    return "\n".join(lines)
