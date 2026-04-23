from __future__ import annotations

from datetime import timezone

from core.orchestrator.portfolio_state import Bot, PortfolioStore


def _store(tmp_path):
    return PortfolioStore(str(tmp_path / "state" / "grid_portfolio.json"))


def test_first_run_creates_default_file(tmp_path):
    store = _store(tmp_path)
    path = tmp_path / "state" / "grid_portfolio.json"
    assert not path.exists()
    store.get_snapshot()
    assert path.exists()


def test_default_has_3_btc_categories(tmp_path):
    store = _store(tmp_path)
    snapshot = store.get_snapshot()
    assert set(snapshot.categories) == {"btc_short", "btc_long", "btc_long_l2"}


def test_default_has_btc_short_l1_live_bot(tmp_path):
    store = _store(tmp_path)
    bot = store.get_bot("btc_short_l1")
    assert bot is not None
    assert bot.stage == "LIVE"
    assert bot.state == "ACTIVE"


def test_get_snapshot_returns_all_data(tmp_path):
    store = _store(tmp_path)
    snapshot = store.get_snapshot()
    assert snapshot.mode == "NORMAL"
    assert "btc_short" in snapshot.categories
    assert "btc_short_l1" in snapshot.bots


def test_get_category_existing(tmp_path):
    store = _store(tmp_path)
    category = store.get_category("btc_short")
    assert category is not None
    assert category.label_ru == "BTC ШОРТ"


def test_get_category_missing_returns_none(tmp_path):
    store = _store(tmp_path)
    assert store.get_category("missing") is None


def test_get_bot_existing(tmp_path):
    store = _store(tmp_path)
    bot = store.get_bot("btc_short_l1")
    assert bot is not None
    assert bot.category == "btc_short"


def test_get_bot_missing_returns_none(tmp_path):
    store = _store(tmp_path)
    assert store.get_bot("missing") is None


def test_get_bots_in_category(tmp_path):
    store = _store(tmp_path)
    bots = store.get_bots_in_category("btc_short")
    assert [bot.key for bot in bots] == ["btc_short_l1"]


def test_get_bots_empty_category(tmp_path):
    store = _store(tmp_path)
    bots = store.get_bots_in_category("btc_long")
    assert bots == []


def test_list_categories_returns_three(tmp_path):
    store = _store(tmp_path)
    assert len(store.list_categories()) == 3


def test_list_bots_returns_default_bot(tmp_path):
    store = _store(tmp_path)
    assert [bot.key for bot in store.list_bots()] == ["btc_short_l1"]


def test_set_category_action_updates_bots(tmp_path):
    store = _store(tmp_path)
    assert store.set_category_action("btc_short", "PAUSE", base_reason="RANGE")
    assert store.get_bot("btc_short_l1").state == "PAUSED_BY_REGIME"
    assert store.set_category_action("btc_short", "RUN", base_reason="RANGE")
    assert store.get_bot("btc_short_l1").state == "ACTIVE"


def test_set_category_action_killswitch_sets_bot_state(tmp_path, monkeypatch):
    from core.orchestrator.killswitch import KillswitchStore

    monkeypatch.setattr(KillswitchStore, "_instance", KillswitchStore(tmp_path / "state" / "killswitch_state.json"))
    store = _store(tmp_path)
    assert store.set_category_action("btc_short", "KILLSWITCH", base_reason="Killswitch")
    assert store.get_bot("btc_short_l1").state == "KILLSWITCH"


def test_set_category_action_preserves_manual_paused(tmp_path):
    store = _store(tmp_path)
    assert store.set_bot_state("btc_short_l1", "PAUSED_MANUAL")
    assert store.set_category_action("btc_short", "PAUSE", base_reason="RANGE")
    assert store.get_bot("btc_short_l1").state == "PAUSED_MANUAL"
    assert store.set_category_action("btc_short", "RUN", base_reason="RANGE")
    assert store.get_bot("btc_short_l1").state == "PAUSED_MANUAL"


def test_set_bot_state_one_bot(tmp_path):
    store = _store(tmp_path)
    assert store.set_bot_state("btc_short_l1", "PAUSED_MANUAL")
    assert store.get_bot("btc_short_l1").state == "PAUSED_MANUAL"


def test_add_bot_new(tmp_path):
    store = _store(tmp_path)
    ok = store.add_bot(
        Bot(
            key="btc_long_l1",
            category="btc_long",
            label="BTC LONG L1",
            strategy_type="GRID_L1",
            stage="TEST",
        )
    )
    assert ok is True
    assert store.get_bot("btc_long_l1") is not None


def test_add_bot_duplicate_key_returns_false(tmp_path):
    store = _store(tmp_path)
    ok = store.add_bot(
        Bot(
            key="btc_short_l1",
            category="btc_short",
            label="dup",
            strategy_type="GRID_L1",
            stage="TEST",
        )
    )
    assert ok is False


def test_remove_bot_sets_archived(tmp_path):
    store = _store(tmp_path)
    assert store.remove_bot("btc_short_l1") is True
    bot = store.get_bot("btc_short_l1")
    assert bot is not None
    assert bot.state == "ARCHIVED"
    assert bot.stage == "ARCHIVED"


def test_remove_bot_missing_returns_false(tmp_path):
    store = _store(tmp_path)
    assert store.remove_bot("missing") is False


def test_persistence_save_load_roundtrip(tmp_path):
    store = _store(tmp_path)
    assert store.set_category_action("btc_short", "PAUSE", base_reason="RANGE", modifiers=["WEEKEND_LOW_VOL"])
    store2 = _store(tmp_path)
    category = store2.get_category("btc_short")
    bot = store2.get_bot("btc_short_l1")
    assert category is not None
    assert category.orchestrator_action == "PAUSE"
    assert category.modifiers_active == ["WEEKEND_LOW_VOL"]
    assert bot is not None
    assert bot.state == "PAUSED_BY_REGIME"


def test_singleton_instance(tmp_path, monkeypatch):
    monkeypatch.setattr(PortfolioStore, "_instance", None)
    first = PortfolioStore.instance()
    second = PortfolioStore.instance()
    assert first is second


def test_snapshot_updated_at_is_timezone_aware(tmp_path):
    store = _store(tmp_path)
    assert store.get_snapshot().updated_at.tzinfo == timezone.utc


def test_set_category_action_missing_returns_false(tmp_path):
    store = _store(tmp_path)
    assert store.set_category_action("missing", "PAUSE") is False


def test_set_category_action_blocked_when_killswitch_active(tmp_path, monkeypatch):
    from core.orchestrator.killswitch import KillswitchStore

    monkeypatch.setattr(KillswitchStore, "_instance", KillswitchStore(tmp_path / "state" / "killswitch_state.json"))
    KillswitchStore.instance().trigger("MANUAL", "operator")
    store = _store(tmp_path)
    assert store.set_category_action("btc_short", "RUN") is False


def test_set_bot_state_missing_returns_false(tmp_path):
    store = _store(tmp_path)
    assert store.set_bot_state("missing", "ACTIVE") is False
