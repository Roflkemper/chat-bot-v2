"""Tests for services.common.humanize."""
from __future__ import annotations

from services.common.humanize import (
    humanize_scenario, humanize_setup_type, humanize_bot,
    SCENARIO_NAMES, SETUP_TYPE_NAMES,
)


def test_humanize_scenario_known():
    assert humanize_scenario("baseline") == "Без вмешательства"
    assert humanize_scenario("combined") == "Защита+Фиксация+Догон"
    assert humanize_scenario("pause_on_drawdown") == "Защита от слива"


def test_humanize_scenario_unknown_returns_code():
    assert humanize_scenario("unknown_code") == "unknown_code"


def test_humanize_setup_type_known():
    assert "Множественная дивергенция" in humanize_setup_type("long_multi_divergence")
    assert "Перебалансировка тренда" in humanize_setup_type("p15_long_open")
    assert "(LONG)" in humanize_setup_type("long_pdl_bounce")
    assert "(SHORT)" in humanize_setup_type("short_pdh_rejection")


def test_humanize_setup_type_unknown_returns_code():
    assert humanize_setup_type("unknown_setup") == "unknown_setup"


def test_humanize_bot_known():
    assert humanize_bot("4524162672") == "TEST_3"
    assert humanize_bot("5188321731") == "ШОРТ-ОБЪЁМ"
    assert humanize_bot("4524162672.0") == "TEST_3"  # float-stringified


def test_humanize_bot_unknown_returns_id():
    assert humanize_bot("99999") == "99999"


def test_all_5_scenarios_named():
    for scen in ("baseline", "pause_on_drawdown", "partial_unload_on_retrace",
                 "trend_chase", "combined"):
        assert scen in SCENARIO_NAMES, f"{scen} нет в глоссарии"


def test_all_19_detectors_named():
    """В DETECTOR_REGISTRY 19 trade-emitting детекторов — все должны быть переведены."""
    expected = [
        "long_pdl_bounce", "long_dump_reversal", "long_oversold_reclaim",
        "long_liq_magnet", "short_pdh_rejection", "short_rally_fade",
        "short_overbought_fade", "short_liq_magnet", "long_double_bottom",
        "short_double_top", "long_multi_divergence", "long_div_bos_confirmed",
        "long_div_bos_15m", "short_div_bos_15m", "long_multi_asset_confluence",
        "long_multi_asset_confluence_v2", "long_mega_dump_bounce",
        "long_rsi_momentum_ga", "short_mfi_multi_ga",
    ]
    for st in expected:
        assert st in SETUP_TYPE_NAMES, f"{st} нет в глоссарии"


def test_all_p15_stages_named():
    for d in ("long", "short"):
        for stage in ("open", "harvest", "reentry", "close"):
            key = f"p15_{d}_{stage}"
            assert key in SETUP_TYPE_NAMES, f"{key} нет в глоссарии"
