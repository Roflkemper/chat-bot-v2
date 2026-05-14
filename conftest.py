"""Root conftest — runs before any test collection.

pytest 9.0+ collects test modules before tests/conftest.py runs, so any
test that imports a service which imports `core.<module>` fails because
the project root is not yet on sys.path. This file fixes that for the
collection phase too.

Background: pytest's `pythonpath = .` setting in pytest.ini handles
runtime imports but NOT collection-phase imports. Without this conftest,
tests/services/decision_log/test_content_dedup.py and other modules that
do `from services.telegram_runtime import ...` fail collection with
`ModuleNotFoundError: No module named 'core.app_logging'`.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
