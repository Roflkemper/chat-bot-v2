from core.orchestrator.i18n_ru import (
    tr, REGIME_RU, ACTION_RU, MODIFIER_RU, CATEGORY_RU, BOT_STATE_RU,
)
from core.orchestrator.visuals import bias_scale, progress_bar, regime_header


def test_i18n_known_translations():
    assert tr("RANGE", REGIME_RU) == "БОКОВИК"
    assert tr("RUN", ACTION_RU) == "РАБОТАЕТ"
    assert tr("btc_short", CATEGORY_RU) == "BTC ШОРТ"


def test_i18n_unknown_key_fallback():
    assert tr("UNKNOWN_REGIME", REGIME_RU) == "UNKNOWN_REGIME"
    assert tr("UNKNOWN", ACTION_RU, default="н/д") == "н/д"


def test_i18n_does_not_raise():
    # Unknown keys must not raise
    for section in [REGIME_RU, ACTION_RU, MODIFIER_RU, CATEGORY_RU, BOT_STATE_RU]:
        tr("DEFINITELY_NOT_IN_DICT", section)


def test_bias_scale_center():
    s = bias_scale(0)
    assert "●" in s
    assert len(s) == 10


def test_bias_scale_extreme_positive():
    s = bias_scale(100)
    # Маркер должен быть справа
    assert s.index("▓") > len(s) // 2


def test_bias_scale_extreme_negative():
    s = bias_scale(-100)
    # Маркер должен быть слева
    assert s.index("▓") < len(s) // 2


def test_progress_bar_full():
    s = progress_bar(100, 100, width=10)
    assert "██████████" in s


def test_progress_bar_warnings():
    s = progress_bar(95, 100, warn_threshold=75, danger_threshold=90)
    assert "🔴" in s
    s = progress_bar(80, 100, warn_threshold=75, danger_threshold=90)
    assert "⚠" in s
    assert "🔴" not in s


def test_regime_header():
    s = regime_header("RANGE", 48, 15)
    assert "БОКОВИК" in s
    assert "12ч" in s
    
    s = regime_header("CASCADE_DOWN", 0)
    assert "только что" in s
