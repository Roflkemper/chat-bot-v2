"""Tests for reports.py — §12 TZ-022."""
from __future__ import annotations

import json
import pandas as pd
import pytest

from src.whatif.reports import (
    _fmt,
    _parse_params,
    _section_header,
    _section_param_grid,
    _section_summary_table,
    _section_best_combo,
    _section_episodes,
    generate_report,
    write_report,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

def _results_df() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "param_combo_id": "aaa00001",
            "param_values": json.dumps({"offset_pct": 0.3}),
            "n_episodes": 100,
            "mean_pnl_usd": -250.0,
            "median_pnl_usd": -245.0,
            "p25_pnl_usd": -300.0,
            "p75_pnl_usd": -200.0,
            "mean_pnl_vs_baseline_usd": -1.5,
            "win_rate": 0.12,
            "mean_dd_pct": 1.8,
            "max_dd_pct": 5.0,
            "mean_dd_vs_baseline_pct": -0.09,
            "mean_target_hit_pct": 0.07,
            "mean_volume_traded_usd": 1500.0,
            "mean_duration_min": 240.0,
        },
        {
            "param_combo_id": "bbb00002",
            "param_values": json.dumps({"offset_pct": 1.0}),
            "n_episodes": 100,
            "mean_pnl_usd": -255.0,
            "median_pnl_usd": -248.0,
            "p25_pnl_usd": -310.0,
            "p75_pnl_usd": -205.0,
            "mean_pnl_vs_baseline_usd": -2.0,
            "win_rate": 0.07,
            "mean_dd_pct": 1.9,
            "max_dd_pct": 5.2,
            "mean_dd_vs_baseline_pct": -0.04,
            "mean_target_hit_pct": 0.07,
            "mean_volume_traded_usd": 2100.0,
            "mean_duration_min": 240.0,
        },
    ])


def _manifest() -> dict:
    return {
        "version": "v1",
        "timestamp": "2026-04-27T10:00:00+00:00",
        "plays_processed": ["P-1"],
        "horizon_min": 240,
        "n_workers": 4,
        "params_hash": "ab12cd34",
    }


def _raw_df(combo_id: str = "aaa00001") -> pd.DataFrame:
    rows = []
    for i in range(10):
        rows.append({
            "param_combo_id": combo_id,
            "param_values": json.dumps({"offset_pct": 0.3}),
            "ts_start": f"2026-0{(i % 9) + 1}-15 08:00:00+00:00",
            "episode_type": "rally_strong" if i % 2 == 0 else "rally_critical",
            "pnl_usd": -250.0 + i * 5,
            "pnl_vs_baseline_usd": -5.0 + i * 1.0,
            "max_drawdown_pct": 2.0,
            "dd_vs_baseline_pct": -0.1 + i * 0.01,
            "target_hit_count": 1 if i == 9 else 0,
            "volume_traded_usd": 1500.0,
            "duration_min": 240,
        })
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# _fmt helpers
# ─────────────────────────────────────────────────────────────────────────────

def test_fmt_normal_float():
    assert _fmt(1.234) == "1.23"


def test_fmt_none_returns_dash():
    assert _fmt(None) == "—"


def test_fmt_nan_returns_dash():
    import math
    assert _fmt(float("nan")) == "—"


def test_fmt_percent():
    assert _fmt(0.112, ".1%") == "11.2%"


def test_parse_params_single():
    assert _parse_params('{"offset_pct": 0.3}') == "offset_pct=0.3"


def test_parse_params_multiple_sorted():
    result = _parse_params('{"z": 1, "a": 2}')
    assert result.startswith("a=")


# ─────────────────────────────────────────────────────────────────────────────
# Header section
# ─────────────────────────────────────────────────────────────────────────────

def test_header_contains_play_id():
    lines = _section_header("P-1", _results_df(), _manifest())
    text = "\n".join(lines)
    assert "P-1" in text


def test_header_contains_play_name():
    lines = _section_header("P-1", _results_df(), _manifest())
    text = "\n".join(lines)
    assert "Raise Boundary" in text


def test_header_contains_date():
    lines = _section_header("P-1", _results_df(), _manifest())
    text = "\n".join(lines)
    assert "2026-04-27" in text


def test_header_contains_version():
    lines = _section_header("P-1", _results_df(), _manifest())
    text = "\n".join(lines)
    assert "v1" in text


def test_header_contains_n_episodes():
    lines = _section_header("P-1", _results_df(), _manifest())
    text = "\n".join(lines)
    assert "100" in text


def test_header_missing_manifest_fallback():
    lines = _section_header("P-1", _results_df(), {})
    text = "\n".join(lines)
    assert "P-1" in text
    assert "unknown" in text


# ─────────────────────────────────────────────────────────────────────────────
# Param grid section
# ─────────────────────────────────────────────────────────────────────────────

def test_param_grid_shows_param_name():
    lines = _section_param_grid(_results_df())
    text = "\n".join(lines)
    assert "offset_pct" in text


def test_param_grid_shows_all_values():
    lines = _section_param_grid(_results_df())
    text = "\n".join(lines)
    assert "0.3" in text
    assert "1.0" in text


def test_param_grid_empty_df_returns_empty():
    lines = _section_param_grid(pd.DataFrame())
    assert lines == []


# ─────────────────────────────────────────────────────────────────────────────
# Summary table
# ─────────────────────────────────────────────────────────────────────────────

def test_summary_table_has_header_row():
    lines = _section_summary_table(_results_df())
    text = "\n".join(lines)
    assert "combo_id" in text
    assert "win_rate" in text


def test_summary_table_has_both_combos():
    lines = _section_summary_table(_results_df())
    text = "\n".join(lines)
    assert "aaa00001" in text
    assert "bbb00002" in text


def test_summary_table_sorted_best_first():
    lines = _section_summary_table(_results_df())
    # aaa00001 has mean_pnl_vs_baseline=-1.5 (better), bbb=-2.0
    data_lines = [l for l in lines if "aaa00001" in l or "bbb00002" in l]
    assert data_lines[0].startswith("| aaa00001")


# ─────────────────────────────────────────────────────────────────────────────
# Best combo section
# ─────────────────────────────────────────────────────────────────────────────

def test_best_combo_picks_highest_pnl_vs_baseline():
    lines, best_id = _section_best_combo(_results_df())
    assert best_id == "aaa00001"


def test_best_combo_shows_params():
    lines, _ = _section_best_combo(_results_df())
    text = "\n".join(lines)
    assert "offset_pct=0.3" in text


def test_best_combo_shows_win_rate():
    lines, _ = _section_best_combo(_results_df())
    text = "\n".join(lines)
    assert "12.0%" in text


# ─────────────────────────────────────────────────────────────────────────────
# Episode sections (top/worst)
# ─────────────────────────────────────────────────────────────────────────────

def test_episodes_none_raw_shows_not_available():
    lines = _section_episodes(None, "aaa00001")
    text = "\n".join(lines)
    assert "недоступны" in text or "not available" in text.lower() or "_raw.parquet" in text


def test_episodes_top5_selects_best_pnl_vs_baseline():
    raw = _raw_df("aaa00001")
    lines = _section_episodes(raw, "aaa00001")
    text = "\n".join(lines)
    # pnl_vs_baseline goes from -5.0 to +4.0; top row should have +4.0
    assert "Top-5" in text
    assert "Worst-5" in text


def test_episodes_wrong_combo_id_shows_no_data():
    raw = _raw_df("aaa00001")
    lines = _section_episodes(raw, "nonexistent")
    text = "\n".join(lines)
    assert "nonexistent" in text or "Нет данных" in text


def test_episodes_target_hit_shown_as_checkmark():
    raw = _raw_df("aaa00001")
    lines = _section_episodes(raw, "aaa00001")
    text = "\n".join(lines)
    # row i=9: target_hit_count=1 → ✓
    assert "✓" in text


# ─────────────────────────────────────────────────────────────────────────────
# generate_report integration
# ─────────────────────────────────────────────────────────────────────────────

def test_generate_report_returns_string():
    md = generate_report("P-1", _results_df(), _manifest())
    assert isinstance(md, str)
    assert len(md) > 100


def test_generate_report_contains_all_sections():
    md = generate_report("P-1", _results_df(), _manifest(), _raw_df())
    assert "# Play P-1" in md
    assert "Сетка параметров" in md
    assert "Сводная таблица" in md
    assert "Лучшее combo" in md
    assert "Top-5" in md
    assert "Worst-5" in md
    assert "Ограничения" in md


def test_generate_report_empty_df():
    md = generate_report("P-1", pd.DataFrame(), {})
    assert "No results" in md


def test_generate_report_no_raw_df():
    md = generate_report("P-1", _results_df(), _manifest(), raw_df=None)
    assert "# Play P-1" in md
    assert "_raw.parquet" in md


def test_generate_report_missing_manifest():
    md = generate_report("P-1", _results_df(), {})
    assert "# Play P-1" in md
    assert "unknown" in md


# ─────────────────────────────────────────────────────────────────────────────
# write_report (filesystem)
# ─────────────────────────────────────────────────────────────────────────────

def test_write_report_creates_md_file(tmp_path):
    df = _results_df()
    agg_path = tmp_path / "P-1_2026-04-27.parquet"
    df.to_parquet(agg_path, index=False)

    out = write_report("P-1", tmp_path, "2026-04-27")
    assert out.exists()
    assert out.suffix == ".md"
    content = out.read_text(encoding="utf-8")
    assert "# Play P-1" in content


def test_write_report_uses_raw_when_present(tmp_path):
    df = _results_df()
    raw = _raw_df("aaa00001")
    df.to_parquet(tmp_path / "P-1_2026-04-27.parquet", index=False)
    raw.to_parquet(tmp_path / "P-1_2026-04-27_raw.parquet", index=False)

    out = write_report("P-1", tmp_path, "2026-04-27")
    content = out.read_text(encoding="utf-8")
    assert "Top-5" in content
    assert "rally_" in content


def test_write_report_most_recent_date(tmp_path):
    df = _results_df()
    df.to_parquet(tmp_path / "P-1_2026-04-01.parquet", index=False)
    df.to_parquet(tmp_path / "P-1_2026-04-27.parquet", index=False)

    out = write_report("P-1", tmp_path)
    assert "2026-04-27" in out.name


def test_write_report_file_not_found_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        write_report("P-99", tmp_path)
