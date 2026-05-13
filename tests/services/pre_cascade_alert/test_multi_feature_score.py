"""Tests for Phase-2 multi-feature score."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from services.pre_cascade_alert.multi_feature_score import (
    compute_score,
    is_high_confidence,
    HIGH_CONFIDENCE_THRESHOLD,
)


def _write_history(path: Path, snapshots: list[tuple[datetime, dict]]) -> None:
    lines = []
    for ts, payload in snapshots:
        lines.append(json.dumps({"last_updated": ts.isoformat(timespec="seconds"),
                                 "BTCUSDT": payload}))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_no_liq_no_signals_score_zero(tmp_path: Path) -> None:
    hp = tmp_path / "h.jsonl"
    now = datetime(2026, 5, 13, 16, 30, tzinfo=timezone.utc)
    _write_history(hp, [
        (now - timedelta(hours=1), {"oi_change_1h_pct": 0.0, "funding_rate_8h": 0.0, "global_ls_ratio": 1.0}),
        (now, {"oi_change_1h_pct": 0.0, "funding_rate_8h": 0.0, "global_ls_ratio": 1.0}),
    ])
    s = compute_score(liq_long_5min=0.0, liq_short_5min=0.0,
                      now=now, history_path=hp)
    assert s.total == 0.0
    assert not is_high_confidence(s)


def test_liq_only_at_norm_gives_half(tmp_path: Path) -> None:
    """Liq=norm (0.3) → liq_score=1.0, weight 0.5 → total=0.5."""
    hp = tmp_path / "h.jsonl"
    now = datetime(2026, 5, 13, 16, 30, tzinfo=timezone.utc)
    _write_history(hp, [
        (now - timedelta(hours=1), {"oi_change_1h_pct": 0.0, "funding_rate_8h": 0.0, "global_ls_ratio": 1.0}),
        (now, {"oi_change_1h_pct": 0.0, "funding_rate_8h": 0.0, "global_ls_ratio": 1.0}),
    ])
    s = compute_score(liq_long_5min=0.3, liq_short_5min=0.0,
                      now=now, history_path=hp)
    assert s.side == "long"
    assert s.liq_score == 1.0
    assert s.total == 0.5
    assert not is_high_confidence(s)  # below 1.0 threshold? 0.5 < 1.0


def test_all_features_max_exceeds_threshold(tmp_path: Path) -> None:
    """liq at 2x norm + остальные at max → total > 1.0 → high confidence."""
    hp = tmp_path / "h.jsonl"
    now = datetime(2026, 5, 13, 16, 30, tzinfo=timezone.utc)
    _write_history(hp, [
        (now - timedelta(hours=1), {"oi_change_1h_pct": 0.0, "funding_rate_8h": 0.0, "global_ls_ratio": 1.0}),
        (now, {"oi_change_1h_pct": 1.0, "funding_rate_8h": 0.0003, "global_ls_ratio": 1.5}),
    ])
    s = compute_score(liq_long_5min=0.6, liq_short_5min=0.0,  # 2x norm
                      now=now, history_path=hp)
    # liq_score=2.0, oi=1.0, fund=1.0, ls=1.0
    # total = 0.5*2.0 + 0.2*1.0 + 0.15*1.0 + 0.15*1.0 = 1.0 + 0.5 = 1.5
    assert s.total == 1.5
    assert is_high_confidence(s)


def test_extreme_liq_alone_high_confidence(tmp_path: Path) -> None:
    """Очень большой liq-кластер (3x norm) сам по себе → high confidence."""
    hp = tmp_path / "h.jsonl"
    now = datetime(2026, 5, 13, 16, 30, tzinfo=timezone.utc)
    _write_history(hp, [(now, {"oi_change_1h_pct": 0.0, "funding_rate_8h": 0.0, "global_ls_ratio": 1.0})])
    s = compute_score(liq_long_5min=0.9, liq_short_5min=0.0,
                      now=now, history_path=hp)
    # liq_score=3.0 (cap), total = 0.5*3 = 1.5
    assert s.liq_score == 3.0
    assert s.total == 1.5
    assert is_high_confidence(s)


def test_liq_score_capped(tmp_path: Path) -> None:
    """Liq >= 3x norm не растёт выше cap=3.0."""
    hp = tmp_path / "h.jsonl"
    now = datetime(2026, 5, 13, 16, 30, tzinfo=timezone.utc)
    _write_history(hp, [(now, {"oi_change_1h_pct": 0.0, "funding_rate_8h": 0.0, "global_ls_ratio": 1.0})])
    s = compute_score(liq_long_5min=10.0, liq_short_5min=0.0,
                      now=now, history_path=hp)
    assert s.liq_score == 3.0  # capped, not 33.3


def test_dominant_side_picked_by_liq(tmp_path: Path) -> None:
    hp = tmp_path / "h.jsonl"
    now = datetime(2026, 5, 13, 16, 30, tzinfo=timezone.utc)
    _write_history(hp, [(now, {"oi_change_1h_pct": 0.0, "funding_rate_8h": 0.0, "global_ls_ratio": 1.0})])
    s = compute_score(liq_long_5min=0.1, liq_short_5min=0.4,
                      now=now, history_path=hp)
    assert s.side == "short"


def test_missing_history_does_not_crash(tmp_path: Path) -> None:
    """Если history файла нет — score рассчитывается с нулями."""
    hp = tmp_path / "missing.jsonl"
    now = datetime(2026, 5, 13, 16, 30, tzinfo=timezone.utc)
    s = compute_score(liq_long_5min=0.3, liq_short_5min=0.0,
                      now=now, history_path=hp)
    assert s.side == "long"
    assert s.liq_score == 1.0
    # oi/funding/ls all 0 since no history
    assert s.oi_score == 0.0
    assert s.funding_flip_score == 0.0


def test_oi_change_positive_or_negative_counts(tmp_path: Path) -> None:
    """OI change учитывается по модулю (рост и падение оба = signal)."""
    hp = tmp_path / "h.jsonl"
    now = datetime(2026, 5, 13, 16, 30, tzinfo=timezone.utc)
    _write_history(hp, [(now, {"oi_change_1h_pct": -1.0, "funding_rate_8h": 0.0, "global_ls_ratio": 1.0})])
    s = compute_score(liq_long_5min=0.0, liq_short_5min=0.0,
                      now=now, history_path=hp)
    assert s.oi_score == 1.0


def test_components_text_in_output(tmp_path: Path) -> None:
    hp = tmp_path / "h.jsonl"
    now = datetime(2026, 5, 13, 16, 30, tzinfo=timezone.utc)
    _write_history(hp, [(now, {"oi_change_1h_pct": 0.5, "funding_rate_8h": 0.0, "global_ls_ratio": 1.0})])
    s = compute_score(liq_long_5min=0.3, liq_short_5min=0.0,
                      now=now, history_path=hp)
    assert "liq=" in s.components_text
    assert "oi=" in s.components_text
