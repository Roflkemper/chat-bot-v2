"""Tests for liq-cluster score autotune."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from services.pre_cascade_alert.score_autotune import (
    analyze,
    format_report_section,
)


def _write_fires(path: Path, fires: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for e in fires:
            f.write(json.dumps(e) + "\n")


def _write_liqs(path: Path, events: list[tuple[datetime, str, float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["ts_utc,exchange,side,qty,price"]
    for ts, side, qty in events:
        lines.append(f"{ts.isoformat()},test,{side},{qty},80000")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_no_data_returns_insufficient(tmp_path: Path) -> None:
    r = analyze(
        now=datetime(2026, 5, 13, 12, 0, tzinfo=timezone.utc),
        journal=tmp_path / "j.jsonl",
        liq_csv=tmp_path / "l.csv",
    )
    assert r["fires_total"] == 0
    assert r["cascades_total"] == 0
    assert r["recommendation"] == "insufficient_data"


def test_perfect_hit_rate_lower_threshold_suggested(tmp_path: Path) -> None:
    now = datetime(2026, 5, 13, 12, 0, tzinfo=timezone.utc)
    # 6 fires, all followed by cascade within 30 min
    fires = []
    liqs = []
    for i in range(6):
        ts = now - timedelta(days=1, hours=i)
        fires.append({"ts": ts.isoformat(), "side": "long", "qty_btc": 0.5})
        # add cascade 10 min after (6 BTC in single event)
        liqs.append((ts + timedelta(minutes=10), "long", 6.0))
    _write_fires(tmp_path / "j.jsonl", fires)
    _write_liqs(tmp_path / "l.csv", liqs)
    r = analyze(now=now, journal=tmp_path / "j.jsonl", liq_csv=tmp_path / "l.csv")
    assert r["fires_total"] == 6
    assert r["hits"] == 6
    assert r["hit_rate"] == 1.0
    assert r["recall"] == 1.0
    assert r["recommendation"] == "lower_threshold"


def test_low_hit_rate_raise_threshold_suggested(tmp_path: Path) -> None:
    now = datetime(2026, 5, 13, 12, 0, tzinfo=timezone.utc)
    # 10 fires, 1 hit
    fires = []
    liqs = []
    for i in range(10):
        ts = now - timedelta(days=1, hours=i)
        fires.append({"ts": ts.isoformat(), "side": "long", "qty_btc": 0.5})
    # One cascade after first fire
    first_ts = datetime.fromisoformat(fires[0]["ts"])
    liqs.append((first_ts + timedelta(minutes=10), "long", 6.0))
    _write_fires(tmp_path / "j.jsonl", fires)
    _write_liqs(tmp_path / "l.csv", liqs)
    r = analyze(now=now, journal=tmp_path / "j.jsonl", liq_csv=tmp_path / "l.csv")
    assert r["fires_total"] == 10
    assert r["hits"] == 1
    assert r["hit_rate"] == 0.1
    assert r["recommendation"] == "raise_threshold"


def test_keep_current_in_normal_range(tmp_path: Path) -> None:
    now = datetime(2026, 5, 13, 12, 0, tzinfo=timezone.utc)
    # 10 fires, 3 hits → 30% hit rate; recall ~ 60%
    fires = []
    liqs = []
    for i in range(10):
        ts = now - timedelta(days=1, hours=i)
        fires.append({"ts": ts.isoformat(), "side": "long", "qty_btc": 0.5})
    # 3 cascades after first 3 fires + 2 unmatched cascades
    for i in range(3):
        ts = datetime.fromisoformat(fires[i]["ts"])
        liqs.append((ts + timedelta(minutes=10), "long", 6.0))
    # 2 cascades NOT preceded by fire (in completely different times)
    liqs.append((now - timedelta(days=2), "long", 6.0))
    liqs.append((now - timedelta(days=3), "long", 6.0))
    _write_fires(tmp_path / "j.jsonl", fires)
    _write_liqs(tmp_path / "l.csv", liqs)
    r = analyze(now=now, journal=tmp_path / "j.jsonl", liq_csv=tmp_path / "l.csv")
    assert 0.20 <= r["hit_rate"] <= 0.40
    # hit_rate 30%, recall = 3/5 = 60% → keep_current
    assert r["recommendation"] in ("keep_current", "lower_threshold_for_recall")


def test_per_side_breakdown(tmp_path: Path) -> None:
    now = datetime(2026, 5, 13, 12, 0, tzinfo=timezone.utc)
    fires = [
        {"ts": (now - timedelta(hours=h)).isoformat(), "side": "long", "qty_btc": 0.5}
        for h in (5, 10, 15)
    ]
    fires += [
        {"ts": (now - timedelta(hours=h)).isoformat(), "side": "short", "qty_btc": 0.6}
        for h in (20, 25)
    ]
    _write_fires(tmp_path / "j.jsonl", fires)
    _write_liqs(tmp_path / "l.csv", [])
    r = analyze(now=now, journal=tmp_path / "j.jsonl", liq_csv=tmp_path / "l.csv")
    assert r["by_side"]["long"]["fires"] == 3
    assert r["by_side"]["short"]["fires"] == 2


def test_format_report_section_contains_keys(tmp_path: Path) -> None:
    now = datetime(2026, 5, 13, 12, 0, tzinfo=timezone.utc)
    fires = [
        {"ts": (now - timedelta(hours=h)).isoformat(), "side": "long", "qty_btc": 0.5}
        for h in range(6)
    ]
    _write_fires(tmp_path / "j.jsonl", fires)
    _write_liqs(tmp_path / "l.csv", [])
    r = analyze(now=now, journal=tmp_path / "j.jsonl", liq_csv=tmp_path / "l.csv")
    text = format_report_section(r)
    assert "LIQ-CLUSTER" in text
    assert "Hit rate" in text
    assert "Recall" in text
