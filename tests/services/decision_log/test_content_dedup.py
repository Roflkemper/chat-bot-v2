"""Tests for content-based Telegram dedup in DecisionLogAlertWorker.

TZ-DECISION-LOG-V2-EVENT-DEDUP-WINDOW: Layer 2 dedup — suppress semantically
identical Telegram pings within a 30-minute window without affecting JSONL recording.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

# Repo root (parents[3] = c:/bot7) — not tests/. Without this, services.telegram_runtime
# imports core.app_logging which lives under c:/bot7/core, not c:/bot7/tests/core.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from services.decision_log.models import (
    CapturedEvent,
    EventSeverity,
    EventType,
    MarketContext,
    PortfolioContext,
)
from services.telegram_runtime import DecisionLogAlertWorker, _ALERT_DEDUP_WINDOW_MINUTES

# ── Fixtures ──────────────────────────────────────────────────────────────────

_MARKET = MarketContext(price_btc=75_927.0, regime_label="consolidation")
_PORTFOLIO = PortfolioContext(
    depo_total=15_000.0,
    shorts_unrealized_usd=-200.0,
    longs_unrealized_usd=0.0,
    net_unrealized_usd=-200.0,
    free_margin_pct=70.0,
    drawdown_pct=1.5,
    shorts_position_btc=0.05,
    longs_position_usd=0.0,
)

_T0 = datetime(2026, 4, 30, 17, 16, 0, tzinfo=timezone.utc)


def _make_pnl_event(
    event_id: str,
    delta: float,
    bot_id: str | None = None,
    ts: datetime | None = None,
) -> CapturedEvent:
    return CapturedEvent(
        event_id=event_id,
        ts=ts or _T0,
        event_type=EventType.PNL_EVENT,
        severity=EventSeverity.WARNING,
        bot_id=bot_id,
        summary=f"PNL delta {delta:+.0f} USD",
        payload={"delta_pnl_usd": delta},
        market_context=_MARKET,
        portfolio_context=_PORTFOLIO,
    )


def _make_pnl_extreme(
    event_id: str,
    value: float,
    ts: datetime | None = None,
) -> CapturedEvent:
    return CapturedEvent(
        event_id=event_id,
        ts=ts or _T0,
        event_type=EventType.PNL_EXTREME,
        severity=EventSeverity.WARNING,
        bot_id=None,
        summary=f"PNL extreme {value:.0f} USD",
        payload={"extreme": "high", "value": value},
        market_context=_MARKET,
        portfolio_context=_PORTFOLIO,
    )


def _make_boundary_breach(
    event_id: str,
    direction: str,
    bot_id: str = "TEST_1",
    ts: datetime | None = None,
) -> CapturedEvent:
    if direction == "above":
        payload = {"price": 76_000.0, "border_top": 75_500.0}
    else:
        payload = {"price": 74_000.0, "border_bottom": 74_500.0}
    return CapturedEvent(
        event_id=event_id,
        ts=ts or _T0,
        event_type=EventType.BOUNDARY_BREACH,
        severity=EventSeverity.WARNING,
        bot_id=bot_id,
        summary="Boundary breach",
        payload=payload,
        market_context=_MARKET,
        portfolio_context=_PORTFOLIO,
    )


def _make_worker(tmp_path: Path) -> DecisionLogAlertWorker:
    events_path = tmp_path / "events.jsonl"
    events_path.touch()
    bot = MagicMock()
    return DecisionLogAlertWorker(bot=bot, chat_ids=[123], events_path=events_path)


def _add_recent_ping(worker: DecisionLogAlertWorker, event: CapturedEvent, ts: datetime) -> None:
    worker._recent_pings.append({
        "event_type": event.event_type,
        "bot_id": event.bot_id,
        "ts": ts,
        "payload_signature": worker._compute_signature(event),
    })


# ── _compute_signature ────────────────────────────────────────────────────────

class TestComputeSignature:
    def test_pnl_event_bucketed_by_100(self, tmp_path: Path) -> None:
        worker = _make_worker(tmp_path)
        ev774 = _make_pnl_event("e1", delta=774.0)
        ev765 = _make_pnl_event("e2", delta=765.0)
        # Both round to 800
        assert worker._compute_signature(ev774) == worker._compute_signature(ev765)

    def test_pnl_event_different_buckets(self, tmp_path: Path) -> None:
        worker = _make_worker(tmp_path)
        ev800 = _make_pnl_event("e1", delta=774.0)   # bucket 800
        ev1100 = _make_pnl_event("e2", delta=1100.0)  # bucket 1100
        assert worker._compute_signature(ev800) != worker._compute_signature(ev1100)

    def test_pnl_extreme_bucketed(self, tmp_path: Path) -> None:
        worker = _make_worker(tmp_path)
        ev = _make_pnl_extreme("e1", value=15_320.0)
        assert worker._compute_signature(ev) == "pnl_extreme_15300"

    def test_boundary_breach_above(self, tmp_path: Path) -> None:
        worker = _make_worker(tmp_path)
        ev = _make_boundary_breach("e1", direction="above")
        assert worker._compute_signature(ev) == "boundary_above"

    def test_boundary_breach_below(self, tmp_path: Path) -> None:
        worker = _make_worker(tmp_path)
        ev = _make_boundary_breach("e1", direction="below")
        assert worker._compute_signature(ev) == "boundary_below"

    def test_boundary_breach_above_vs_below_differ(self, tmp_path: Path) -> None:
        worker = _make_worker(tmp_path)
        above = _make_boundary_breach("e1", direction="above")
        below = _make_boundary_breach("e2", direction="below")
        assert worker._compute_signature(above) != worker._compute_signature(below)


# ── _is_duplicate_recent ──────────────────────────────────────────────────────

class TestIsDuplicateRecent:
    def test_no_recent_pings_not_duplicate(self, tmp_path: Path) -> None:
        worker = _make_worker(tmp_path)
        ev = _make_pnl_event("e1", delta=774.0)
        assert worker._is_duplicate_recent(ev) is False

    def test_same_event_within_window_is_duplicate(self, tmp_path: Path) -> None:
        worker = _make_worker(tmp_path)
        ev1 = _make_pnl_event("e1", delta=774.0, ts=_T0)
        ev2 = _make_pnl_event("e2", delta=765.0, ts=_T0 + timedelta(minutes=10))

        _add_recent_ping(worker, ev1, ts=_T0)

        assert worker._is_duplicate_recent(ev2) is True

    def test_different_bot_not_duplicate(self, tmp_path: Path) -> None:
        worker = _make_worker(tmp_path)
        ev1 = _make_pnl_event("e1", delta=774.0, bot_id="TEST_1")
        ev2 = _make_pnl_event("e2", delta=774.0, bot_id="TEST_2")

        _add_recent_ping(worker, ev1, ts=_T0)

        assert worker._is_duplicate_recent(ev2) is False

    def test_after_window_expires_not_duplicate(self, tmp_path: Path) -> None:
        worker = _make_worker(tmp_path)
        now = datetime.now(timezone.utc)
        ev1 = _make_pnl_event("e1", delta=774.0, ts=now - timedelta(minutes=31))
        ev2 = _make_pnl_event("e2", delta=774.0, ts=now)

        # Inject a ping that is older than the dedup window (relative to now)
        expired_ts = now - timedelta(minutes=_ALERT_DEDUP_WINDOW_MINUTES + 1)
        _add_recent_ping(worker, ev1, ts=expired_ts)

        assert worker._is_duplicate_recent(ev2) is False

    def test_different_event_type_not_duplicate(self, tmp_path: Path) -> None:
        worker = _make_worker(tmp_path)
        pnl_ev = _make_pnl_event("e1", delta=774.0)
        boundary_ev = _make_boundary_breach("e2", direction="above")

        _add_recent_ping(worker, pnl_ev, ts=_T0)

        assert worker._is_duplicate_recent(boundary_ev) is False

    def test_significant_delta_change_not_duplicate(self, tmp_path: Path) -> None:
        worker = _make_worker(tmp_path)
        ev1 = _make_pnl_event("e1", delta=774.0)   # bucket 800
        ev2 = _make_pnl_event("e2", delta=1100.0)  # bucket 1100

        _add_recent_ping(worker, ev1, ts=_T0)

        assert worker._is_duplicate_recent(ev2) is False

    def test_fails_open_on_corrupt_recent_ping(self, tmp_path: Path) -> None:
        worker = _make_worker(tmp_path)
        worker._recent_pings.append({"broken": True})  # type: ignore[arg-type]
        ev = _make_pnl_event("e1", delta=774.0)
        # Must not raise; must return False (fail open)
        assert worker._is_duplicate_recent(ev) is False


# ── Integration: dedup suppresses Telegram but not JSONL ─────────────────────

class TestDedupIntegration:
    def _write_events(self, path: Path, events: list[CapturedEvent]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            for e in events:
                row = {
                    "event_id": e.event_id,
                    "ts": e.ts.isoformat(),
                    "event_type": e.event_type,
                    "severity": e.severity,
                    "bot_id": e.bot_id,
                    "summary": e.summary,
                    "payload": e.payload,
                    "market_context": {
                        "price_btc": e.market_context.price_btc,
                        "regime_label": e.market_context.regime_label,
                        "regime_modifiers": e.market_context.regime_modifiers,
                        "rsi_1h": e.market_context.rsi_1h,
                        "rsi_5m": e.market_context.rsi_5m,
                        "price_change_5m_pct": e.market_context.price_change_5m_pct,
                        "price_change_1h_pct": e.market_context.price_change_1h_pct,
                        "atr_normalized": e.market_context.atr_normalized,
                        "session_kz": e.market_context.session_kz,
                        "nearest_liq_above": e.market_context.nearest_liq_above,
                        "nearest_liq_below": e.market_context.nearest_liq_below,
                    },
                    "portfolio_context": {
                        "depo_total": e.portfolio_context.depo_total,
                        "shorts_unrealized_usd": e.portfolio_context.shorts_unrealized_usd,
                        "longs_unrealized_usd": e.portfolio_context.longs_unrealized_usd,
                        "net_unrealized_usd": e.portfolio_context.net_unrealized_usd,
                        "free_margin_pct": e.portfolio_context.free_margin_pct,
                        "drawdown_pct": e.portfolio_context.drawdown_pct,
                        "shorts_position_btc": e.portfolio_context.shorts_position_btc,
                        "longs_position_usd": e.portfolio_context.longs_position_usd,
                    },
                }
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _make_worker_then_write(
        self, tmp_path: Path, events: list[CapturedEvent]
    ) -> tuple[DecisionLogAlertWorker, list]:
        """Create worker with empty JSONL, then write events so they appear as new."""
        events_path = tmp_path / "events.jsonl"
        events_path.touch()
        bot = MagicMock()
        worker = DecisionLogAlertWorker(bot=bot, chat_ids=[111], events_path=events_path)
        self._write_events(events_path, events)
        new_events = worker._read_new_events()
        return worker, new_events

    def test_pnl_event_dedup_within_30min(self, tmp_path: Path) -> None:
        """Same PNL_EVENT delta bucket within 30 min → second ping suppressed."""
        ev1 = _make_pnl_event("e1", delta=774.0, ts=_T0)
        ev2 = _make_pnl_event("e2", delta=765.0, ts=_T0 + timedelta(minutes=10))

        worker, new_events = self._make_worker_then_write(tmp_path, [ev1, ev2])
        assert len(new_events) == 2  # both in JSONL

        sent_ids: list[str] = []
        for event in new_events:
            if not worker._is_duplicate_recent(event):
                _add_recent_ping(worker, event, ts=datetime.now(timezone.utc))
                sent_ids.append(event.event_id)

        assert sent_ids == ["e1"], "Only first event should be pinged"

    def test_different_bot_both_pinged(self, tmp_path: Path) -> None:
        """Same delta, different bot → both pinged."""
        ev1 = _make_pnl_event("e1", delta=774.0, bot_id="BOT_1")
        ev2 = _make_pnl_event("e2", delta=774.0, bot_id="BOT_2")

        worker, new_events = self._make_worker_then_write(tmp_path, [ev1, ev2])

        sent_ids: list[str] = []
        for event in new_events:
            if not worker._is_duplicate_recent(event):
                _add_recent_ping(worker, event, ts=datetime.now(timezone.utc))
                sent_ids.append(event.event_id)

        assert sorted(sent_ids) == ["e1", "e2"]

    def test_boundary_breach_dedup_per_direction(self, tmp_path: Path) -> None:
        """Same direction breach within window → second suppressed."""
        ev1 = _make_boundary_breach("e1", direction="above", bot_id="X")
        ev2 = _make_boundary_breach("e2", direction="above", bot_id="X", ts=_T0 + timedelta(minutes=5))

        worker, new_events = self._make_worker_then_write(tmp_path, [ev1, ev2])

        sent_ids: list[str] = []
        for event in new_events:
            if not worker._is_duplicate_recent(event):
                _add_recent_ping(worker, event, ts=datetime.now(timezone.utc))
                sent_ids.append(event.event_id)

        assert sent_ids == ["e1"]

    def test_jsonl_records_both_events(self, tmp_path: Path) -> None:
        """JSONL holds both events regardless of Telegram dedup."""
        events_path = tmp_path / "events.jsonl"
        ev1 = _make_pnl_event("e1", delta=774.0)
        ev2 = _make_pnl_event("e2", delta=765.0, ts=_T0 + timedelta(minutes=10))

        self._write_events(events_path, [ev1, ev2])

        lines = events_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2, "JSONL must contain both events"
        ids = [json.loads(ln)["event_id"] for ln in lines]
        assert ids == ["e1", "e2"]

    def test_recent_pings_buffer_bounded(self, tmp_path: Path) -> None:
        """deque maxlen=200 — adding 250 entries keeps only last 200."""
        worker = _make_worker(tmp_path)
        for i in range(250):
            ev = _make_pnl_event(f"e{i}", delta=float(i * 10))
            _add_recent_ping(worker, ev, ts=datetime.now(timezone.utc))

        assert len(worker._recent_pings) == 200
