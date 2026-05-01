from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from .sessions import SESSION_LABELS

_7D_NS = int(7 * 24 * 3600 * 1e9)
_HISTORY_RESAMPLE = "5min"  # compute unmitigated JSON at 5-min resolution, ffill to 1m


@dataclass
class _LevelRecord:
    session: str
    is_high: bool
    create_ts: pd.Timestamp
    level_price: float
    mitigation_ts: Optional[pd.Timestamp] = field(default=None)


def _extract_levels(df: pd.DataFrame) -> list[_LevelRecord]:
    """Extract one LevelRecord per completed session instance (high + low)."""
    records: list[_LevelRecord] = []
    for sess in SESSION_LABELS:
        mask = df["session_active"] == sess
        if not mask.any():
            continue
        sess_df = df[mask]
        for sid, grp in sess_df.groupby("_kz_session_id"):
            close_ts = grp.index[-1]
            high_price = float(grp["high"].max())
            low_price = float(grp["low"].min())
            records.append(_LevelRecord(sess, True,  close_ts, high_price))
            records.append(_LevelRecord(sess, False, close_ts, low_price))
    records.sort(key=lambda r: r.create_ts)
    return records


def _find_mitigation_ts(
    records: list[_LevelRecord],
    high_arr: np.ndarray,
    low_arr: np.ndarray,
    ts_index: pd.DatetimeIndex,
) -> None:
    """Fill mitigation_ts in-place for each record using vectorized numpy argmax."""
    ts_ns = np.asarray(ts_index.astype(np.int64))

    for rec in records:
        # Find bar index immediately after session close
        create_ns = rec.create_ts.value
        start_idx = int(np.searchsorted(ts_ns, create_ns, side="right"))
        if start_idx >= len(ts_ns):
            continue  # level created at last bar — no subsequent bars

        if rec.is_high:
            touch = high_arr[start_idx:] >= rec.level_price
        else:
            touch = low_arr[start_idx:] <= rec.level_price

        if touch.any():
            first = int(np.argmax(touch))
            rec.mitigation_ts = ts_index[start_idx + first]


def _build_unmitigated_arrays(
    df: pd.DataFrame,
    records: list[_LevelRecord],
) -> pd.DataFrame:
    """Build unmitigated history columns at 5min resolution, then reindex to 1m.

    Returns DataFrame with columns:
      unmitigated_session_highs_history  (JSON string)
      unmitigated_session_lows_history   (JSON string)
      nearest_unmitigated_high_above     (float)
      nearest_unmitigated_high_above_age_h (float)
      nearest_unmitigated_low_below      (float)
      nearest_unmitigated_low_below_age_h  (float)
      unmitigated_count_7d               (int)
    """
    if not records:
        cols = [
            "unmitigated_session_highs_history",
            "unmitigated_session_lows_history",
            "nearest_unmitigated_high_above",
            "nearest_unmitigated_high_above_age_h",
            "nearest_unmitigated_low_below",
            "nearest_unmitigated_low_below_age_h",
            "unmitigated_count_7d",
        ]
        result = pd.DataFrame(index=df.index)
        for c in cols:
            result[c] = None if "history" in c else np.nan
        result["unmitigated_count_7d"] = 0
        return result

    # Resample to 5min index for cheaper iteration
    df_5m = df["close"].resample(_HISTORY_RESAMPLE).last().dropna()
    bar_ts_5m = df_5m.index
    close_5m = df_5m.values

    n_bars = len(bar_ts_5m)
    bar_ts_ns = np.asarray(bar_ts_5m.astype(np.int64))

    # Vectorize level arrays
    highs = [r for r in records if r.is_high]
    lows  = [r for r in records if not r.is_high]

    def _process(level_list: list[_LevelRecord], is_high: bool) -> tuple:
        if not level_list:
            return (
                ["[]"] * n_bars,
                np.full(n_bars, np.nan),
                np.full(n_bars, np.nan),
            )

        create_ns = np.array([r.create_ts.value for r in level_list], dtype=np.int64)
        mitig_ns = np.array(
            [r.mitigation_ts.value if r.mitigation_ts is not None else np.iinfo(np.int64).max
             for r in level_list],
            dtype=np.int64,
        )
        prices = np.array([r.level_price for r in level_list], dtype=np.float64)
        sessions = [r.session for r in level_list]

        history_strs: list[str] = []
        nearest_price = np.full(n_bars, np.nan)
        nearest_age_h = np.full(n_bars, np.nan)

        CHUNK = 2000
        for chunk_start in range(0, n_bars, CHUNK):
            chunk_end = min(chunk_start + CHUNK, n_bars)
            chunk_ts = bar_ts_ns[chunk_start:chunk_end]  # (C,)
            chunk_close = close_5m[chunk_start:chunk_end]  # (C,)

            # (L, C) boolean visibility matrix
            in_window = (
                (create_ns[:, None] < chunk_ts[None, :]) &
                (chunk_ts[None, :] - create_ns[:, None] <= _7D_NS)
            )
            not_mitigated = mitig_ns[:, None] > chunk_ts[None, :]
            visible = in_window & not_mitigated  # (L, C)

            for b in range(chunk_end - chunk_start):
                abs_b = chunk_start + b
                vis_mask = visible[:, b]
                if not vis_mask.any():
                    history_strs.append("[]")
                    continue

                vis_prices = prices[vis_mask]
                vis_sessions = [sessions[i] for i in np.where(vis_mask)[0]]
                vis_create_ns = create_ns[vis_mask]
                age_h = (chunk_ts[b] - vis_create_ns) / 3_600_000_000_000.0

                # Build JSON entries
                if is_high:
                    sort_idx = np.argsort(-vis_prices)  # descending
                else:
                    sort_idx = np.argsort(vis_prices)   # ascending

                entries = []
                for k in sort_idx:
                    entries.append({
                        "session": vis_sessions[k],
                        "session_close_ts": int(vis_create_ns[k] // 1_000_000),
                        "level": float(vis_prices[k]),
                        "age_hours": round(float(age_h[k]), 2),
                    })
                history_strs.append(json.dumps(entries))

                # Nearest above (for highs) or below (for lows)
                cur_close = chunk_close[b]
                if is_high:
                    above = vis_prices[vis_prices > cur_close]
                    if len(above) > 0:
                        nearest_price[abs_b] = float(np.min(above))
                        idx_near = np.where(vis_prices == nearest_price[abs_b])[0]
                        if len(idx_near) > 0:
                            nearest_age_h[abs_b] = float(age_h[idx_near[0]])
                else:
                    below = vis_prices[vis_prices < cur_close]
                    if len(below) > 0:
                        nearest_price[abs_b] = float(np.max(below))
                        idx_near = np.where(vis_prices == nearest_price[abs_b])[0]
                        if len(idx_near) > 0:
                            nearest_age_h[abs_b] = float(age_h[idx_near[0]])

        return history_strs, nearest_price, nearest_age_h

    high_history, nearest_h_price, nearest_h_age = _process(highs, True)
    low_history,  nearest_l_price, nearest_l_age  = _process(lows,  False)

    # Build result at 5min resolution
    result_5m = pd.DataFrame(index=bar_ts_5m)
    result_5m["unmitigated_session_highs_history"] = high_history
    result_5m["unmitigated_session_lows_history"]  = low_history
    result_5m["nearest_unmitigated_high_above"]      = nearest_h_price
    result_5m["nearest_unmitigated_high_above_age_h"] = nearest_h_age
    result_5m["nearest_unmitigated_low_below"]       = nearest_l_price
    result_5m["nearest_unmitigated_low_below_age_h"]  = nearest_l_age

    # unmitigated_count_7d: sum of visible highs + lows per bar
    # Recompute count cheaply using visibility sums
    _count_combined: list[int] = []
    for i in range(len(high_history)):
        h_count = 0 if high_history[i] == "[]" else len(json.loads(high_history[i]))
        l_count = 0 if low_history[i]  == "[]" else len(json.loads(low_history[i]))
        _count_combined.append(h_count + l_count)
    result_5m["unmitigated_count_7d"] = _count_combined

    # Reindex to original 1m index (forward-fill 5min → 1m)
    result_1m = result_5m.reindex(df.index, method="ffill")
    result_1m["unmitigated_count_7d"] = result_1m["unmitigated_count_7d"].fillna(0).astype(int)
    return result_1m


def _add_per_session_mitigation_ts(
    df: pd.DataFrame,
    records: list[_LevelRecord],
) -> pd.DataFrame:
    """Add {sess}_high_mitigated_ts and {sess}_low_mitigated_ts columns.

    Each column = mitigation_ts of the most recently closed session of that type.
    NaT if the most recent session's level is not yet mitigated.
    """
    out = df.copy()
    for sess in SESSION_LABELS:
        for is_high in (True, False):
            suffix = "high" if is_high else "low"
            col = f"{sess}_{suffix}_mitigated_ts"

            sess_recs = [r for r in records if r.session == sess and r.is_high == is_high]
            if not sess_recs:
                out[col] = pd.NaT
                continue

            # One event per session instance: at session close, record mitigation_ts (or NaT)
            close_times = [r.create_ts for r in sess_recs]
            mitig_times = [r.mitigation_ts for r in sess_recs]
            events = pd.Series(mitig_times, index=pd.DatetimeIndex(close_times, tz="UTC"))
            events = events.sort_index()

            # Forward-fill: at bar T, show the most recent session's mitigation_ts
            out[col] = events.reindex(df.index, method="ffill")

    return out


def add_mitigation_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add all mitigation-related columns to df."""
    records = _extract_levels(df)
    _find_mitigation_ts(
        records,
        df["high"].values,
        df["low"].values,
        df.index,
    )

    out = _add_per_session_mitigation_ts(df, records)
    history_df = _build_unmitigated_arrays(out, records)

    for col in history_df.columns:
        out[col] = history_df[col]

    return out
