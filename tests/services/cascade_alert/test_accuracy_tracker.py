"""Tests for cascade accuracy_tracker."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from services.cascade_alert.accuracy_tracker import (
    CascadePrognosis,
    evaluate_pending,
    read_journal,
    record_prognosis,
    summary,
)


def test_record_and_read(tmp_path: Path) -> None:
    p = tmp_path / "j.jsonl"
    record_prognosis(CascadePrognosis(
        ts="2026-05-13T01:11:00+00:00",
        direction="long", threshold_btc=5.0,
        spot_price=81_358.0, qty_btc=5.14,
        predicted_pct_12h=1.14,
    ), path=p)
    rows = read_journal(path=p)
    assert len(rows) == 1
    assert rows[0]["direction"] == "long"


def test_evaluate_pending_fills_realized(tmp_path: Path) -> None:
    p = tmp_path / "j.jsonl"
    ts = datetime(2026, 5, 13, 1, 11, tzinfo=timezone.utc)
    record_prognosis(CascadePrognosis(
        ts=ts.isoformat(), direction="long", threshold_btc=5.0,
        spot_price=81_358.0, qty_btc=5.14, predicted_pct_12h=1.14,
    ), path=p)

    # Mock price at +12h: $80,612 (real 13.05 data — drop −0.92%)
    def mock_price(t: datetime) -> float:
        prices = {
            ts + timedelta(hours=4): 81_080.0,
            ts + timedelta(hours=12): 80_612.0,
            ts + timedelta(hours=24): 80_900.0,
        }
        return prices.get(t, 0.0)

    later = ts + timedelta(hours=25)
    n = evaluate_pending(get_price_fn=mock_price, now=later, path=p)
    assert n == 3  # 3 horizons filled

    rows = read_journal(path=p)
    r = rows[0]
    # 12h drop −0.92% → correct=False (expected UP, but went down)
    assert r["realized_pct_12h"] < 0
    assert r["correct_12h"] is False
    # 4h drop −0.34% → also wrong
    assert r["correct_4h"] is False
    # 24h drop −0.56% → also wrong
    assert r["correct_24h"] is False


def test_evaluate_only_after_horizon(tmp_path: Path) -> None:
    """Не заполнять если ещё рано."""
    p = tmp_path / "j.jsonl"
    ts = datetime(2026, 5, 13, 1, 0, tzinfo=timezone.utc)
    record_prognosis(CascadePrognosis(
        ts=ts.isoformat(), direction="long", threshold_btc=5.0,
        spot_price=80_000.0, qty_btc=5.0, predicted_pct_12h=1.0,
    ), path=p)
    # only +2h passed — none of the horizons reached
    later = ts + timedelta(hours=2)
    n = evaluate_pending(get_price_fn=lambda t: 80_100.0, now=later, path=p)
    assert n == 0
    rows = read_journal(path=p)
    assert rows[0].get("realized_pct_4h") is None


def test_summary_aggregates_accuracy(tmp_path: Path) -> None:
    p = tmp_path / "j.jsonl"
    # 5 long cascades, 3 correct
    for i, (price_then, price_12h) in enumerate([
        (80_000, 81_000),  # +1.25% — correct UP
        (80_000, 80_500),  # +0.625 — correct
        (80_000, 81_500),  # +1.875 — correct
        (80_000, 79_500),  # -0.625 — wrong
        (80_000, 79_000),  # -1.25 — wrong
    ]):
        ts = datetime(2026, 5, 13, i, 0, tzinfo=timezone.utc)
        record_prognosis(CascadePrognosis(
            ts=ts.isoformat(), direction="long", threshold_btc=5.0,
            spot_price=price_then, qty_btc=5.0, predicted_pct_12h=1.0,
        ), path=p)
        later = ts + timedelta(hours=13)
        evaluate_pending(get_price_fn=lambda t, p_then=price_then, p_after=price_12h: p_after,
                         now=later, path=p)

    s = summary(path=p, min_samples=5)
    assert s["total"] == 5
    assert s["by_bucket"]["long"]["12h"]["n"] == 5
    assert s["by_bucket"]["long"]["12h"]["accuracy"] == 60.0
