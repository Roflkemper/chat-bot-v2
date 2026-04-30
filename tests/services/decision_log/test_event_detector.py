from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from services.decision_log.event_detector import build_portfolio_context, detect_events
from services.decision_log.models import EventSeverity, EventType, MarketContext


def _now() -> datetime:
    return datetime(2026, 4, 30, 12, 0, tzinfo=timezone.utc)


def _market(price: float = 76520.0) -> MarketContext:
    return MarketContext(
        price_btc=price,
        regime_label="trend_up",
        regime_modifiers=[],
        rsi_1h=55.0,
        rsi_5m=60.0,
        price_change_5m_pct=0.4,
        price_change_1h_pct=1.2,
        atr_normalized=0.01,
        session_kz="NY_AM",
        nearest_liq_above=77000.0,
        nearest_liq_below=75800.0,
    )


def _market_with(**kwargs: Any) -> MarketContext:
    defaults: dict[str, Any] = dict(
        price_btc=76520.0,
        regime_label="trend_up",
        regime_modifiers=[],
        rsi_1h=55.0,
        rsi_5m=60.0,
        price_change_5m_pct=0.4,
        price_change_1h_pct=1.2,
        atr_normalized=0.01,
        session_kz="NY_AM",
        nearest_liq_above=77000.0,
        nearest_liq_below=75800.0,
    )
    defaults.update(kwargs)
    return MarketContext(**defaults)


def _snap(position: str = "-0.100", profit: str = "-100", status: str = "2") -> dict[str, str]:
    return {
        "ts_utc": "2026-04-30T12:00:00+00:00",
        "bot_id": "1",
        "alias": "TEST_1",
        "status": status,
        "position": position,
        "current_profit": profit,
        "average_price": "76000",
    }


def _params(target: str = "0.25", grid_step: str = "0.03", border_top: str = "78600", border_bottom: str = "68000") -> dict[str, str]:
    return {
        "bot_id": "1",
        "alias": "TEST_1",
        "target": target,
        "grid_step": grid_step,
        "instop": "0.01",
        "border_top": border_top,
        "border_bottom": border_bottom,
        "raw_params_json": "{}",
    }


def _portfolio(snapshots: dict[str, dict[str, str]], free_margin_pct: float = 50.0):
    return build_portfolio_context(snapshots, free_margin_pct=free_margin_pct, depo_total=15000.0, drawdown_pct=8.0)


# ── existing tests ────────────────────────────────────────────────────────────

def test_detects_param_change_when_gap_tog_changed() -> None:
    events, _ = detect_events({"1": _snap()}, {"1": _params(target="0.30")}, {"snapshots": {"1": _snap()}, "params": {"1": _params(target="0.25")}}, now=_now(), market_context=_market(), portfolio_context=_portfolio({"1": _snap()}))
    assert any(event.event_type == EventType.PARAM_CHANGE for event in events)


def test_detects_param_change_when_gs_changed() -> None:
    events, _ = detect_events({"1": _snap()}, {"1": _params(grid_step="0.05")}, {"snapshots": {"1": _snap()}, "params": {"1": _params(grid_step="0.03")}}, now=_now(), market_context=_market(), portfolio_context=_portfolio({"1": _snap()}))
    assert any(event.event_type == EventType.PARAM_CHANGE for event in events)


def test_no_event_when_params_unchanged() -> None:
    events, _ = detect_events({"1": _snap()}, {"1": _params()}, {"snapshots": {"1": _snap()}, "params": {"1": _params()}}, now=_now(), market_context=_market(), portfolio_context=_portfolio({"1": _snap()}))
    assert not any(event.event_type == EventType.PARAM_CHANGE for event in events)


def test_detects_position_change_when_delta_above_5pct() -> None:
    events, _ = detect_events({"1": _snap(position="-0.120")}, {"1": _params()}, {"snapshots": {"1": _snap(position="-0.100")}, "params": {"1": _params()}}, now=_now(), market_context=_market(), portfolio_context=_portfolio({"1": _snap(position="-0.120")}))
    assert any(event.event_type == EventType.POSITION_CHANGE for event in events)


def test_no_position_event_when_delta_below_5pct() -> None:
    events, _ = detect_events({"1": _snap(position="-0.104")}, {"1": _params()}, {"snapshots": {"1": _snap(position="-0.100")}, "params": {"1": _params()}}, now=_now(), market_context=_market(), portfolio_context=_portfolio({"1": _snap(position="-0.104")}))
    assert not any(event.event_type == EventType.POSITION_CHANGE for event in events)


def test_detects_pnl_event_when_delta_above_200_in_15min() -> None:
    state = {"portfolio_history": [{"ts": (_now() - timedelta(minutes=15)).isoformat(), "net_unrealized_usd": -100.0}]}
    portfolio = _portfolio({"1": _snap(profit="-350")})
    events, _ = detect_events({"1": _snap(profit="-350")}, {"1": _params()}, state, now=_now(), market_context=_market(), portfolio_context=portfolio)
    assert any(event.event_type == EventType.PNL_EVENT for event in events)


def test_detects_pnl_extreme_when_new_24h_low() -> None:
    state = {"portfolio_history": [{"ts": (_now() - timedelta(hours=1)).isoformat(), "net_unrealized_usd": -100.0}]}
    portfolio = _portfolio({"1": _snap(profit="-350")})
    events, _ = detect_events({"1": _snap(profit="-350")}, {"1": _params()}, state, now=_now(), market_context=_market(), portfolio_context=portfolio)
    assert any(event.event_type == EventType.PNL_EXTREME for event in events)


def test_detects_margin_alert_at_threshold_crossing() -> None:
    portfolio = _portfolio({"1": _snap()}, free_margin_pct=29.0)
    events, _ = detect_events({"1": _snap()}, {"1": _params()}, {"free_margin_pct": 31.0}, now=_now(), market_context=_market(), portfolio_context=portfolio)
    assert any(event.event_type == EventType.MARGIN_ALERT for event in events)


def test_no_margin_alert_when_threshold_not_crossed() -> None:
    portfolio = _portfolio({"1": _snap()}, free_margin_pct=58.0)
    events, _ = detect_events({"1": _snap()}, {"1": _params()}, {"free_margin_pct": 59.0}, now=_now(), market_context=_market(), portfolio_context=portfolio)
    assert not any(event.event_type == EventType.MARGIN_ALERT for event in events)


def test_detects_boundary_breach_when_price_above_boundary() -> None:
    events, _ = detect_events({"1": _snap()}, {"1": _params(border_top="76000")}, {"snapshots": {"1": _snap()}, "params": {"1": _params(border_top="76000")}}, now=_now(), market_context=_market(price=76520.0), portfolio_context=_portfolio({"1": _snap()}))
    assert any(event.event_type == EventType.BOUNDARY_BREACH for event in events)


def test_event_id_unique_within_session() -> None:
    state = {"snapshots": {"1": _snap()}, "params": {"1": _params(target="0.25")}}
    events, _ = detect_events({"1": _snap(position="-0.120")}, {"1": _params(target="0.30")}, state, now=_now(), market_context=_market(), portfolio_context=_portfolio({"1": _snap(position="-0.120")}))
    assert len({event.event_id for event in events}) == len(events)


def test_event_id_format_evt_yyyymmdd_nnnn() -> None:
    state = {"snapshots": {"1": _snap()}, "params": {"1": _params(target="0.25")}}
    events, _ = detect_events({"1": _snap(position="-0.120")}, {"1": _params(target="0.30")}, state, now=_now(), market_context=_market(), portfolio_context=_portfolio({"1": _snap(position="-0.120")}))
    assert events[0].event_id == "evt-20260430-0001"


# ── new tests: Fix 1 — cold start protection ──────────────────────────────────

def test_cold_start_no_events_generated_when_last_seen_empty() -> None:
    events, new_state = detect_events(
        {"1": _snap()}, {"1": _params()}, {},
        now=_now(), market_context=_market(), portfolio_context=_portfolio({"1": _snap()}),
    )
    assert events == []
    assert new_state.get("initialized") is True


def test_cold_start_events_generated_on_second_iteration() -> None:
    _, state_after_first = detect_events(
        {"1": _snap()}, {"1": _params()}, {},
        now=_now(), market_context=_market(), portfolio_context=_portfolio({"1": _snap()}),
    )
    events, _ = detect_events(
        {"1": _snap()}, {"1": _params(target="0.30")}, state_after_first,
        now=_now() + timedelta(minutes=1),
        market_context=_market(),
        portfolio_context=_portfolio({"1": _snap()}),
    )
    assert any(event.event_type == EventType.PARAM_CHANGE for event in events)


# ── new tests: Fix 2 — context-aware severity ─────────────────────────────────

def test_boundary_breach_severity_info_in_consolidation() -> None:
    market = _market_with(price_btc=76520.0, regime_label="consolidation", price_change_1h_pct=0.2)
    events, _ = detect_events(
        {"1": _snap()}, {"1": _params(border_top="76000")},
        {"snapshots": {"1": _snap()}, "params": {"1": _params(border_top="76000")}},
        now=_now(), market_context=market, portfolio_context=_portfolio({"1": _snap()}),
    )
    breach = [e for e in events if e.event_type == EventType.BOUNDARY_BREACH]
    assert breach and breach[0].severity == EventSeverity.INFO


def test_boundary_breach_severity_warning_in_trend() -> None:
    # _market() returns trend_up with price_change_1h_pct=1.2 > 1.0 → WARNING
    events, _ = detect_events(
        {"1": _snap()}, {"1": _params(border_top="76000")},
        {"snapshots": {"1": _snap()}, "params": {"1": _params(border_top="76000")}},
        now=_now(), market_context=_market(price=76520.0), portfolio_context=_portfolio({"1": _snap()}),
    )
    breach = [e for e in events if e.event_type == EventType.BOUNDARY_BREACH]
    assert breach and breach[0].severity == EventSeverity.WARNING


def test_pnl_extreme_severity_info_below_3pct_depo() -> None:
    # depo=15000, net_unrealized=-200 (1.3%) → INFO
    state = {"portfolio_history": [{"ts": (_now() - timedelta(hours=1)).isoformat(), "net_unrealized_usd": -100.0}]}
    portfolio = _portfolio({"1": _snap(profit="-200")})
    events, _ = detect_events(
        {"1": _snap(profit="-200")}, {"1": _params()}, state,
        now=_now(), market_context=_market(), portfolio_context=portfolio,
    )
    extreme = [e for e in events if e.event_type == EventType.PNL_EXTREME]
    assert extreme and extreme[0].severity == EventSeverity.INFO


def test_pnl_extreme_severity_critical_above_8pct_depo() -> None:
    # depo=15000, net_unrealized=-1350 (9%) → CRITICAL
    state = {"portfolio_history": [{"ts": (_now() - timedelta(hours=1)).isoformat(), "net_unrealized_usd": -100.0}]}
    portfolio = _portfolio({"1": _snap(profit="-1350")})
    events, _ = detect_events(
        {"1": _snap(profit="-1350")}, {"1": _params()}, state,
        now=_now(), market_context=_market(), portfolio_context=portfolio,
    )
    extreme = [e for e in events if e.event_type == EventType.PNL_EXTREME]
    assert extreme and extreme[0].severity == EventSeverity.CRITICAL


# ── new tests: Fix 3 — dedup window ──────────────────────────────────────────

def _snap_for(bot_id: str) -> dict[str, str]:
    return {
        "ts_utc": "2026-04-30T12:00:00+00:00",
        "bot_id": bot_id,
        "alias": f"TEST_{bot_id}",
        "status": "2",
        "position": "-0.100",
        "current_profit": "-100",
        "average_price": "76000",
    }


def _params_for(bot_id: str, border_top: str = "76000") -> dict[str, str]:
    return {
        "bot_id": bot_id,
        "alias": f"TEST_{bot_id}",
        "target": "0.25",
        "grid_step": "0.03",
        "instop": "0.01",
        "border_top": border_top,
        "border_bottom": "68000",
        "raw_params_json": "{}",
    }


def test_dedup_aggregates_3_events_into_1() -> None:
    snaps = {"1": _snap_for("1"), "2": _snap_for("2"), "3": _snap_for("3")}
    params = {"1": _params_for("1"), "2": _params_for("2"), "3": _params_for("3")}
    state: dict[str, Any] = {
        "snapshots": {k: v for k, v in snaps.items()},
        "params": {k: v for k, v in params.items()},
    }
    portfolio = _portfolio(snaps)
    events, _ = detect_events(
        snaps, params, state,
        now=_now(), market_context=_market(price=76520.0), portfolio_context=portfolio,
    )
    breach = [e for e in events if e.event_type == EventType.BOUNDARY_BREACH]
    assert len(breach) == 1
    assert breach[0].bot_id == "multiple"
    assert "affected_bots" in breach[0].payload
    assert len(breach[0].payload["affected_bots"]) == 3


def test_dedup_does_not_aggregate_different_severities() -> None:
    # BOUNDARY_BREACH (NOTICE: trend_up but low delta) + PARAM_CHANGE (WARNING) → 2 separate events
    market = _market_with(price_btc=76520.0, regime_label="trend_up", price_change_1h_pct=0.5)
    state: dict[str, Any] = {
        "snapshots": {"1": _snap()},
        "params": {"1": _params(border_top="76000", target="0.25")},
    }
    events, _ = detect_events(
        {"1": _snap()}, {"1": _params(border_top="76000", target="0.30")}, state,
        now=_now(), market_context=market, portfolio_context=_portfolio({"1": _snap()}),
    )
    assert any(e.event_type == EventType.BOUNDARY_BREACH and e.severity == EventSeverity.NOTICE for e in events)
    assert any(e.event_type == EventType.PARAM_CHANGE and e.severity == EventSeverity.WARNING for e in events)
    # BOUNDARY_BREACH (NOTICE) and PARAM_CHANGE (WARNING) are not merged — different (type, severity) pairs
    bb = [e for e in events if e.event_type == EventType.BOUNDARY_BREACH]
    pc = [e for e in events if e.event_type == EventType.PARAM_CHANGE]
    assert len(bb) == 1 and bb[0].bot_id != "multiple"
    assert len(pc) == 1


def test_telegram_not_sent_for_info_or_notice() -> None:
    # Consolidation regime → BOUNDARY_BREACH → INFO → should not be WARNING/CRITICAL
    market = _market_with(price_btc=76520.0, regime_label="consolidation", price_change_1h_pct=0.2)
    events, _ = detect_events(
        {"1": _snap()}, {"1": _params(border_top="76000")},
        {"snapshots": {"1": _snap()}, "params": {"1": _params(border_top="76000")}},
        now=_now(), market_context=market, portfolio_context=_portfolio({"1": _snap()}),
    )
    breach = [e for e in events if e.event_type == EventType.BOUNDARY_BREACH]
    assert breach
    assert all(e.severity not in (EventSeverity.WARNING, EventSeverity.CRITICAL) for e in breach)
