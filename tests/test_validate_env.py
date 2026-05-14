"""Tests for validate_env script."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def mod():
    spec = importlib.util.spec_from_file_location(
        "validate_env", ROOT / "scripts" / "validate_env.py",
    )
    m = importlib.util.module_from_spec(spec)
    sys.modules["validate_env"] = m
    spec.loader.exec_module(m)
    return m


def test_parse_env_skips_comments_and_blank(mod, tmp_path):
    p = tmp_path / "env.test"
    p.write_text("# comment\n\nFOO=bar\nBAZ=qux\n", encoding="utf-8")
    out = mod._parse_env(p)
    assert out == {"FOO": "bar", "BAZ": "qux"}


def test_parse_env_strips_quotes(mod, tmp_path):
    p = tmp_path / "env.test"
    p.write_text('A="quoted"\nB=\'sq\'\nC=plain\n', encoding="utf-8")
    out = mod._parse_env(p)
    assert out == {"A": "quoted", "B": "sq", "C": "plain"}


def test_parse_env_missing_file(mod, tmp_path):
    assert mod._parse_env(tmp_path / "absent") == {}


def test_known_keys_includes_essentials(mod):
    """Sanity: KNOWN_KEYS covers the critical config surface."""
    must_have = {"BOT_TOKEN", "BITMEX_API_KEY", "DISABLED_DETECTORS",
                 "GC_SHADOW_MODE", "ADVISOR_DEPO_TOTAL"}
    assert must_have <= mod.KNOWN_KEYS
