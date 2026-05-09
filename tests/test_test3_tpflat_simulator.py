"""Unit tests for services.test3_tpflat_simulator.

Tests the state machine:
  - OPEN fires when SHORT gate True and no position
  - no OPEN when gate False
  - CLOSE_TP fires when low touches tp price
  - CLOSE_FORCED fires when adverse_pct >= dd_cap
  - extreme tracker updates correctly
  - PnL math (gross - 2 fees) for both close types
"""
from __future__ import annotations

from services.test3_tpflat_simulator import loop as sim


def _gate_closes_short() -> list[float]:
    """Build 250 closes where EMA50>EMA200 and last>EMA50 → SHORT gate True."""
    # rising linearly: EMA50 of recent will be > EMA200 of older
    base = list(range(70000, 70000 + 250))
    return [float(x) for x in base]


def _gate_closes_no() -> list[float]:
    """Flat closes — gate False (e50 ~ e200)."""
    return [70000.0] * 250


def test_open_fires_on_short_gate(monkeypatch, tmp_path):
    monkeypatch.setattr(sim, "JOURNAL_PATH", tmp_path / "journal.jsonl")
    monkeypatch.setattr(sim, "STATE_PATH", tmp_path / "state.json")
    state = sim._State()
    closes = _gate_closes_short()
    sim._check_and_act(closes, current_price=70300.0, high_now=70320.0,
                       low_now=70280.0, state=state)
    assert state.in_pos
    assert state.entry == 70300.0
    assert state.extreme == 70300.0
    assert state.volume_usd == sim.BASE_SIZE_USD


def test_no_open_when_gate_false(monkeypatch, tmp_path):
    monkeypatch.setattr(sim, "JOURNAL_PATH", tmp_path / "j.jsonl")
    state = sim._State()
    sim._check_and_act(_gate_closes_no(), 70000.0, 70010.0, 69990.0, state)
    assert not state.in_pos
    assert state.volume_usd == 0.0


def test_close_tp_fires_when_low_touches_tp(monkeypatch, tmp_path):
    monkeypatch.setattr(sim, "JOURNAL_PATH", tmp_path / "j.jsonl")
    state = sim._State(in_pos=True, entry=70000.0, extreme=70000.0, volume_usd=1000.0)
    # tp_price = 70000 * (1 - 10/1000) = 69300
    sim._check_and_act(_gate_closes_short(), current_price=69500.0,
                       high_now=70050.0, low_now=69299.0, state=state)
    assert not state.in_pos
    assert state.n_tp == 1
    # PnL ≈ 10$ - fees(2*0.5 = 1$) = ~$9
    assert 8.0 < state.realized_pnl_usd < 10.0
    assert state.volume_usd == 2000.0  # open + close


def test_close_forced_when_adverse_exceeds_dd_cap(monkeypatch, tmp_path):
    monkeypatch.setattr(sim, "JOURNAL_PATH", tmp_path / "j.jsonl")
    state = sim._State(in_pos=True, entry=70000.0, extreme=70000.0, volume_usd=1000.0)
    # adverse pct = (high-entry)/entry. high=72200 → 3.14% > 3% cap
    sim._check_and_act(_gate_closes_short(), current_price=72100.0,
                       high_now=72200.0, low_now=72050.0, state=state)
    assert not state.in_pos
    assert state.n_forced == 1
    # PnL: SHORT, exit at 72100, entry 70000 → gross loss
    # gross = (70000-72100)/70000 * 1000 = -30$, fees -1$, total ≈ -31$
    assert state.realized_pnl_usd < -30.0


def test_extreme_tracker_updates(monkeypatch, tmp_path):
    monkeypatch.setattr(sim, "JOURNAL_PATH", tmp_path / "j.jsonl")
    state = sim._State(in_pos=True, entry=70000.0, extreme=70100.0)
    sim._check_and_act(_gate_closes_short(), current_price=70200.0,
                       high_now=70500.0, low_now=70150.0, state=state)
    assert state.extreme == 70500.0
    # new high but no tp/dd → still in pos
    assert state.in_pos


def test_no_close_when_neither_tp_nor_dd(monkeypatch, tmp_path):
    monkeypatch.setattr(sim, "JOURNAL_PATH", tmp_path / "j.jsonl")
    state = sim._State(in_pos=True, entry=70000.0, extreme=70000.0)
    sim._check_and_act(_gate_closes_short(), current_price=70050.0,
                       high_now=70100.0, low_now=69900.0, state=state)
    assert state.in_pos
    assert state.n_tp == 0
    assert state.n_forced == 0
