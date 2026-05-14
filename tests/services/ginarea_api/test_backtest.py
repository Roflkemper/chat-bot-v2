from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from services.ginarea_api.backtest import BacktestAPI, _to_iso
from services.ginarea_api.client import GinAreaClient
from services.ginarea_api.exceptions import (
    GinAreaAPIError,
    GinAreaProductionBotGuardError,
    GinAreaTestFailedError,
    GinAreaTestTimeoutError,
)
from services.ginarea_api.models import BotStatus


def test_to_iso_naive_datetime_treated_as_utc():
    assert _to_iso(datetime(2026, 4, 30, 12, 0, 0)) == "2026-04-30T12:00:00Z"


def test_to_iso_aware_datetime_converted_to_utc():
    aware = datetime(2026, 4, 30, 14, 0, 0, tzinfo=timezone(timedelta(hours=2)))
    assert _to_iso(aware) == "2026-04-30T12:00:00Z"


def test_to_iso_format_ends_with_Z():
    assert _to_iso(datetime(2026, 4, 30, 12, 0, 0, tzinfo=timezone.utc)).endswith("Z")


def test_create_test_payload_correct_format(httpx_mock, monkeypatch, load_fixture, mock_client):
    monkeypatch.setattr("services.ginarea_api.bots._load_production_bot_ids", lambda: frozenset())
    httpx_mock.add_response(json=load_fixture("test_create_response.json"))
    api = BacktestAPI(mock_client)
    api.create_test(6161205316, datetime(2026, 4, 1, 0, 0), datetime(2026, 4, 10, 0, 0))
    request = httpx_mock.get_requests()[0]
    assert request.read().decode() == '{"dateFrom":"2026-04-01T00:00:00Z","dateTo":"2026-04-10T00:00:00Z"}'


def test_create_test_blocks_on_production_bot_id(monkeypatch, mock_client):
    monkeypatch.setattr("services.ginarea_api.bots._load_production_bot_ids", lambda: frozenset({6161205316}))
    with pytest.raises(GinAreaProductionBotGuardError):
        BacktestAPI(mock_client).create_test(6161205316, datetime.now(), datetime.now())


def test_create_test_returns_test_with_status_created(httpx_mock, monkeypatch, load_fixture, mock_client):
    monkeypatch.setattr("services.ginarea_api.bots._load_production_bot_ids", lambda: frozenset())
    httpx_mock.add_response(json=load_fixture("test_create_response.json"))
    test = BacktestAPI(mock_client).create_test(
        6161205316,
        datetime(2026, 4, 1, tzinfo=timezone.utc),
        datetime(2026, 4, 10, tzinfo=timezone.utc),
    )
    assert test.status == BotStatus.CREATED


def test_list_tests_parses_array(httpx_mock, load_fixture, mock_client):
    httpx_mock.add_response(json=load_fixture("tests_list_active.json"))
    tests = BacktestAPI(mock_client).list_tests(6161205316)
    assert len(tests) == 2


def test_list_tests_with_custom_interval_max_count(httpx_mock, load_fixture, mock_client):
    httpx_mock.add_response(json=load_fixture("tests_list_active.json"))
    BacktestAPI(mock_client).list_tests(6161205316, interval="30m", max_count=10)
    request = httpx_mock.get_requests()[0]
    assert request.url.params["interval"] == "30m"
    assert request.url.params["maxCount"] == "10"


def test_get_test_finds_by_id(httpx_mock, load_fixture, mock_client):
    httpx_mock.add_response(json=load_fixture("tests_list_active.json"))
    test = BacktestAPI(mock_client).get_test(6161205316, 9001)
    assert test.id == 9001


def test_get_test_not_found_raises(httpx_mock, load_fixture, mock_client):
    httpx_mock.add_response(json=load_fixture("tests_list_active.json"))
    with pytest.raises(GinAreaAPIError):
        BacktestAPI(mock_client).get_test(6161205316, 9999)


def test_wait_for_finished_returns_immediately_if_already_finished(httpx_mock, load_fixture, mock_client):
    httpx_mock.add_response(json=load_fixture("tests_list_finished.json"))
    test = BacktestAPI(mock_client).wait_for_finished(6161205316, 9002, poll_interval=0.0, timeout=1.0)
    assert test.status == BotStatus.FINISHED


def test_wait_for_finished_polls_until_finished(monkeypatch, mock_client):
    api = BacktestAPI(mock_client)
    sequence = [
        BotStatus.STARTING,
        BotStatus.ACTIVE,
        BotStatus.ACTIVE,
        BotStatus.FINISHED,
    ]
    calls = {"idx": 0}

    def _get_test(bot_id: int, test_id: int):
        status = sequence[calls["idx"]]
        calls["idx"] += 1
        from services.ginarea_api.models import Test, DefaultGridParams  # local import for test helper
        return Test(
            id=test_id,
            botId=bot_id,
            accountId=1,
            strategyId=1,
            exchangeId=1,
            exchangeMarketIds="BTCUSDT",
            status=status,
            params=DefaultGridParams(),
            dateFrom=datetime(2026, 4, 1, tzinfo=timezone.utc),
            dateTo=datetime(2026, 4, 10, tzinfo=timezone.utc),
            errorCode=None,
            createdAt=datetime(2026, 4, 1, tzinfo=timezone.utc),
            updatedAt=datetime(2026, 4, 1, tzinfo=timezone.utc),
            startedAt=None,
            stoppedAt=None,
            stat=None,
            statHistory=[],
        )

    monkeypatch.setattr(api, "get_test", _get_test)
    monkeypatch.setattr("services.ginarea_api.backtest.time.sleep", lambda seconds: None)
    test = api.wait_for_finished(6161205316, 9001, poll_interval=0.1, timeout=2.0)
    assert test.status == BotStatus.FINISHED


def test_wait_for_finished_raises_ginarea_test_failed_error_on_failed(monkeypatch, mock_client):
    api = BacktestAPI(mock_client)
    from services.ginarea_api.models import Test, DefaultGridParams
    monkeypatch.setattr(
        api,
        "get_test",
        lambda bot_id, test_id: Test(
            id=test_id,
            botId=bot_id,
            accountId=1,
            strategyId=1,
            exchangeId=1,
            exchangeMarketIds="BTCUSDT",
            status=BotStatus.FAILED,
            params=DefaultGridParams(),
            dateFrom=datetime(2026, 4, 1, tzinfo=timezone.utc),
            dateTo=datetime(2026, 4, 10, tzinfo=timezone.utc),
            errorCode=42,
            createdAt=datetime(2026, 4, 1, tzinfo=timezone.utc),
            updatedAt=datetime(2026, 4, 1, tzinfo=timezone.utc),
            startedAt=None,
            stoppedAt=None,
            stat=None,
            statHistory=[],
        ),
    )
    with pytest.raises(GinAreaTestFailedError):
        api.wait_for_finished(6161205316, 9001, poll_interval=0.0, timeout=1.0)


def test_wait_for_finished_raises_ginarea_test_timeout_error_on_timeout(monkeypatch, mock_client):
    api = BacktestAPI(mock_client)
    from services.ginarea_api.models import Test, DefaultGridParams
    monkeypatch.setattr(
        api,
        "get_test",
        lambda bot_id, test_id: Test(
            id=test_id,
            botId=bot_id,
            accountId=1,
            strategyId=1,
            exchangeId=1,
            exchangeMarketIds="BTCUSDT",
            status=BotStatus.ACTIVE,
            params=DefaultGridParams(),
            dateFrom=datetime(2026, 4, 1, tzinfo=timezone.utc),
            dateTo=datetime(2026, 4, 10, tzinfo=timezone.utc),
            errorCode=None,
            createdAt=datetime(2026, 4, 1, tzinfo=timezone.utc),
            updatedAt=datetime(2026, 4, 1, tzinfo=timezone.utc),
            startedAt=None,
            stoppedAt=None,
            stat=None,
            statHistory=[],
        ),
    )
    monotonic_values = iter([0.0, 2.0])
    monkeypatch.setattr("services.ginarea_api.backtest.time.monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr("services.ginarea_api.backtest.time.sleep", lambda seconds: None)
    with pytest.raises(GinAreaTestTimeoutError):
        api.wait_for_finished(6161205316, 9001, poll_interval=0.1, timeout=1.0)


def test_wait_for_finished_polls_at_specified_interval(monkeypatch, mock_client):
    api = BacktestAPI(mock_client)
    sequence = [BotStatus.ACTIVE, BotStatus.FINISHED]
    calls = {"idx": 0}
    sleeps: list[float] = []
    from services.ginarea_api.models import Test, DefaultGridParams

    def _get_test(bot_id: int, test_id: int):
        status = sequence[calls["idx"]]
        calls["idx"] += 1
        return Test(
            id=test_id,
            botId=bot_id,
            accountId=1,
            strategyId=1,
            exchangeId=1,
            exchangeMarketIds="BTCUSDT",
            status=status,
            params=DefaultGridParams(),
            dateFrom=datetime(2026, 4, 1, tzinfo=timezone.utc),
            dateTo=datetime(2026, 4, 10, tzinfo=timezone.utc),
            errorCode=None,
            createdAt=datetime(2026, 4, 1, tzinfo=timezone.utc),
            updatedAt=datetime(2026, 4, 1, tzinfo=timezone.utc),
            startedAt=None,
            stoppedAt=None,
            stat=None,
            statHistory=[],
        )

    monkeypatch.setattr(api, "get_test", _get_test)
    monkeypatch.setattr("services.ginarea_api.backtest.time.sleep", lambda seconds: sleeps.append(seconds))
    api.wait_for_finished(6161205316, 9001, poll_interval=2.5, timeout=10.0)
    assert sleeps == [2.5]


def test_run_test_full_flow_create_plus_poll(monkeypatch, mock_client):
    api = BacktestAPI(mock_client)
    from services.ginarea_api.models import Test, DefaultGridParams
    created = Test(
        id=9001,
        botId=6161205316,
        accountId=1,
        strategyId=1,
        exchangeId=1,
        exchangeMarketIds="BTCUSDT",
        status=BotStatus.CREATED,
        params=DefaultGridParams(),
        dateFrom=datetime(2026, 4, 1, tzinfo=timezone.utc),
        dateTo=datetime(2026, 4, 10, tzinfo=timezone.utc),
        errorCode=None,
        createdAt=datetime(2026, 4, 1, tzinfo=timezone.utc),
        updatedAt=datetime(2026, 4, 1, tzinfo=timezone.utc),
        startedAt=None,
        stoppedAt=None,
        stat=None,
        statHistory=[],
    )
    finished = Test(
        id=9001,
        botId=6161205316,
        accountId=1,
        strategyId=1,
        exchangeId=1,
        exchangeMarketIds="BTCUSDT",
        status=BotStatus.FINISHED,
        params=DefaultGridParams(),
        dateFrom=datetime(2026, 4, 1, tzinfo=timezone.utc),
        dateTo=datetime(2026, 4, 10, tzinfo=timezone.utc),
        errorCode=None,
        createdAt=datetime(2026, 4, 1, tzinfo=timezone.utc),
        updatedAt=datetime(2026, 4, 1, tzinfo=timezone.utc),
        startedAt=None,
        stoppedAt=None,
        stat=None,
        statHistory=[],
    )
    monkeypatch.setattr(api, "create_test", lambda bot_id, date_from, date_to: created)
    monkeypatch.setattr(api, "wait_for_finished", lambda bot_id, test_id, **kwargs: finished)
    assert api.run_test(6161205316, datetime(2026, 4, 1), datetime(2026, 4, 10)) == finished
