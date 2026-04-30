from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from services.ginarea_api.client import GinAreaClient


@pytest.fixture
def mock_client() -> GinAreaClient:
    return GinAreaClient(token="TEST_BEARER_TOKEN", auth=None, rate_limit_min_interval=0.0)


@pytest.fixture
def sample_default_grid_params() -> dict[str, Any]:
    return {
        "gs": 0.5,
        "gsr": 1.2,
        "maxOp": 12,
        "side": 2,
        "p": True,
        "cf": 0.04,
        "hedge": False,
        "leverage": 3,
        "ul": None,
        "dsblin": False,
        "dsblinbtr": False,
        "dsblinbap": False,
        "obap": True,
        "ris": False,
        "slt": True,
        "tsl": 4.5,
        "lsl": 2.5,
        "ttp": 1.8,
        "ttpinc": 0.2,
        "border": {"bottom": 72000.0, "top": 82000.0},
        "gap": {"isg": 0.5, "tog": 1.0, "minS": 0.3, "maxS": 1.5},
        "q": {"minQ": 10.0, "maxQ": 100.0, "qr": 1.1},
        "tr": {"mdTr": 0.2, "minToTr": 60, "tr": 0.4},
        "slp": {"m": 1, "tp": 0.8, "pp": 20},
    }


@pytest.fixture
def load_fixture() -> Any:
    fixtures_dir = Path(__file__).resolve().parent / "fixtures"

    def _load(name: str) -> Any:
        return json.loads((fixtures_dir / name).read_text(encoding="utf-8"))

    return _load
