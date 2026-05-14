"""Tests for bot_registry resolver + migration script."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from services.bot_registry import resolver as res_mod
from services.bot_registry.resolver import (
    UID_RE, resolve_to_uid, get_display, list_bots,
)


@pytest.fixture
def sample_registry(tmp_path):
    p = tmp_path / "bot_registry.json"
    p.write_text(json.dumps({
        "version": "v0.1",
        "bots": {
            "binance:short:btcusdt:001": {
                "ginarea_id": "6399265299",
                "display_name": "🐉GPT🐉% SHORT 1.1%",
                "alias_short": "SHORT_1.1%",
                "platform": "binance",
                "side": "short",
                "symbol": "BTCUSDT",
                "status": "running",
            },
            "binance:long:btcusdt:001": {
                "ginarea_id": "5427983401",
                "display_name": "BTC-LONG-B",
                "alias_short": None,
                "platform": "binance",
                "side": "long",
                "symbol": "BTCUSDT",
                "status": "running",
            },
            "binance:long:btcusdt:002": {
                "ginarea_id": "5312167170",
                "display_name": "BTC-LONG-C",
                "alias_short": None,
                "platform": "binance",
                "side": "long",
                "symbol": "BTCUSDT",
                "status": "running",
            },
        },
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    res_mod._invalidate_cache()
    yield p
    res_mod._invalidate_cache()


# ── UID format ────────────────────────────────────────────────────────────────

def test_uid_format_matches(sample_registry):
    reg = json.loads(sample_registry.read_text(encoding="utf-8"))
    for uid in reg["bots"]:
        assert UID_RE.match(uid), f"Bad UID: {uid}"


def test_uid_format_rejects_bad():
    assert UID_RE.match("binance:short:btcusdt:001")
    assert not UID_RE.match("binance:short:btcusdt:1")    # not 3 digits
    assert not UID_RE.match("binance:bullish:btcusdt:001")  # bad side
    assert not UID_RE.match("Binance:short:btcusdt:001")  # uppercase platform


# ── resolve_to_uid ────────────────────────────────────────────────────────────

def test_resolve_by_ginarea_id(sample_registry):
    assert resolve_to_uid("6399265299", path=sample_registry) == "binance:short:btcusdt:001"


def test_resolve_by_ginarea_id_with_dot_zero(sample_registry):
    """GinArea sometimes emits IDs as floats — should still match."""
    assert resolve_to_uid("6399265299.0", path=sample_registry) == "binance:short:btcusdt:001"


def test_resolve_by_alias(sample_registry):
    assert resolve_to_uid("SHORT_1.1%", path=sample_registry) == "binance:short:btcusdt:001"


def test_resolve_by_display_name(sample_registry):
    assert resolve_to_uid("🐉GPT🐉% SHORT 1.1%", path=sample_registry) == "binance:short:btcusdt:001"


def test_resolve_unknown_returns_none(sample_registry):
    assert resolve_to_uid("nonexistent_bot", path=sample_registry) is None


def test_resolve_uid_passthrough(sample_registry):
    """If you pass a UID directly, it's returned unchanged."""
    assert resolve_to_uid("binance:long:btcusdt:001", path=sample_registry) == "binance:long:btcusdt:001"


def test_resolve_empty_returns_none(sample_registry):
    assert resolve_to_uid("", path=sample_registry) is None
    assert resolve_to_uid(None, path=sample_registry) is None


# ── get_display ───────────────────────────────────────────────────────────────

def test_get_display_returns_alias_when_present(sample_registry):
    assert get_display("binance:short:btcusdt:001", path=sample_registry) == "SHORT_1.1%"


def test_get_display_falls_back_to_display_name(sample_registry):
    assert get_display("binance:long:btcusdt:001", path=sample_registry) == "BTC-LONG-B"


def test_get_display_falls_back_to_uid_for_unknown(sample_registry):
    assert get_display("binance:short:btcusdt:999", path=sample_registry) == "binance:short:btcusdt:999"


# ── list_bots ─────────────────────────────────────────────────────────────────

def test_list_bots_unfiltered(sample_registry):
    bots = list_bots(path=sample_registry)
    assert len(bots) == 3
    assert all("bot_uid" in b for b in bots)


def test_list_bots_by_side(sample_registry):
    longs = list_bots(filter_side="long", path=sample_registry)
    assert len(longs) == 2
    shorts = list_bots(filter_side="short", path=sample_registry)
    assert len(shorts) == 1


# ── Bijection: ginarea_id ↔ uid ──────────────────────────────────────────────

def test_ginarea_id_uid_bijective(sample_registry):
    reg = json.loads(sample_registry.read_text(encoding="utf-8"))
    seen_gids = set()
    for uid, info in reg["bots"].items():
        gid = info["ginarea_id"]
        assert gid not in seen_gids, f"Duplicate ginarea_id {gid}"
        seen_gids.add(gid)
        # round-trip
        assert resolve_to_uid(gid, path=sample_registry) == uid


# ── Aliases can collide (same alias on two bots — uid still resolves correctly) ──

def test_collide_alias_resolves_to_first_match(tmp_path):
    """Two bots sharing alias_short — resolve_to_uid returns the first found."""
    p = tmp_path / "reg.json"
    p.write_text(json.dumps({
        "bots": {
            "binance:short:btcusdt:001": {"ginarea_id": "111", "alias_short": "DUP", "display_name": "A"},
            "binance:short:btcusdt:002": {"ginarea_id": "222", "alias_short": "DUP", "display_name": "B"},
        },
    }), encoding="utf-8")
    res_mod._invalidate_cache()
    # Should still resolve to *some* UID (not None)
    uid = resolve_to_uid("DUP", path=p)
    assert uid in ("binance:short:btcusdt:001", "binance:short:btcusdt:002")
    # GinArea ID disambiguates
    assert resolve_to_uid("111", path=p) == "binance:short:btcusdt:001"
    assert resolve_to_uid("222", path=p) == "binance:short:btcusdt:002"
    res_mod._invalidate_cache()


# ── Migration script idempotency ─────────────────────────────────────────────

def test_migration_build_proposed_idempotent(tmp_path, monkeypatch):
    """build_proposed_registry called twice with identical inputs → same UIDs."""
    import scripts.migrate_bot_ids as mig

    fake_csv = tmp_path / "snapshots.csv"
    fake_csv.write_text(
        "ts_utc,bot_id,bot_name,alias,status\n"
        "2026-05-04T15:39:11+00:00,5427983401,BTC-LONG-B,,2\n"
        "2026-05-04T15:39:11+00:00,6399265299,SHORT 1.1%,SHORT_1.1%,2\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(mig, "SNAPSHOTS_PATH", fake_csv)

    first = mig.build_proposed_registry(None)
    second = mig.build_proposed_registry(first)
    # UIDs preserved
    assert set(first["bots"].keys()) == set(second["bots"].keys())


def test_migration_appends_new_bot(tmp_path, monkeypatch):
    import scripts.migrate_bot_ids as mig

    fake_csv = tmp_path / "snapshots.csv"
    fake_csv.write_text(
        "ts_utc,bot_id,bot_name,alias,status\n"
        "2026-05-04T15:39:11+00:00,5427983401,BTC-LONG-B,,2\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(mig, "SNAPSHOTS_PATH", fake_csv)

    first = mig.build_proposed_registry(None)
    assert len(first["bots"]) == 1

    # Append a new bot
    fake_csv.write_text(
        "ts_utc,bot_id,bot_name,alias,status\n"
        "2026-05-04T15:39:11+00:00,5427983401,BTC-LONG-B,,2\n"
        "2026-05-04T15:40:11+00:00,9999999999,BTC-NEW,,2\n",
        encoding="utf-8",
    )
    second = mig.build_proposed_registry(first)
    assert len(second["bots"]) == 2
    # Original UID preserved
    assert "binance:long:btcusdt:001" in second["bots"]
    # New bot got next seq
    assert "binance:long:btcusdt:002" in second["bots"]


def test_migration_infers_side():
    import scripts.migrate_bot_ids as mig
    assert mig._infer_side("BTC SHORT 1%") == "short"
    assert mig._infer_side("ЛОНГ БТС") == "long"
    assert mig._infer_side("spot btc Новый") == "spot"
    assert mig._infer_side("🐉GPT🐉TEST 1") == "test"


def test_migration_infers_xrp_symbol():
    import scripts.migrate_bot_ids as mig
    assert mig._infer_symbol("XRP_ЛОНГ 2.5") == "xrpusdt"
    assert mig._infer_symbol("BTC-LONG-B") == "btcusdt"
