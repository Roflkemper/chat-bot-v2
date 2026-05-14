"""Real walk-forward T2-MEGA на 1m BTCUSDT 2y данных через GridBotSim.

GridBotSim — calibrated approximation движка GinArea (instop Semant A +
indicator gate, raw 4-tick resolution). Не учитывает `mult` (всегда
order_size=100), поэтому даёт нижнюю оценку profit. Это OK для проверки
overfit-к-LIBERATION гипотезы: смотрим, стабильно ли T2-MEGA положительный
на других 3-мес окнах.

Конфиг T2-MEGA (frozen):
  side=LONG (COIN-M XBTUSD inverse)
  order_size=100, grid_step_pct=0.04, target_pct=0.9
  instop_pct=0.018, indicator_period=30, indicator_threshold_pct=1.5
  max_orders=5000, no out_stop_group

CLI: python scripts/walk_forward_t2mega.py [--windows N]
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from services.calibration.sim import load_ohlcv_bars, run_sim

ROOT = Path(__file__).resolve().parents[2]
BTC_1M_PATH = ROOT / "backtests" / "frozen" / "BTCUSDT_1m_2y.csv"

T2_MEGA_PARAMS = dict(
    side="LONG",
    order_size=100.0,
    grid_step_pct=0.04,
    target_pct=0.9,
    max_orders=5000,
    instop_pct=0.018,
    indicator_period=30,
    indicator_threshold_pct=1.5,
)

# Эталон T2-MEGA на платформе GinArea (CASCADE_GINAREA_V5_SWEEP.md, пачка #15):
#   period 2026-02-01..04-29, profit = +$22 672, vol = $4.08M
# Sim даёт **относительные** оценки. Абсолютные числа ниже платформы в ~28×
# из-за неучтённых факторов: mult=1.3 (×1.3), накопительный bag size при mult
# на каждой ступеньке (×8-10) и др. движковые тонкости.
# Используем sim для **relative walk-forward**: окно vs окно (знак и порядок).
REF_PROFIT_PLATFORM = 22_672.0
REF_VOL_PLATFORM = 4_080_000.0

# Эмпирический множитель для конверсии sim → платформа (откалиброван на
# эталонном окне 2026-02-01..04-29). Применяется в `realized_pnl_usd` чтобы
# таблица показывала ожидание в платформенных $.
SIM_TO_PLATFORM_FACTOR = 28.0


@dataclass
class WindowResult:
    label: str
    start: str
    end: str
    bars: int
    realized_pnl_btc: float          # COIN-M LONG returns BTC
    realized_pnl_usd: float          # converted via avg close-of-window price
    unrealized_pnl_btc: float
    trading_volume_usd: float
    num_fills: int
    pct_of_ref_profit: float         # vs $22 672 platform reference


def _iso_to_ms(iso: str) -> int:
    return int(datetime.fromisoformat(iso).replace(tzinfo=timezone.utc).timestamp() * 1000)


def _last_close_in_window(start_iso: str, end_iso: str) -> float:
    """Read last close price in window (for BTC→USD conversion of LONG PnL)."""
    start_ms = _iso_to_ms(start_iso)
    end_ms = _iso_to_ms(end_iso)
    last_close = 0.0
    with BTC_1M_PATH.open("r", encoding="utf-8") as f:
        next(f)  # header
        for line in f:
            parts = line.split(",")
            ts_ms = int(float(parts[0]))
            if ts_ms < start_ms:
                continue
            if ts_ms > end_ms:
                break
            last_close = float(parts[4])
    return last_close


def run_window(label: str, start_iso: str, end_iso: str) -> WindowResult:
    bars = load_ohlcv_bars(BTC_1M_PATH, start_iso, end_iso)
    if not bars:
        return WindowResult(
            label=label, start=start_iso, end=end_iso, bars=0,
            realized_pnl_btc=0.0, realized_pnl_usd=0.0,
            unrealized_pnl_btc=0.0, trading_volume_usd=0.0,
            num_fills=0, pct_of_ref_profit=0.0,
        )
    result = run_sim(bars=bars, **T2_MEGA_PARAMS)
    last_close = bars[-1][3]
    realized_usd_sim = result.realized_pnl * last_close  # raw sim (mult=1)
    # Калибровка к платформенному масштабу через эмпирический множитель
    realized_usd_platform = realized_usd_sim * SIM_TO_PLATFORM_FACTOR
    return WindowResult(
        label=label,
        start=start_iso, end=end_iso, bars=len(bars),
        realized_pnl_btc=result.realized_pnl,
        realized_pnl_usd=realized_usd_platform,
        unrealized_pnl_btc=result.unrealized_pnl,
        trading_volume_usd=result.trading_volume_usd * SIM_TO_PLATFORM_FACTOR,
        num_fills=result.num_fills,
        pct_of_ref_profit=realized_usd_platform / REF_PROFIT_PLATFORM * 100 if REF_PROFIT_PLATFORM else 0.0,
    )


def _gen_windows(span_days: int = 90, step_days: int = 30,
                 start_iso: str = "2024-05-01", end_iso: str = "2026-04-29") -> list[tuple[str, str, str]]:
    """Скользящие 3-мес окна с шагом 30 дней."""
    start = datetime.fromisoformat(start_iso).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(end_iso).replace(tzinfo=timezone.utc)
    windows = []
    cur = start
    while cur + timedelta(days=span_days) <= end:
        w_start = cur
        w_end = cur + timedelta(days=span_days)
        label = f"{w_start.date().isoformat()}→{w_end.date().isoformat()}"
        windows.append((label, w_start.date().isoformat(), w_end.date().isoformat()))
        cur += timedelta(days=step_days)
    return windows


def run_walk_forward(span_days: int = 90, step_days: int = 30) -> list[WindowResult]:
    """Полный walk-forward: 3-мес окна со сдвигом 30 дней по всему 2y dataset."""
    windows = _gen_windows(span_days=span_days, step_days=step_days)
    return [run_window(*w) for w in windows]


def format_walk_forward(results: list[WindowResult]) -> str:
    if not results:
        return "Нет окон для прогона."
    lines = [
        "🚶 Walk-forward T2-MEGA (real GridBotSim simulation)",
        "",
        f"{'window':<28} {'bars':>6} {'fills':>5} {'profit$':>9} {'vol M$':>7} {'%ref':>5}",
        "-" * 70,
    ]
    profits = []
    vols = []
    for r in results:
        profits.append(r.realized_pnl_usd)
        vols.append(r.trading_volume_usd)
        lines.append(
            f"{r.label:<28} {r.bars:>6} {r.num_fills:>5} "
            f"{r.realized_pnl_usd:>+9.0f} "
            f"{r.trading_volume_usd / 1e6:>6.2f} "
            f"{r.pct_of_ref_profit:>4.0f}%"
        )
    pos_count = sum(1 for p in profits if p > 0)
    lines += [
        "-" * 70,
        f"Окон: {len(results)}, положительных: {pos_count} ({pos_count/len(results)*100:.0f}%)",
        f"Средний profit: {sum(profits)/len(profits):+.0f}$ "
        f"(min {min(profits):+.0f}, max {max(profits):+.0f})",
        f"Средний vol:    ${sum(vols)/len(vols)/1e6:.2f}M",
        "",
        "Интерпретация:",
        "- pos% < 60% → T2-MEGA overfit к выбранному периоду",
        "- pos% > 80% → конфиг устойчив",
        "- profit ниже эталона в 2-3× ожидаем (sim не моделирует mult=1.3)",
    ]
    return "\n".join(lines)
