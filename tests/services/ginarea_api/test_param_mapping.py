from __future__ import annotations

from services.ginarea_api.models import DefaultGridParams
from services.ginarea_api.param_mapping import API_TO_UI, UI_TO_API, get_param, set_param


def test_ui_to_api_keys_match_dataclass_fields(sample_default_grid_params):
    dataclass_keys = set(DefaultGridParams.from_dict(sample_default_grid_params).to_dict().keys())
    for api_path in UI_TO_API.values():
        assert api_path.split(".")[0] in dataclass_keys


def test_get_param_returns_none_for_missing_path(sample_default_grid_params):
    assert get_param({"q": {}}, "order_size_max") is None


def test_get_param_dotted_path_navigation(sample_default_grid_params):
    assert get_param(sample_default_grid_params, "order_size_min") == 10.0
    assert get_param(sample_default_grid_params, "border_top") == 82000.0


def test_set_param_immutable_returns_new_dict(sample_default_grid_params):
    updated = set_param(sample_default_grid_params, "grid_step", 0.75)
    assert updated is not sample_default_grid_params
    assert sample_default_grid_params["gs"] == 0.5
    assert updated["gs"] == 0.75


def test_set_param_creates_nested_keys():
    updated = set_param({}, "order_size_min", 11.0)
    assert updated["q"]["minQ"] == 11.0


def test_api_to_ui_inverse_of_ui_to_api():
    assert API_TO_UI == {value: key for key, value in UI_TO_API.items()}
