from __future__ import annotations

import asyncio

from services.decision_log.auto_capture import decision_log_loop


def test_loop_handles_iteration_exception_continues() -> None:
    stop_event = asyncio.Event()
    calls = {"detector": 0, "outcome": 0}

    def detector() -> None:
        calls["detector"] += 1
        if calls["detector"] == 1:
            raise RuntimeError("boom")
        stop_event.set()

    def outcome() -> None:
        calls["outcome"] += 1

    asyncio.run(decision_log_loop(stop_event, detector_runner=detector, outcome_runner=outcome, interval_sec=0.01))
    assert calls["detector"] >= 2


def test_loop_respects_stop_event() -> None:
    stop_event = asyncio.Event()
    stop_event.set()
    calls = {"detector": 0}
    asyncio.run(
        decision_log_loop(
            stop_event,
            detector_runner=lambda: calls.__setitem__("detector", 1),
            outcome_runner=lambda: None,
            interval_sec=0.01,
        )
    )
    assert calls["detector"] == 0


def test_loop_sleeps_300s_between_iterations(monkeypatch) -> None:
    stop_event = asyncio.Event()
    sleeps: list[float] = []
    original_wait_for = asyncio.wait_for

    async def fake_wait_for(awaitable, timeout):
        sleeps.append(timeout)
        stop_event.set()
        return await original_wait_for(awaitable, timeout=0)

    monkeypatch.setattr("services.decision_log.auto_capture.asyncio.wait_for", fake_wait_for)
    asyncio.run(decision_log_loop(stop_event, detector_runner=lambda: None, outcome_runner=lambda: None, interval_sec=300.0))
    assert sleeps == [300.0]


def test_first_iteration_runs_before_stop_check() -> None:
    stop_event = asyncio.Event()
    calls = {"detector": 0}

    def detector() -> None:
        calls["detector"] += 1
        stop_event.set()

    asyncio.run(decision_log_loop(stop_event, detector_runner=detector, outcome_runner=lambda: None, interval_sec=0.01))
    assert calls["detector"] == 1
