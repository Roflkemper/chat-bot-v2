"""Tests for brief generator, virtual trader, live monitor, and delivery."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from services.market_forward_analysis.brief_generator import (
    generate_brief, Level, DayPotential, VirtualTraderSnapshot,
)
from services.market_forward_analysis.regime_switcher import ForecastResult
from services.market_forward_analysis.virtual_trader import (
    VirtualTrader, evaluate_signal, update_position,
)
from services.market_forward_analysis import virtual_trader as vt_mod
from services.market_forward_analysis import live_monitor as lm_mod
from services.market_forward_analysis.live_monitor import (
    record_prediction, resolve_pending, rolling_brier, check_alerts,
)
from services.market_forward_analysis.delivery import (
    DeliveryState, should_send, update_state, send_brief,
)


# ── Brief generator ──────────────────────────────────────────────────────────

def _make_forecasts(prob_up_1h=0.42, mode_1d="qualitative"):
    return {
        "1h": ForecastResult("1h", "numeric", prob_up_1h, 0.18, None),
        "4h": ForecastResult("4h", "numeric", 0.46, 0.09, None),
        "1d": ForecastResult("1d", mode_1d, "lean_down" if mode_1d == "qualitative" else 0.40,
                             0.0 if mode_1d == "qualitative" else 0.06, None),
    }


def _sample_levels():
    return [
        Level(price=67500, label="зона предложения (хай NY-сессии)", kind="supply",
              scenarios=[
                  {"name": "А", "trigger": "пробой полным телом NY-сессии",
                   "target": "68800–69200 (следующая supply)", "rr": "2.3",
                   "action_long": "рассмотри частичный TP 30–40% на 67800",
                   "action_short": "сдвинь стоп выше 68000",
                   "action_flat": "false breakout в MARKDOWN частый — шорт со стопом 68200"}
              ]),
        Level(price=64000, label="зона спроса (свеча капитуляции)", kind="demand",
              scenarios=[
                  {"name": "А", "trigger": "волатильный обвал к зоне",
                   "action_long": "лонг на бычьей реакции 4ч, стоп 63500"}
              ]),
    ]


def test_brief_renders_all_sections():
    text = generate_brief(
        timestamp=datetime(2026, 5, 4, 9, 0, tzinfo=timezone.utc),
        price=67050, pct_24h=1.2,
        regime="MARKDOWN", regime_confidence=0.85,
        stable_bars=14, switch_pending=False,
        forecasts=_make_forecasts(),
        levels=_sample_levels(),
        day_potential=DayPotential(60, (64500, 67200), 25, "64000 → 62500 при сломе 64k", 15, "67500 пробит → 69000+"),
        virtual_trader=VirtualTraderSnapshot(
            today_setup={"direction": "short", "entry": 67500, "sl": 68200, "tp1": 65500, "tp2": 64000,
                         "rr1": 2.9, "rr2": 5.0, "ttl": "до 18:00 UTC", "reason": "зона предложения"},
            open_positions=[{"direction": "short", "entry": 67000, "entry_time_str": "03 мая 14:00", "pnl_pct": 0.3}],
            stats_7d={"signals": 4, "wins": 2, "losses": 1, "open": 1, "avg_rr": 1.6},
        ),
        watches=[
            {"key": "funding_flip"},
            {"key": "volume_spike"},
            {"key": "regime_change", "args": {"from_r": "MARKDOWN", "to_r": "RANGE"}},
        ],
    )
    # All section headers present
    for section in ["УТРЕННИЙ БРИФ", "📍 РЕЖИМ:", "📊 ПРОГНОЗ:", "🎯 КЛЮЧЕВЫЕ УРОВНИ",
                    "🎲 ПОТЕНЦИАЛ ДНЯ", "🤖 ВИРТУАЛЬНАЯ ТОРГОВЛЯ БОТА", "👀 СЛЕДИМ ЗА:",
                    "не торговый совет"]:
        assert section in text, f"missing section: {section}"
    # Russian content
    assert "медвежий уклон" in text
    assert "качественный" in text
    # Watch lines translated
    assert "Funding flip" in text
    assert "MARKDOWN → RANGE" in text


def test_brief_skips_far_levels():
    far_level = Level(price=80000, label="дальняя зона", kind="supply", scenarios=[])
    text = generate_brief(
        timestamp=datetime(2026, 5, 4, 9, 0, tzinfo=timezone.utc),
        price=67050, pct_24h=0,
        regime="RANGE", regime_confidence=0.7, stable_bars=20, switch_pending=False,
        forecasts=_make_forecasts(),
        levels=[far_level],
        day_potential=DayPotential(50, (66000, 68000), 25, "x", 25, "y"),
        virtual_trader=VirtualTraderSnapshot(),
        watches=[{"key": "funding_flip"}],
    )
    assert "80000" not in text  # > 5% away → skipped


def test_brief_qualitative_forecast_mode():
    fc = {
        "1h": ForecastResult("1h", "qualitative", "lean_up", 0.0, None),
        "4h": ForecastResult("4h", "qualitative", "lean_up", 0.0, None),
        "1d": ForecastResult("1d", "qualitative", "lean_up", 0.0, None),
    }
    text = generate_brief(
        timestamp=datetime(2026, 5, 4, 9, 0, tzinfo=timezone.utc),
        price=67050, pct_24h=0,
        regime="MARKUP", regime_confidence=0.7, stable_bars=20, switch_pending=False,
        forecasts=fc, levels=[],
        day_potential=DayPotential(50, (66000, 68000), 25, "x", 25, "y"),
        virtual_trader=VirtualTraderSnapshot(),
        watches=[{"key": "funding_flip"}],
    )
    assert "бычий уклон" in text
    assert "качественный" in text


# ── Virtual trader ────────────────────────────────────────────────────────────

def _isolate_log(tmp_path, monkeypatch):
    monkeypatch.setattr(vt_mod, "_LOG_DIR", tmp_path)
    monkeypatch.setattr(vt_mod, "_LOG_PATH", tmp_path / "positions_log.jsonl")


def test_signal_long_in_markup(tmp_path, monkeypatch):
    _isolate_log(tmp_path, monkeypatch)
    fc = {"1h": ForecastResult("1h", "numeric", 0.62, 0.2, None)}
    bar_t = datetime(2026, 5, 4, 9, 0, tzinfo=timezone.utc)
    pos = evaluate_signal(fc, "MARKUP", bar_t, bar_price=67000, bar_atr=300)
    assert pos is not None
    assert pos.direction == "long"
    assert pos.sl < pos.entry_price < pos.tp1 < pos.tp2
    # SL = 1.2 * ATR below entry
    assert abs(pos.sl - (67000 - 1.2 * 300)) < 0.01


def test_signal_short_in_markdown(tmp_path, monkeypatch):
    _isolate_log(tmp_path, monkeypatch)
    fc = {"1h": ForecastResult("1h", "numeric", 0.40, 0.2, None)}
    bar_t = datetime(2026, 5, 4, 9, 0, tzinfo=timezone.utc)
    pos = evaluate_signal(fc, "MARKDOWN", bar_t, bar_price=67000, bar_atr=300)
    assert pos is not None
    assert pos.direction == "short"
    assert pos.sl > pos.entry_price > pos.tp1 > pos.tp2


def test_no_signal_below_threshold(tmp_path, monkeypatch):
    _isolate_log(tmp_path, monkeypatch)
    fc = {"1h": ForecastResult("1h", "numeric", 0.52, 0.1, None)}
    pos = evaluate_signal(fc, "MARKDOWN", datetime.now(timezone.utc), 67000, 300)
    assert pos is None


def test_no_signal_on_qualitative(tmp_path, monkeypatch):
    _isolate_log(tmp_path, monkeypatch)
    fc = {"1h": ForecastResult("1h", "qualitative", "lean_down", 0.0, None)}
    pos = evaluate_signal(fc, "MARKDOWN", datetime.now(timezone.utc), 67000, 300)
    assert pos is None


def test_position_sl_hit(tmp_path, monkeypatch):
    _isolate_log(tmp_path, monkeypatch)
    fc = {"1h": ForecastResult("1h", "numeric", 0.62, 0.2, None)}
    t0 = datetime(2026, 5, 4, 9, 0, tzinfo=timezone.utc)
    pos = evaluate_signal(fc, "MARKUP", t0, 67000, 300)
    # Bar that hits SL (low <= 67000 - 360 = 66640)
    pos = update_position(pos, t0 + timedelta(minutes=30), bar_high=67050, bar_low=66600)
    assert pos.status == "closed_sl"
    assert pos.r_realized == -1.0


def test_position_tp1_then_tp2(tmp_path, monkeypatch):
    _isolate_log(tmp_path, monkeypatch)
    fc = {"1h": ForecastResult("1h", "numeric", 0.62, 0.2, None)}
    t0 = datetime(2026, 5, 4, 9, 0, tzinfo=timezone.utc)
    pos = evaluate_signal(fc, "MARKUP", t0, 67000, 300)
    # First bar: hit TP1 only (high reaches tp1, not tp2)
    pos = update_position(pos, t0 + timedelta(minutes=30), bar_high=pos.tp1 + 1, bar_low=66950)
    assert pos.half_closed
    assert pos.status == "tp1_hit"
    # Second bar: hit TP2 too
    pos = update_position(pos, t0 + timedelta(hours=1), bar_high=pos.tp2 + 1, bar_low=pos.tp1)
    assert pos.status == "closed_tp2"
    # 50% at TP1 (1.5R) + 50% at TP2 (3.0R) = 2.25R
    assert abs(pos.r_realized - 2.25) < 0.01


def test_position_time_exit(tmp_path, monkeypatch):
    _isolate_log(tmp_path, monkeypatch)
    fc = {"1h": ForecastResult("1h", "numeric", 0.62, 0.2, None)}
    t0 = datetime(2026, 5, 4, 9, 0, tzinfo=timezone.utc)
    pos = evaluate_signal(fc, "MARKUP", t0, 67000, 300)
    # Step past TTL (4h) without hitting SL or TP
    pos = update_position(pos, t0 + timedelta(hours=5), bar_high=67100, bar_low=66950)
    assert pos.status == "closed_time"


def test_trader_persistence(tmp_path, monkeypatch):
    _isolate_log(tmp_path, monkeypatch)
    trader = VirtualTrader()
    fc = {"1h": ForecastResult("1h", "numeric", 0.62, 0.2, None)}
    t0 = datetime(2026, 5, 4, 9, 0, tzinfo=timezone.utc)
    p = trader.evaluate_and_open(fc, "MARKUP", t0, 67000, 300)
    assert p is not None
    # Re-open trader instance, should resurrect from log
    trader2 = VirtualTrader()
    assert trader2.open_pos is not None
    assert trader2.open_pos.position_id == p.position_id


def test_trader_only_one_open(tmp_path, monkeypatch):
    _isolate_log(tmp_path, monkeypatch)
    trader = VirtualTrader()
    fc = {"1h": ForecastResult("1h", "numeric", 0.62, 0.2, None)}
    t0 = datetime(2026, 5, 4, 9, 0, tzinfo=timezone.utc)
    p1 = trader.evaluate_and_open(fc, "MARKUP", t0, 67000, 300)
    p2 = trader.evaluate_and_open(fc, "MARKUP", t0 + timedelta(minutes=10), 67100, 300)
    assert p1 is not None
    assert p2 is None  # already have open


def test_trader_stats_window(tmp_path, monkeypatch):
    _isolate_log(tmp_path, monkeypatch)
    trader = VirtualTrader()
    fc = {"1h": ForecastResult("1h", "numeric", 0.62, 0.2, None)}
    now = datetime(2026, 5, 4, 9, 0, tzinfo=timezone.utc)
    # Open + close a winning trade
    p = trader.evaluate_and_open(fc, "MARKUP", now - timedelta(days=1), 67000, 300)
    trader.step(now - timedelta(days=1, hours=-1), bar_high=p.tp2 + 10, bar_low=66980)
    s = trader.stats(window_days=7, now=now)
    assert s["signals"] >= 1
    assert s["wins"] == 1


# ── Live monitor ─────────────────────────────────────────────────────────────

def _isolate_brier_log(tmp_path, monkeypatch):
    monkeypatch.setattr(lm_mod, "_LOG_PATH", tmp_path / "live_brier_log.jsonl")


def test_record_and_resolve(tmp_path, monkeypatch):
    _isolate_brier_log(tmp_path, monkeypatch)
    t0 = datetime(2026, 5, 4, 9, 0, tzinfo=timezone.utc)
    record_prediction(t0, "MARKDOWN", "1h", prob_up=0.4, entry_price=67000)
    # Build price series: at +1h, close went down (actual_up=0)
    idx = pd.DatetimeIndex([t0, t0 + timedelta(hours=1)], tz="UTC")
    prices = pd.Series([67000, 66600], index=idx)
    n = resolve_pending(t0 + timedelta(hours=1, minutes=5), prices)
    assert n == 1
    rb = rolling_brier("MARKDOWN", "1h")
    assert rb is not None
    # Brier of (0.4 - 0)^2 = 0.16
    assert abs(rb - 0.16) < 0.01


def test_alert_fires_on_high_brier(tmp_path, monkeypatch):
    _isolate_brier_log(tmp_path, monkeypatch)
    t0 = datetime(2026, 5, 4, 9, 0, tzinfo=timezone.utc)
    # Predict prob_up=0.9 but actual goes down → Brier = 0.81
    record_prediction(t0, "MARKDOWN", "1h", prob_up=0.9, entry_price=67000)
    idx = pd.DatetimeIndex([t0, t0 + timedelta(hours=1)], tz="UTC")
    prices = pd.Series([67000, 66600], index=idx)
    resolve_pending(t0 + timedelta(hours=1, minutes=5), prices)
    alerts = check_alerts({"MARKDOWN": {"1h": "numeric"}})
    assert len(alerts) == 1
    assert alerts[0]["regime"] == "MARKDOWN"
    assert alerts[0]["rolling_brier"] > 0.28


def test_no_alert_for_qualitative(tmp_path, monkeypatch):
    _isolate_brier_log(tmp_path, monkeypatch)
    alerts = check_alerts({"MARKDOWN": {"1d": "qualitative"}})
    assert alerts == []


# ── Delivery triggers ────────────────────────────────────────────────────────

def test_delivery_morning_trigger():
    state = DeliveryState()
    now = datetime(2026, 5, 4, 8, 0, tzinfo=timezone.utc)
    ok, reason = should_send(now, state, "MARKDOWN", 0.4)
    assert ok and reason == "morning"


def test_delivery_no_resend_same_day():
    state = DeliveryState()
    now = datetime(2026, 5, 4, 8, 0, tzinfo=timezone.utc)
    update_state(state, now, "MARKDOWN", 0.4)
    # Same day, 8:30 — should not re-send for morning trigger
    later = datetime(2026, 5, 4, 8, 30, tzinfo=timezone.utc)
    ok, _ = should_send(later, state, "MARKDOWN", 0.4)
    assert not ok


def test_delivery_regime_change_trigger():
    state = DeliveryState(last_brief_time=datetime(2026, 5, 4, 8, 0, tzinfo=timezone.utc),
                          last_regime="RANGE", last_prob_up_1h=0.5)
    now = datetime(2026, 5, 4, 14, 0, tzinfo=timezone.utc)
    ok, reason = should_send(now, state, "MARKDOWN", 0.4)
    assert ok and "regime_change" in reason


def test_delivery_forecast_shift_trigger():
    state = DeliveryState(last_brief_time=datetime(2026, 5, 4, 8, 0, tzinfo=timezone.utc),
                          last_regime="MARKDOWN", last_prob_up_1h=0.50)
    now = datetime(2026, 5, 4, 14, 0, tzinfo=timezone.utc)
    ok, reason = should_send(now, state, "MARKDOWN", 0.30)
    assert ok and "forecast_shift" in reason


def test_send_brief_with_mock():
    sent = []
    ok = send_brief("hello", send_fn=lambda t: sent.append(t))
    assert ok and sent == ["hello"]
