from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from whatif.episodes_window import EpisodesWindow, compute_tracker_window, latest_features_ts


def test_window_start_is_max_of_bot_mins(tmp_path, monkeypatch):
    csv = tmp_path / "snapshots_v2.csv"
    csv.write_text(
        "\n".join(
            [
                "ts_utc,bot_id,bot_name,alias",
                "2026-04-24T10:00:00+00:00,1,TEST_3,TEST_3",
                "2026-04-24T10:10:00+00:00,1,TEST_3,TEST_3",
                "2026-04-24T09:00:00+00:00,2,BTC-LONG-B,BTC-LONG-B",
                "2026-04-24T09:05:00+00:00,2,BTC-LONG-B,BTC-LONG-B",
                "2026-04-24T11:00:00+00:00,3,BTC-LONG-C,BTC-LONG-C",
            ]
        ),
        encoding="utf-8",
    )
    # Force features_end so end_ts is not empty after clipping.
    monkeypatch.setattr("whatif.episodes_window.latest_features_ts", lambda *args, **kwargs: pd.Timestamp("2026-04-25T00:00:00+00:00"))
    window = compute_tracker_window(["TEST_3", "BTC-LONG-B", "BTC-LONG-C"], snapshots_csv=csv)
    assert window.start_ts == pd.Timestamp("2026-04-24T11:00:00+00:00")


def test_empty_overlap_raises_explicit_error(tmp_path, monkeypatch):
    csv = tmp_path / "snapshots_v2.csv"
    csv.write_text(
        "\n".join(
            [
                "ts_utc,bot_id,bot_name,alias",
                "2026-04-24T23:30:00+00:00,1,TEST_3,TEST_3",
                "2026-04-24T23:31:00+00:00,2,BTC-LONG-B,BTC-LONG-B",
                "2026-04-24T23:32:00+00:00,3,BTC-LONG-C,BTC-LONG-C",
            ]
        ),
        encoding="utf-8",
    )
    # Clip end_ts earlier than start_ts to force empty window.
    monkeypatch.setattr("whatif.episodes_window.latest_features_ts", lambda *args, **kwargs: pd.Timestamp("2026-04-24T22:00:00+00:00"))
    with pytest.raises(ValueError, match="Tracker window is empty"):
        compute_tracker_window(["TEST_3", "BTC-LONG-B", "BTC-LONG-C"], snapshots_csv=csv)
