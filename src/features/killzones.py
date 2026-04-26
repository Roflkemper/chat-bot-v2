"""Killzone running and finalized state features.

Input df must have columns from calendar.compute():
    kz_active, kz_session_id, open, high, low, close.
Index: UTC tz-aware DatetimeIndex (1-minute bars).

Reference: ICT_KILLZONES_SPEC §6–11.
"""
from __future__ import annotations

import math
import numpy as np
import pandas as pd

# §16 fixed defaults
_SWEEP_X_MS = np.int64(240 * 60 * 1_000)   # 240 min breach window
_SWEEP_Y_MS = np.int64(30 * 60 * 1_000)    # 30 min return window
_RANGE_N = 5

SESSION_NAMES = ["ASIA", "LONDON", "NY_AM", "NY_LUNCH", "NY_PM"]
_PREFIX = {
    "ASIA": "asia",
    "LONDON": "london",
    "NY_AM": "nyam",
    "NY_LUNCH": "nylu",
    "NY_PM": "nypm",
}
_NAN = float("nan")


class _State:
    """Mutable per-session-type state for the forward pass."""

    __slots__ = (
        "pfx",
        "cur_sid", "run_h", "run_lo", "start_i", "last_i",
        "fin_h", "fin_lo", "fin_mid", "fin_close_ts",
        "high_mit", "low_mit", "mid_vis",
        "hs_phase", "hs_breach_ts", "hs_done",   # sweep high
        "ls_phase", "ls_breach_ts", "ls_done",   # sweep low
        "mid_visit_ts", "mid_visit_min",
        "range_hist",
    )

    def __init__(self, pfx: str) -> None:
        self.pfx = pfx
        self.cur_sid = ""
        self.run_h = _NAN
        self.run_lo = _NAN
        self.start_i = -1
        self.last_i = -1
        self.fin_h = _NAN
        self.fin_lo = _NAN
        self.fin_mid = _NAN
        self.fin_close_ts = np.int64(-1)
        self.high_mit = False
        self.low_mit = False
        self.mid_vis = False
        self.hs_phase = 0    # 0=watching, 1=breached, 2=confirmed, -1=expired
        self.hs_breach_ts = np.int64(-1)
        self.hs_done = False
        self.ls_phase = 0
        self.ls_breach_ts = np.int64(-1)
        self.ls_done = False
        self.mid_visit_ts = np.int64(-1)
        self.mid_visit_min = _NAN
        self.range_hist: list[float] = []

    def finalize(self, close_ts: np.int64) -> None:
        mid = (self.run_h + self.run_lo) / 2
        rng = self.run_h - self.run_lo
        rng_pct = rng / mid * 100 if mid != 0 else _NAN
        self.fin_h = self.run_h
        self.fin_lo = self.run_lo
        self.fin_mid = mid
        self.fin_close_ts = close_ts
        self.high_mit = False
        self.low_mit = False
        self.mid_vis = False
        self.hs_phase = 0
        self.hs_breach_ts = np.int64(-1)
        self.hs_done = False
        self.ls_phase = 0
        self.ls_breach_ts = np.int64(-1)
        self.ls_done = False
        self.mid_visit_ts = np.int64(-1)
        self.mid_visit_min = _NAN
        if not math.isnan(rng_pct):
            self.range_hist.append(rng_pct)
            if len(self.range_hist) > _RANGE_N:
                self.range_hist.pop(0)

    def update_flags(self, h: float, lo: float, cl: float, ts: np.int64) -> None:
        """Update forward-propagating flags after session close."""
        if self.fin_close_ts < 0:
            return
        elapsed = ts - self.fin_close_ts

        # mitigation (cumulative — never reset within same closed session)
        if not self.high_mit and h > self.fin_h:
            self.high_mit = True
        if not self.low_mit and lo < self.fin_lo:
            self.low_mit = True
        if not self.mid_vis and lo <= self.fin_mid <= h:
            self.mid_vis = True

        # midpoint visit timing (first touch only)
        if self.mid_visit_ts < 0 and lo <= self.fin_mid <= h:
            self.mid_visit_ts = ts
            self.mid_visit_min = float(elapsed) / 60_000.0

        # sweep high: breach within X, then close returns within Y (same-bar wick allowed)
        if self.hs_phase == 0:
            if elapsed <= _SWEEP_X_MS:
                if h > self.fin_h:
                    if cl < self.fin_h:       # same-bar wick sweep
                        self.hs_done = True
                        self.hs_phase = 2
                    else:                     # breach only → wait for return
                        self.hs_phase = 1
                        self.hs_breach_ts = ts
            else:
                self.hs_phase = -1
        elif self.hs_phase == 1:
            since = ts - self.hs_breach_ts
            if since <= _SWEEP_Y_MS:
                if cl < self.fin_h:
                    self.hs_done = True
                    self.hs_phase = 2
            else:
                self.hs_phase = -1

        # sweep low: breach within X, then close returns within Y (same-bar wick allowed)
        if self.ls_phase == 0:
            if elapsed <= _SWEEP_X_MS:
                if lo < self.fin_lo:
                    if cl > self.fin_lo:      # same-bar wick sweep
                        self.ls_done = True
                        self.ls_phase = 2
                    else:                     # breach only → wait for return
                        self.ls_phase = 1
                        self.ls_breach_ts = ts
            else:
                self.ls_phase = -1
        elif self.ls_phase == 1:
            since = ts - self.ls_breach_ts
            if since <= _SWEEP_Y_MS:
                if cl > self.fin_lo:
                    self.ls_done = True
                    self.ls_phase = 2
            else:
                self.ls_phase = -1


def compute(df: pd.DataFrame) -> pd.DataFrame:
    """Add killzone state features to df.

    Requires df columns: kz_active, kz_session_id, open, high, low, close.
    Index must be UTC tz-aware DatetimeIndex.
    """
    out = df.copy()
    n = len(out)
    if n == 0:
        return out

    high = out["high"].to_numpy(dtype=float)
    low = out["low"].to_numpy(dtype=float)
    close_ = out["close"].to_numpy(dtype=float)
    open_ = out["open"].to_numpy(dtype=float)
    kz_active = out["kz_active"].to_numpy(dtype=object)
    kz_session_id = out["kz_session_id"].to_numpy(dtype=object)
    ts_ms = out.index.asi8 // 1_000_000  # nanoseconds → milliseconds

    # ── Allocate running-state arrays (6 cols) ────────────────────────────────
    kz_run_h = np.full(n, _NAN)
    kz_run_lo = np.full(n, _NAN)
    kz_run_mid = np.full(n, _NAN)
    kz_run_rng = np.full(n, _NAN)
    kz_run_rng_pct = np.full(n, _NAN)
    kz_min_into = np.full(n, _NAN)

    # ── Allocate finalized/sweep/magnet/range arrays (per type) ──────────────
    pfx_list = [_PREFIX[s] for s in SESSION_NAMES]
    A: dict[str, np.ndarray] = {}
    for pfx in pfx_list:
        A[f"last_{pfx}_high"] = np.full(n, _NAN)
        A[f"last_{pfx}_low"] = np.full(n, _NAN)
        A[f"last_{pfx}_midpoint"] = np.full(n, _NAN)
        A[f"last_{pfx}_close_ts"] = np.full(n, np.int64(-1), dtype=np.int64)
        A[f"last_{pfx}_high_mitigated"] = np.zeros(n, dtype=bool)
        A[f"last_{pfx}_low_mitigated"] = np.zeros(n, dtype=bool)
        A[f"last_{pfx}_midpoint_visited"] = np.zeros(n, dtype=bool)
        A[f"{pfx}_high_sweep"] = np.zeros(n, dtype=bool)
        A[f"{pfx}_low_sweep"] = np.zeros(n, dtype=bool)
        A[f"{pfx}_minutes_to_midpoint_visit"] = np.full(n, _NAN)
        A[f"{pfx}_avg_range_pct_5"] = np.full(n, _NAN)
        A[f"{pfx}_current_range_vs_avg"] = np.full(n, _NAN)

    # ── NY AM false move arrays (3 cols) ──────────────────────────────────────
    nyam_first30_dir = np.zeros(n, dtype=np.int8)
    nyam_first30_mag = np.full(n, _NAN)
    nyam_reversal_arr = np.zeros(n, dtype=bool)

    # NY_AM tracking vars (reset on each new NY_AM session)
    nyam_open_px = _NAN
    nyam_dir_val: int = 0
    nyam_mag_val: float = _NAN
    nyam_reversal_val = False
    nyam_locked = False

    # ── Initialize session states ─────────────────────────────────────────────
    states = {name: _State(_PREFIX[name]) for name in SESSION_NAMES}

    # ── Single forward pass ───────────────────────────────────────────────────
    for i in range(n):
        h = high[i]
        lo = low[i]
        cl = close_[i]
        op = open_[i]
        ts = ts_ms[i]
        active = kz_active[i]
        sid = kz_session_id[i]

        # Detect session end: prev row was an active session, this row is not.
        # Finalize immediately so downstream tests can see the finalized state
        # without waiting for the next same-type session.
        if i > 0:
            prev_act = kz_active[i - 1]
            if prev_act in SESSION_NAMES and active != prev_act:
                st_end = states[prev_act]
                if st_end.cur_sid != "" and not math.isnan(st_end.run_h):
                    st_end.finalize(ts_ms[st_end.last_i])
                    st_end.cur_sid = ""  # mark: no in-progress session of this type

        for sname in SESSION_NAMES:
            st = states[sname]
            pfx = st.pfx
            is_active = active == sname

            if is_active:
                if st.cur_sid != sid:
                    # New session of this type. Finalize any in-progress one that
                    # was not yet finalized by the transition detector above (edge case:
                    # two consecutive sessions of the same type with no NONE gap).
                    if st.cur_sid != "":
                        st.finalize(ts_ms[st.last_i])
                    st.cur_sid = sid
                    st.run_h = h
                    st.run_lo = lo
                    st.start_i = i
                    st.last_i = i
                    if sname == "NY_AM":
                        nyam_open_px = op
                        nyam_dir_val = 0
                        nyam_mag_val = _NAN
                        nyam_reversal_val = False
                        nyam_locked = False
                else:
                    if h > st.run_h:
                        st.run_h = h
                    if lo < st.run_lo:
                        st.run_lo = lo
                    st.last_i = i

                # Write running state (single active session only)
                run_mid = (st.run_h + st.run_lo) / 2
                run_rng = st.run_h - st.run_lo
                run_rng_pct = run_rng / run_mid * 100 if run_mid != 0 else _NAN
                min_into = i - st.start_i
                kz_run_h[i] = st.run_h
                kz_run_lo[i] = st.run_lo
                kz_run_mid[i] = run_mid
                kz_run_rng[i] = run_rng
                kz_run_rng_pct[i] = run_rng_pct
                kz_min_into[i] = min_into

                # Range vs avg (only when active)
                if len(st.range_hist) >= _RANGE_N:
                    avg_r = sum(st.range_hist) / _RANGE_N
                    A[f"{pfx}_avg_range_pct_5"][i] = avg_r
                    if avg_r != 0 and not math.isnan(run_rng_pct):
                        A[f"{pfx}_current_range_vs_avg"][i] = run_rng_pct / avg_r

                # NY_AM false move tracking
                if sname == "NY_AM":
                    if min_into == 29 and not nyam_locked:
                        delta = (cl - nyam_open_px) / nyam_open_px * 100 if nyam_open_px else 0.0
                        nyam_dir_val = 1 if delta > 0 else (-1 if delta < 0 else 0)
                        nyam_mag_val = abs(delta)
                        nyam_locked = True
                    elif min_into >= 30 and nyam_locked and not nyam_reversal_val:
                        if nyam_dir_val != 0 and not math.isnan(nyam_mag_val):
                            # ASSUMPTION: spec §11.3 formula appears inverted.
                            # Implementing as: reversal when price moved opposite to
                            # initial direction by ≥1.5× initial magnitude.
                            move = (cl - nyam_open_px) / nyam_open_px * 100
                            if move * nyam_dir_val < -1.5 * nyam_mag_val:
                                nyam_reversal_val = True
                    if nyam_locked:
                        nyam_first30_dir[i] = nyam_dir_val
                        nyam_first30_mag[i] = nyam_mag_val
                        nyam_reversal_arr[i] = nyam_reversal_val

            else:
                # Not active: propagate NY_AM false move values forward
                if sname == "NY_AM" and nyam_locked:
                    nyam_first30_dir[i] = nyam_dir_val
                    nyam_first30_mag[i] = nyam_mag_val
                    nyam_reversal_arr[i] = nyam_reversal_val

            # Update forward flags for this type's finalized session (all bars)
            st.update_flags(h, lo, cl, ts)

            # Write finalized state + flags
            if not math.isnan(st.fin_h):
                A[f"last_{pfx}_high"][i] = st.fin_h
                A[f"last_{pfx}_low"][i] = st.fin_lo
                A[f"last_{pfx}_midpoint"][i] = st.fin_mid
            A[f"last_{pfx}_close_ts"][i] = st.fin_close_ts
            A[f"last_{pfx}_high_mitigated"][i] = st.high_mit
            A[f"last_{pfx}_low_mitigated"][i] = st.low_mit
            A[f"last_{pfx}_midpoint_visited"][i] = st.mid_vis
            A[f"{pfx}_high_sweep"][i] = st.hs_done
            A[f"{pfx}_low_sweep"][i] = st.ls_done
            if not math.isnan(st.mid_visit_min):
                A[f"{pfx}_minutes_to_midpoint_visit"][i] = st.mid_visit_min
            # Propagate avg range when not active
            if not is_active and len(st.range_hist) >= _RANGE_N:
                A[f"{pfx}_avg_range_pct_5"][i] = sum(st.range_hist) / _RANGE_N

    # ── Distance features (vectorized after loop) ─────────────────────────────
    # Active KZ (3 cols) — NaN when kz_active == NONE
    dist_act_h = (kz_run_h - close_) / close_ * 100
    dist_act_lo = (close_ - kz_run_lo) / close_ * 100
    dist_act_mid = (close_ - kz_run_mid) / close_ * 100

    # Last KZ per type (5 × 3 = 15 cols)
    dist_last: dict[str, np.ndarray] = {}
    for pfx in pfx_list:
        lh = A[f"last_{pfx}_high"]
        llo = A[f"last_{pfx}_low"]
        lm = A[f"last_{pfx}_midpoint"]
        dist_last[f"dist_last_{pfx}_high_pct"] = (lh - close_) / close_ * 100
        dist_last[f"dist_last_{pfx}_low_pct"] = (close_ - llo) / close_ * 100
        dist_last[f"dist_last_{pfx}_midpoint_pct"] = (close_ - lm) / close_ * 100

    # ── Assign to output ──────────────────────────────────────────────────────
    out["kz_running_high"] = kz_run_h
    out["kz_running_low"] = kz_run_lo
    out["kz_running_midpoint"] = kz_run_mid
    out["kz_running_range"] = kz_run_rng
    out["kz_running_range_pct"] = kz_run_rng_pct
    out["kz_minutes_into_session"] = kz_min_into

    for col, vals in A.items():
        out[col] = vals

    out["dist_active_kz_high_pct"] = dist_act_h
    out["dist_active_kz_low_pct"] = dist_act_lo
    out["dist_active_kz_midpoint_pct"] = dist_act_mid
    for col, vals in dist_last.items():
        out[col] = vals

    out["nyam_first30_direction"] = nyam_first30_dir
    out["nyam_first30_magnitude_pct"] = nyam_first30_mag
    out["nyam_reversal_after_first30"] = nyam_reversal_arr

    return out
