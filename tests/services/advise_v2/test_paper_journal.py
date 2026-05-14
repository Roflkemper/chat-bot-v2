from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from services.advise_v2.paper_journal import (
    PAPER_JOURNAL_INTERVAL_SEC,
    _build_current_exposure_sync,
    _build_market_context_sync,
    _null_reason,
    _rsi,
    _run_one_iteration_sync,
    paper_journal_loop,
)
from services.advise_v2.schemas import CurrentExposure, MarketContext


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _fake_snapshot() -> dict:
    return {
        "price": 76000.0,
        "delta_1h_pct": -0.3,
        "regime": {
            "primary": "RANGE",
            "modifiers": ["WEEKEND_LOW_VOL"],
            "metrics": {
                "bb_width_pct_1h": 4.5,
                "adx_1h": 20.0,
                "adx_slope_1h": 0.1,
            },
        },
        "bots": [{"live": {"mark": 76000.0, "avg_entry": 76000.0}}],
    }


def _fake_df(closes: list[float]):
    import pandas as pd
    return pd.DataFrame({"close": closes})


def _fake_market_ctx() -> MarketContext:
    return MarketContext(
        price_btc=76000.0,
        regime_label="range_wide",
        regime_modifiers=[],
        rsi_1h=50.0,
        rsi_5m=None,
        price_change_5m_30bars_pct=0.0,
        price_change_1h_pct=-0.3,
    )


def _fake_exposure() -> CurrentExposure:
    return CurrentExposure(
        net_btc=0.0,
        shorts_btc=0.0,
        longs_btc=0.0,
        free_margin_pct=50.0,
        available_usd=10000.0,
        margin_coef_pct=10.0,
    )


# ── _rsi ──────────────────────────────────────────────────────────────────────


def test_rsi_returns_50_on_insufficient_data() -> None:
    assert _rsi([100.0] * 5) == 50.0


def test_rsi_returns_100_on_no_loss() -> None:
    closes = list(range(1, 30))  # strictly increasing
    val = _rsi(closes)
    assert val > 90.0


def test_rsi_returns_0_on_no_gain() -> None:
    closes = list(range(30, 1, -1))  # strictly decreasing
    val = _rsi(closes)
    assert val < 10.0


def test_rsi_value_in_valid_range() -> None:
    import random
    random.seed(42)
    closes = [100 + random.gauss(0, 1) for _ in range(50)]
    val = _rsi(closes)
    assert 0.0 <= val <= 100.0


# ── _null_reason ──────────────────────────────────────────────────────────────


def test_null_reason_unknown_regime() -> None:
    ctx = _fake_market_ctx()
    ctx = ctx.model_copy(update={"regime_label": "unknown"})
    exp = _fake_exposure()
    assert _null_reason(ctx, exp) == "regime_unknown"


def test_null_reason_insufficient_margin() -> None:
    ctx = _fake_market_ctx()
    exp = _fake_exposure().model_copy(update={"free_margin_pct": 15.0})
    assert _null_reason(ctx, exp) == "insufficient_margin"


def test_null_reason_no_match() -> None:
    ctx = _fake_market_ctx()
    exp = _fake_exposure()
    assert _null_reason(ctx, exp) == "no_match_above_threshold"


# ── _run_one_iteration_sync ───────────────────────────────────────────────────


def test_iteration_logs_signal_when_envelope_returned(tmp_path: Path, monkeypatch) -> None:
    import services.advise_v2.paper_journal as pj

    mock_envelope = MagicMock()
    mock_envelope.signal_id = "adv_2026-04-29_143000_001"
    mock_envelope.setup_id = "P-7"

    monkeypatch.setattr(pj, "_build_market_context_sync", lambda: _fake_market_ctx())
    monkeypatch.setattr(pj, "_build_current_exposure_sync", lambda: _fake_exposure())
    monkeypatch.setattr(pj, "generate_signal", lambda **_: mock_envelope)

    logged: list = []
    monkeypatch.setattr(pj, "log_signal", lambda env: logged.append(env))
    monkeypatch.setattr(pj, "log_null_signal", lambda **_: None)

    _run_one_iteration_sync(1)
    assert len(logged) == 1
    assert logged[0] is mock_envelope


def test_iteration_logs_null_when_no_envelope(tmp_path: Path, monkeypatch) -> None:
    import services.advise_v2.paper_journal as pj

    monkeypatch.setattr(pj, "_build_market_context_sync", lambda: _fake_market_ctx())
    monkeypatch.setattr(pj, "_build_current_exposure_sync", lambda: _fake_exposure())
    monkeypatch.setattr(pj, "generate_signal", lambda **_: None)

    null_calls: list = []
    monkeypatch.setattr(pj, "log_signal", lambda _: None)
    monkeypatch.setattr(pj, "log_null_signal", lambda **kw: null_calls.append(kw))

    _run_one_iteration_sync(1)
    assert len(null_calls) == 1
    assert "reason" in null_calls[0]


def test_iteration_logs_null_on_snapshot_failure(monkeypatch) -> None:
    import services.advise_v2.paper_journal as pj

    monkeypatch.setattr(pj, "_build_market_context_sync", lambda: (_ for _ in ()).throw(RuntimeError("api down")))
    null_calls: list = []
    monkeypatch.setattr(pj, "log_null_signal", lambda **kw: null_calls.append(kw))

    _run_one_iteration_sync(1)
    assert null_calls[0]["reason"] == "snapshot_failed"


def test_iteration_logs_null_on_exposure_failure(monkeypatch) -> None:
    import services.advise_v2.paper_journal as pj

    monkeypatch.setattr(pj, "_build_market_context_sync", lambda: _fake_market_ctx())
    monkeypatch.setattr(pj, "_build_current_exposure_sync", lambda: (_ for _ in ()).throw(RuntimeError("csv missing")))
    null_calls: list = []
    monkeypatch.setattr(pj, "log_null_signal", lambda **kw: null_calls.append(kw))

    _run_one_iteration_sync(1)
    assert null_calls[0]["reason"] == "exposure_failed"


# ── paper_journal_loop async ──────────────────────────────────────────────────


def test_loop_stops_on_stop_event(monkeypatch) -> None:
    import services.advise_v2.paper_journal as pj

    calls: list[int] = []

    def fake_iter(n: int) -> None:
        calls.append(n)

    monkeypatch.setattr(pj, "_run_one_iteration_sync", fake_iter)

    async def exercise() -> None:
        stop = asyncio.Event()
        stop.set()   # pre-set: loop should run once then exit
        await asyncio.wait_for(paper_journal_loop(interval_sec=1, stop_event=stop), timeout=2.0)

    asyncio.run(exercise())
    # ran first iteration before checking stop
    assert len(calls) >= 1


def test_loop_continues_on_iteration_error(monkeypatch) -> None:
    import services.advise_v2.paper_journal as pj

    call_count = [0]

    def failing_iter(n: int) -> None:
        call_count[0] += 1
        if call_count[0] < 3:
            raise RuntimeError("transient error")

    monkeypatch.setattr(pj, "_run_one_iteration_sync", failing_iter)

    async def exercise() -> None:
        stop = asyncio.Event()

        async def stopper() -> None:
            while call_count[0] < 3:
                await asyncio.sleep(0.01)
            stop.set()

        await asyncio.gather(
            paper_journal_loop(interval_sec=0, stop_event=stop),
            stopper(),
        )

    asyncio.run(exercise())
    assert call_count[0] >= 3


def test_loop_increments_signal_counter(monkeypatch) -> None:
    import services.advise_v2.paper_journal as pj

    counters: list[int] = []

    def capture_iter(n: int) -> None:
        counters.append(n)

    monkeypatch.setattr(pj, "_run_one_iteration_sync", capture_iter)

    async def exercise() -> None:
        stop = asyncio.Event()

        async def stopper() -> None:
            while len(counters) < 3:
                await asyncio.sleep(0.01)
            stop.set()

        await asyncio.gather(
            paper_journal_loop(interval_sec=0, stop_event=stop),
            stopper(),
        )

    asyncio.run(exercise())
    assert counters == list(range(1, len(counters) + 1))


def test_default_interval_is_300() -> None:
    assert PAPER_JOURNAL_INTERVAL_SEC == 300


# ── app_runner integration ────────────────────────────────────────────────────


def test_app_runner_has_paper_journal_task() -> None:
    import app_runner
    import inspect
    src = inspect.getsource(app_runner)
    assert "_run_paper_journal" in src
    assert "paper_journal_task" in src
    assert '"paper_journal"' in src
