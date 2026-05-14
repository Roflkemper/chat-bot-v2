from services.managed_grid_sim.intervention_actions import InterventionExecutor
from services.managed_grid_sim.intervention_rules import InterventionDecision
from services.managed_grid_sim.models import InterventionType

from .conftest import FakeBot, FakeCfg, FakeContract, FakeOrder, FakeSide


def _bot() -> FakeBot:
    cfg = FakeCfg("short_main", "short_main", FakeSide("short"), FakeContract("linear"), 1.0, 10, 0.03, 0.21, 0.01, 0.04, 0.01, 0.0, 999999.0, 30, 0.3)
    bot = FakeBot(cfg)
    bot.active_orders = [FakeOrder(qty=2.0, entry_price=100.0)]
    return bot


def test_apply_pause_calls_set_dsblin_true(sample_snapshot):
    bot = _bot()
    event = InterventionExecutor({"short_main": bot}).apply(
        "short_main",
        InterventionDecision(InterventionType.PAUSE_NEW_ENTRIES, "pause"),
        type("Bar", (), {"close": 90.0})(),
        snapshot=sample_snapshot,
    )
    assert bot.is_active is False
    assert event.intervention_type.value == "pause_new_entries"


def test_apply_partial_unload_reduces_position(sample_snapshot):
    bot = _bot()
    InterventionExecutor({"short_main": bot}).apply(
        "short_main",
        InterventionDecision(InterventionType.PARTIAL_UNLOAD, "trim", partial_unload_fraction=0.5),
        type("Bar", (), {"close": 90.0})(),
        snapshot=sample_snapshot,
    )
    assert bot.position_size() == 1.0
    assert len(bot.closed_orders) == 1


def test_apply_activate_booster_creates_new_bot(sample_snapshot):
    bot = _bot()

    def factory(cfg):
        new_cfg = FakeCfg(
            cfg["bot_id"], cfg["alias"], FakeSide(cfg["side"]), FakeContract(cfg["contract_type"]),
            cfg["order_size"], cfg["order_count"], cfg["grid_step_pct"], cfg["target_profit_pct"],
            cfg["min_stop_pct"], cfg["max_stop_pct"], cfg["instop_pct"], cfg["boundaries_lower"],
            cfg["boundaries_upper"], cfg["indicator_period"], cfg["indicator_threshold_pct"]
        )
        return FakeBot(new_cfg)

    bots = {"short_main": bot}
    InterventionExecutor(bots, bot_factory=factory).apply(
        "short_main",
        InterventionDecision(InterventionType.ACTIVATE_BOOSTER, "boost", booster_config={"qty_factor": 2.0, "border_top_offset_pct": 0.5}),
        type("Bar", (), {"close": 100.0})(),
        snapshot=sample_snapshot,
    )
    assert "short_main_booster" in bots
