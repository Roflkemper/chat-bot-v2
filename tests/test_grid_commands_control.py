from __future__ import annotations

from datetime import date, datetime, timezone

from core.orchestrator.calibration_log import CalibrationLog
from handlers.command_actions import CommandActionContext, CommandActions
from core.orchestrator.killswitch import KillswitchStore
from core.orchestrator.portfolio_state import PortfolioStore
from core.orchestrator.regime_classifier import RegimeStateStore


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()


def _ctx(command: str) -> CommandActionContext:
    return CommandActionContext(command=command, timeframe="1h", snapshot_loader=lambda tf: None)


def _fake_snapshot(primary="RANGE", modifiers=None):
    return {"regime": {"primary": primary, "modifiers": modifiers or [], "bias_score": 21, "metrics": {"adx_1h": 18}}}


def test_pause_sets_all_bots_to_paused_manual(tmp_path, monkeypatch):
    store = PortfolioStore(str(tmp_path / "state" / "grid_portfolio.json"))
    monkeypatch.setattr(PortfolioStore, "_instance", store)
    payload = CommandActions(_ctx("/pause btc_short")).pause()
    assert "РУЧНАЯ ПАУЗА" in payload.text
    assert store.get_bot("btc_short_l1").state == "PAUSED_MANUAL"


def test_pause_missing_arg():
    payload = CommandActions(_ctx("/pause")).pause()
    assert "Использование" in payload.text


def test_pause_invalid_category(tmp_path, monkeypatch):
    store = PortfolioStore(str(tmp_path / "state" / "grid_portfolio.json"))
    monkeypatch.setattr(PortfolioStore, "_instance", store)
    payload = CommandActions(_ctx("/pause bad")).pause()
    assert "не найдена" in payload.text


def test_pause_already_paused_returns_info(tmp_path, monkeypatch):
    store = PortfolioStore(str(tmp_path / "state" / "grid_portfolio.json"))
    monkeypatch.setattr(PortfolioStore, "_instance", store)
    CommandActions(_ctx("/pause btc_short")).pause()
    payload = CommandActions(_ctx("/pause btc_short")).pause()
    assert "уже на ручной паузе" in payload.text


def test_resume_sets_bots_to_ready(tmp_path, monkeypatch):
    store = PortfolioStore(str(tmp_path / "state" / "grid_portfolio.json"))
    monkeypatch.setattr(PortfolioStore, "_instance", store)
    CommandActions(_ctx("/pause btc_short")).pause()
    payload = CommandActions(_ctx("/resume btc_short")).resume()
    assert "ВОЗОБНОВЛЕНО" in payload.text
    assert store.get_bot("btc_short_l1").state == "ACTIVE"


def test_resume_missing_arg():
    payload = CommandActions(_ctx("/resume")).resume()
    assert "Использование" in payload.text


def test_resume_when_not_paused_returns_info(tmp_path, monkeypatch):
    store = PortfolioStore(str(tmp_path / "state" / "grid_portfolio.json"))
    monkeypatch.setattr(PortfolioStore, "_instance", store)
    payload = CommandActions(_ctx("/resume btc_short")).resume()
    assert "нет ботов на ручной паузе" in payload.text


def test_bot_add_creates_new_bot(tmp_path, monkeypatch):
    store = PortfolioStore(str(tmp_path / "state" / "grid_portfolio.json"))
    monkeypatch.setattr(PortfolioStore, "_instance", store)
    payload = CommandActions(_ctx("/bot_add btc_long_a btc_long GRID_L1")).bot_add()
    assert "БОТ ДОБАВЛЕН" in payload.text
    assert store.get_bot("btc_long_a") is not None


def test_bot_add_duplicate_key_fails(tmp_path, monkeypatch):
    store = PortfolioStore(str(tmp_path / "state" / "grid_portfolio.json"))
    monkeypatch.setattr(PortfolioStore, "_instance", store)
    payload = CommandActions(_ctx("/bot_add btc_short_l1 btc_short GRID_L1")).bot_add()
    assert "уже существует" in payload.text


def test_bot_add_invalid_strategy_type(tmp_path, monkeypatch):
    store = PortfolioStore(str(tmp_path / "state" / "grid_portfolio.json"))
    monkeypatch.setattr(PortfolioStore, "_instance", store)
    payload = CommandActions(_ctx("/bot_add x1 btc_short BAD")).bot_add()
    assert "Недопустимый" in payload.text


def test_bot_add_invalid_category(tmp_path, monkeypatch):
    store = PortfolioStore(str(tmp_path / "state" / "grid_portfolio.json"))
    monkeypatch.setattr(PortfolioStore, "_instance", store)
    payload = CommandActions(_ctx("/bot_add x1 bad GRID_L1")).bot_add()
    assert "не найдена" in payload.text


def test_bot_add_missing_args():
    payload = CommandActions(_ctx("/bot_add x1")).bot_add()
    assert "Использование" in payload.text


def test_bot_remove_archives_bot(tmp_path, monkeypatch):
    store = PortfolioStore(str(tmp_path / "state" / "grid_portfolio.json"))
    monkeypatch.setattr(PortfolioStore, "_instance", store)
    payload = CommandActions(_ctx("/bot_remove btc_short_l1")).bot_remove()
    assert "АРХИВИРОВАН" in payload.text
    assert store.get_bot("btc_short_l1").state == "ARCHIVED"


def test_bot_remove_missing_key(tmp_path, monkeypatch):
    store = PortfolioStore(str(tmp_path / "state" / "grid_portfolio.json"))
    monkeypatch.setattr(PortfolioStore, "_instance", store)
    payload = CommandActions(_ctx("/bot_remove missing")).bot_remove()
    assert "не найден" in payload.text


def test_blackout_sets_expiry(tmp_path, monkeypatch):
    store = RegimeStateStore(str(tmp_path / "state" / "regime_state.json"))
    monkeypatch.setattr("core.orchestrator.regime_classifier.RegimeStateStore", lambda: store)
    payload = CommandActions(_ctx("/blackout 2")).blackout()
    assert "БЛЭКАУТ ВКЛЮЧЁН" in payload.text
    assert store.get_blackout() is not None


def test_blackout_zero_clears(tmp_path, monkeypatch):
    store = RegimeStateStore(str(tmp_path / "state" / "regime_state.json"))
    monkeypatch.setattr("core.orchestrator.regime_classifier.RegimeStateStore", lambda: store)
    CommandActions(_ctx("/blackout 2")).blackout()
    payload = CommandActions(_ctx("/blackout 0")).blackout()
    assert "СБРОШЕН" in payload.text
    assert store.get_blackout() is None


def test_blackout_invalid_number():
    payload = CommandActions(_ctx("/blackout zz")).blackout()
    assert "Некорректное" in payload.text


def test_apply_reports_no_changes_when_aligned(tmp_path, monkeypatch):
    store = PortfolioStore(str(tmp_path / "state" / "grid_portfolio.json"))
    monkeypatch.setattr(PortfolioStore, "_instance", store)
    monkeypatch.setattr("core.pipeline.build_full_snapshot", lambda symbol="BTCUSDT": _fake_snapshot("RANGE"))
    payload = CommandActions(_ctx("/apply")).apply()
    assert "Изменено категорий: 0" in payload.text


def test_apply_reports_changes_list(tmp_path, monkeypatch):
    store = PortfolioStore(str(tmp_path / "state" / "grid_portfolio.json"))
    monkeypatch.setattr(PortfolioStore, "_instance", store)
    monkeypatch.setattr("core.pipeline.build_full_snapshot", lambda symbol="BTCUSDT": _fake_snapshot("TREND_DOWN"))
    payload = CommandActions(_ctx("/apply")).apply()
    assert "Изменено категорий:" in payload.text
    assert "BTC ЛОНГ" in payload.text


def test_apply_logs_manual_command(tmp_path, monkeypatch):
    store = PortfolioStore(str(tmp_path / "state" / "grid_portfolio.json"))
    monkeypatch.setattr(PortfolioStore, "_instance", store)
    monkeypatch.setattr(CalibrationLog, "_instance", None)
    CalibrationLog.instance(tmp_path / "state" / "calibration")
    monkeypatch.setattr("core.pipeline.build_full_snapshot", lambda symbol="BTCUSDT": _fake_snapshot("RANGE"))
    CommandActions(_ctx("/apply")).apply()
    events = CalibrationLog.instance().read_events(_utc_today())
    assert any(event["event_type"] == "MANUAL_COMMAND" for event in events)


def test_daily_report_returns_summary(tmp_path, monkeypatch):
    monkeypatch.setattr(CalibrationLog, "_instance", None)
    log = CalibrationLog.instance(tmp_path / "state" / "calibration")
    log.log_manual_command("/apply", None, "APPLY", "RANGE", [])
    command = "/daily_report"
    if _utc_today() != date.today():
        command = "/daily_report yesterday"
    payload = CommandActions(_ctx(command)).daily_report()
    assert "DAILY REPORT" in payload.text
    assert "MANUAL_COMMAND: 1" in payload.text
