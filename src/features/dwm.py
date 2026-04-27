"""Day/Week/Month boundary features.

Input df must have columns: open, high, low, close.
Index: UTC tz-aware DatetimeIndex (1-minute bars).

Computes ~30 columns:
  DWM open prices (3): d_open, w_open, m_open
  Previous H/L (6):    pdh, pdl, pwh, pwl, pmh, pml
  Hit flags (6):       pdh_hit, pdl_hit, pwh_hit, pwl_hit, pmh_hit, pml_hit
  Distance (9):        dist_to_pdh/pdl/pwh/pwl/pmh/pml/d_open/w_open/m_open _pct
  Current day H/L (4): current_d_high, current_d_low, dist_to_d_high_pct, dist_to_d_low_pct
  PDH/PDL sweep (2):   pdh_sweep, pdl_sweep (same-bar wick logic, Y=30 min)

Reference: ICT_KILLZONES_SPEC §10, §11.4.
"""
from __future__ import annotations

import math
import numpy as np
import pandas as pd

# PDH/PDL sweep return window (§11.4, §16)
_SWEEP_Y_MS = np.int64(30 * 60 * 1_000)

_NAN = float("nan")


def compute(df: pd.DataFrame) -> pd.DataFrame:
    """Add DWM features to df.

    Requires df columns: open, high, low, close.
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
    ts_ms = out.index.asi8 // 1_000_000

    idx = out.index
    hours = idx.hour
    minutes_ = idx.minute
    weekdays = idx.weekday    # 0=Monday … 6=Sunday
    days = idx.day            # 1-31

    # ── Allocate output arrays ────────────────────────────────────────────────
    d_open_arr = np.full(n, _NAN)
    w_open_arr = np.full(n, _NAN)
    m_open_arr = np.full(n, _NAN)

    pdh_arr = np.full(n, _NAN)
    pdl_arr = np.full(n, _NAN)
    pwh_arr = np.full(n, _NAN)
    pwl_arr = np.full(n, _NAN)
    pmh_arr = np.full(n, _NAN)
    pml_arr = np.full(n, _NAN)

    pdh_hit_arr = np.zeros(n, dtype=bool)
    pdl_hit_arr = np.zeros(n, dtype=bool)
    pwh_hit_arr = np.zeros(n, dtype=bool)
    pwl_hit_arr = np.zeros(n, dtype=bool)
    pmh_hit_arr = np.zeros(n, dtype=bool)
    pml_hit_arr = np.zeros(n, dtype=bool)

    cur_d_high_arr = np.full(n, _NAN)
    cur_d_low_arr = np.full(n, _NAN)

    pdh_sw_arr = np.zeros(n, dtype=bool)
    pdl_sw_arr = np.zeros(n, dtype=bool)

    # ── Running state ─────────────────────────────────────────────────────────
    cur_d_open = _NAN
    cur_w_open = _NAN
    cur_m_open = _NAN

    cur_pdh = _NAN
    cur_pdl = _NAN
    cur_pwh = _NAN
    cur_pwl = _NAN
    cur_pmh = _NAN
    cur_pml = _NAN

    cur_pdh_hit = False
    cur_pdl_hit = False
    cur_pwh_hit = False
    cur_pwl_hit = False
    cur_pmh_hit = False
    cur_pml_hit = False

    # Running H/L within each period (accumulate all bars, reset on boundary)
    run_d_h = _NAN
    run_d_lo = _NAN
    run_w_h = _NAN
    run_w_lo = _NAN
    run_m_h = _NAN
    run_m_lo = _NAN

    # PDH sweep state machine (per-day, reset on boundary)
    pdh_sw_phase = 0         # 0=watching, 1=breach seen, 2=confirmed, -1=expired
    pdh_sw_breach_ts = np.int64(-1)
    pdh_sw_done = False
    pdl_sw_phase = 0
    pdl_sw_breach_ts = np.int64(-1)
    pdl_sw_done = False

    # ── Forward pass ──────────────────────────────────────────────────────────
    for i in range(n):
        h = high[i]
        lo = low[i]
        cl = close_[i]
        op = open_[i]
        ts = ts_ms[i]

        is_day_bndry = (hours[i] == 0 and minutes_[i] == 0)
        is_week_bndry = is_day_bndry and (weekdays[i] == 0)   # Monday 00:00
        is_month_bndry = is_day_bndry and (days[i] == 1)       # 1st 00:00

        # ── Day boundary: fix PDH/PDL, reset running day H/L ─────────────────
        # ORDER MATTERS: fix from previous day FIRST, then reset for new day.
        if is_day_bndry:
            if not math.isnan(run_d_h):
                cur_pdh = run_d_h
                cur_pdl = run_d_lo
                cur_pdh_hit = False
                cur_pdl_hit = False
                # Reset PDH/PDL sweep for new day
                pdh_sw_phase = 0
                pdh_sw_breach_ts = np.int64(-1)
                pdh_sw_done = False
                pdl_sw_phase = 0
                pdl_sw_breach_ts = np.int64(-1)
                pdl_sw_done = False
            cur_d_open = op
            run_d_h = h      # new day starts with this bar
            run_d_lo = lo

        # ── Week boundary: fix PWH/PWL ────────────────────────────────────────
        if is_week_bndry:
            if not math.isnan(run_w_h):
                cur_pwh = run_w_h
                cur_pwl = run_w_lo
                cur_pwh_hit = False
                cur_pwl_hit = False
            cur_w_open = op
            run_w_h = h
            run_w_lo = lo

        # ── Month boundary: fix PMH/PML ───────────────────────────────────────
        if is_month_bndry:
            if not math.isnan(run_m_h):
                cur_pmh = run_m_h
                cur_pml = run_m_lo
                cur_pmh_hit = False
                cur_pml_hit = False
            cur_m_open = op
            run_m_h = h
            run_m_lo = lo

        # ── Update running H/L for non-boundary bars ──────────────────────────
        if not is_day_bndry:
            if math.isnan(run_d_h):
                run_d_h = h
                run_d_lo = lo
            else:
                if h > run_d_h:   run_d_h = h
                if lo < run_d_lo: run_d_lo = lo

        if not is_week_bndry:
            if math.isnan(run_w_h):
                run_w_h = h
                run_w_lo = lo
            else:
                if h > run_w_h:   run_w_h = h
                if lo < run_w_lo: run_w_lo = lo

        if not is_month_bndry:
            if math.isnan(run_m_h):
                run_m_h = h
                run_m_lo = lo
            else:
                if h > run_m_h:   run_m_h = h
                if lo < run_m_lo: run_m_lo = lo

        # ── Hit flags (cumulative within day/week/month) ──────────────────────
        if not math.isnan(cur_pdh):
            if h >= cur_pdh:  cur_pdh_hit = True
            if lo <= cur_pdl: cur_pdl_hit = True
        if not math.isnan(cur_pwh):
            if h >= cur_pwh:  cur_pwh_hit = True
            if lo <= cur_pwl: cur_pwl_hit = True
        if not math.isnan(cur_pmh):
            if h >= cur_pmh:  cur_pmh_hit = True
            if lo <= cur_pml: cur_pml_hit = True

        # ── PDH sweep (§11.4) — same-bar wick logic, Y=30 min ─────────────────
        if not math.isnan(cur_pdh):
            # PDH sweep: breach up, close returns below
            if pdh_sw_phase == 0:
                if h > cur_pdh:
                    if cl < cur_pdh:           # same-bar wick sweep
                        pdh_sw_done = True
                        pdh_sw_phase = 2
                    else:
                        pdh_sw_phase = 1
                        pdh_sw_breach_ts = ts
            elif pdh_sw_phase == 1:
                since = ts - pdh_sw_breach_ts
                if since <= _SWEEP_Y_MS:
                    if cl < cur_pdh:
                        pdh_sw_done = True
                        pdh_sw_phase = 2
                else:
                    pdh_sw_phase = -1

            # PDL sweep: breach down, close returns above
            if pdl_sw_phase == 0:
                if lo < cur_pdl:
                    if cl > cur_pdl:           # same-bar wick sweep
                        pdl_sw_done = True
                        pdl_sw_phase = 2
                    else:
                        pdl_sw_phase = 1
                        pdl_sw_breach_ts = ts
            elif pdl_sw_phase == 1:
                since = ts - pdl_sw_breach_ts
                if since <= _SWEEP_Y_MS:
                    if cl > cur_pdl:
                        pdl_sw_done = True
                        pdl_sw_phase = 2
                else:
                    pdl_sw_phase = -1

        # ── Write arrays ──────────────────────────────────────────────────────
        d_open_arr[i] = cur_d_open
        w_open_arr[i] = cur_w_open
        m_open_arr[i] = cur_m_open

        pdh_arr[i] = cur_pdh
        pdl_arr[i] = cur_pdl
        pwh_arr[i] = cur_pwh
        pwl_arr[i] = cur_pwl
        pmh_arr[i] = cur_pmh
        pml_arr[i] = cur_pml

        pdh_hit_arr[i] = cur_pdh_hit
        pdl_hit_arr[i] = cur_pdl_hit
        pwh_hit_arr[i] = cur_pwh_hit
        pwl_hit_arr[i] = cur_pwl_hit
        pmh_hit_arr[i] = cur_pmh_hit
        pml_hit_arr[i] = cur_pml_hit

        cur_d_high_arr[i] = run_d_h
        cur_d_low_arr[i] = run_d_lo

        pdh_sw_arr[i] = pdh_sw_done
        pdl_sw_arr[i] = pdl_sw_done

    # ── Distance features (vectorized) ────────────────────────────────────────
    # Convention: (level - close) / close × 100 for HIGH levels (positive = below)
    #             (close - level) / close × 100 for LOW  levels (positive = above)
    #             (close - open)  / open  × 100 for OPEN levels (positive = bullish)
    def dist_h(level: np.ndarray) -> np.ndarray:
        return (level - close_) / close_ * 100

    def dist_l(level: np.ndarray) -> np.ndarray:
        return (close_ - level) / close_ * 100

    def dist_o(level: np.ndarray) -> np.ndarray:
        return (close_ - level) / level * 100

    # ── Assign to output ──────────────────────────────────────────────────────
    out["d_open"] = d_open_arr
    out["w_open"] = w_open_arr
    out["m_open"] = m_open_arr

    out["pdh"] = pdh_arr
    out["pdl"] = pdl_arr
    out["pwh"] = pwh_arr
    out["pwl"] = pwl_arr
    out["pmh"] = pmh_arr
    out["pml"] = pml_arr

    out["pdh_hit"] = pdh_hit_arr
    out["pdl_hit"] = pdl_hit_arr
    out["pwh_hit"] = pwh_hit_arr
    out["pwl_hit"] = pwl_hit_arr
    out["pmh_hit"] = pmh_hit_arr
    out["pml_hit"] = pml_hit_arr

    out["current_d_high"] = cur_d_high_arr
    out["current_d_low"] = cur_d_low_arr

    out["pdh_sweep"] = pdh_sw_arr
    out["pdl_sweep"] = pdl_sw_arr

    out["dist_to_pdh_pct"] = dist_h(pdh_arr)
    out["dist_to_pdl_pct"] = dist_l(pdl_arr)
    out["dist_to_pwh_pct"] = dist_h(pwh_arr)
    out["dist_to_pwl_pct"] = dist_l(pwl_arr)
    out["dist_to_pmh_pct"] = dist_h(pmh_arr)
    out["dist_to_pml_pct"] = dist_l(pml_arr)
    out["dist_to_d_open_pct"] = dist_o(d_open_arr)
    out["dist_to_w_open_pct"] = dist_o(w_open_arr)
    out["dist_to_m_open_pct"] = dist_o(m_open_arr)

    out["dist_to_d_high_pct"] = dist_h(cur_d_high_arr)
    out["dist_to_d_low_pct"] = dist_l(cur_d_low_arr)

    return out
