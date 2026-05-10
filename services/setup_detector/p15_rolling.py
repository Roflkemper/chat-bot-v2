"""P-15 rolling-trend rebalance detector — TG signal generator.

Validated edge (tools/_backtest_p15_full.py 2026-05-08):
  TF=15m, R=0.3%, K=1.0%, dd_cap=3.0%
  PnL 2y BTC: +$67,463 SHORT  +$64,980 LONG
  PF: 4.32 / 4.37   Sharpe: 0.23   Walk-forward: 4/4 positive folds.

Strategy lifecycle (per direction, two parallel state machines):

  IDLE → wait for trend_gate trigger
    LONG:  EMA50 > EMA200 AND close > EMA50  (uptrend confirmed)
    SHORT: EMA50 < EMA200 AND close < EMA50  (downtrend confirmed)

  OPEN  → emit P15_*_OPEN setup; record avg_entry = close, extreme = close.

  TRACK → on each tick, update extreme (running_high for LONG, running_low
          for SHORT). No alert per-bar (signal-only, not noise).

  HARVEST → when retrace from extreme >= R%:
            close 50% of position at exit_price; emit P15_*_HARVEST.

  REENTRY → immediately after HARVEST: open new layer at K% offset
            (above for LONG / below for SHORT); emit P15_*_REENTRY.

  CLOSE  → when trend_gate flips OR cum_dd >= dd_cap_pct:
           close all remaining position; emit P15_*_CLOSE.
           dd_cap is emergency safety only.

State is persisted to state/p15_state.json across detector cycles. Two
independent state machines run in parallel (LONG and SHORT). They don't
know about each other — operator can run both legs simultaneously.

Telegram cards rendered by services/setup_detector/telegram_card.py via
the standard format_telegram_card(setup) path. Each card includes:
  - Direction (LONG/SHORT)
  - Stage (OPEN/HARVEST/REENTRY/CLOSE)
  - avg_entry, running_extreme, current_price
  - layer count, total_size_usd
  - exit_price (if HARVEST), reentry_price (if REENTRY)
  - dd_pct, P&L_estimate
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .models import (
    Setup,
    SetupBasis,
    SetupType,
    make_setup,
)
from .setup_types import DetectionContext

logger = logging.getLogger(__name__)

# ── Validated parameters from backtest_p15_full.py 2026-05-08 ─────────────────
P15_R_PCT = 0.3        # retrace from extreme to harvest
P15_K_PCT = 1.0        # reentry offset above/below harvest exit
P15_DD_CAP_PCT = 3.0   # emergency hard close
# 2026-05-10 TZ#8: time-stop if position held >MAX_HOLD_HOURS with cum_dd>1%
# AND no HARVEST event. Prevents stuck positions in slow grinds.
P15_MAX_HOLD_HOURS = 48.0
P15_TIME_STOP_DD_TRIGGER_PCT = 1.0
P15_BASE_SIZE_USD = 1000.0
# 2026-05-10 TZ#9: margin-aware sizing — scale base size to % of operator's
# total deposit. Cap at 8 layers (after 7 reentries it's 8x size). At
# typical $15k depo, P15_PCT_OF_DEPO=6.5% gives base $1000, max $8000 = 53%
# of depo — leaves headroom for grid bots.
P15_PCT_OF_DEPO = 6.5  # base size = ADVISOR_DEPO_TOTAL × this / 100
P15_MIN_BASE_USD = 500.0

# 2026-05-10 TZ-1: per-pair sizing factor. Backtest PFs (BTC 3.84/3.91 vs
# XRP 3.48/3.04 vs ETH 3.36/3.39) say BTC is the strongest edge — give it
# full size; alts get reduced. Also reflects spread/slippage: XRP smaller
# market depth, less liquidity at midprice. Six potential open legs (3
# pairs × 2 dirs) → without scaling we'd over-allocate to alts.
P15_PAIR_SIZE_FACTOR = {
    "BTCUSDT": 1.0,
    "ETHUSDT": 0.5,
    "XRPUSDT": 0.3,
}

# 2026-05-10 TZ-1: cross-asset correlation cap. If 2 pairs already open in
# the same direction, refuse OPEN on the 3rd — they're highly correlated,
# would be 3x the same risk under one regime. Counted across BTC/ETH/XRP.
P15_MAX_SAME_DIRECTION_LEGS = 2


def _resolve_base_size_usd(pair: str = "BTCUSDT") -> float:
    """Read ADVISOR_DEPO_TOTAL at runtime, scale base size. Fall back to fixed.

    Pair factor adjusts for relative edge strength / market depth.
    """
    factor = P15_PAIR_SIZE_FACTOR.get(pair, 0.5)
    try:
        from config import ADVISOR_DEPO_TOTAL
        depo = float(ADVISOR_DEPO_TOTAL or 0)
        if depo > 0:
            sized = depo * P15_PCT_OF_DEPO / 100.0 * factor
            return max(P15_MIN_BASE_USD * factor, sized)
    except Exception:
        pass
    return P15_BASE_SIZE_USD * factor


def _count_same_direction_open_legs(state: dict, direction: str,
                                     except_pair: str | None = None) -> int:
    """Count how many legs are currently open in the given direction
    across all pairs, optionally excluding one pair."""
    n = 0
    for key, leg in state.items():
        if not leg.in_pos:
            continue
        try:
            pair, dir_ = key.split(":", 1)
        except ValueError:
            continue
        if except_pair is not None and pair == except_pair:
            continue
        if dir_ == direction:
            n += 1
    return n


P15_MAX_LAYERS = 10

P15_STATE_PATH = Path("state/p15_state.json")
# 2026-05-10 TZ#2: equity curve writer. Each CLOSE/HARVEST event appends
# one line. Used by edge_tracker + future analytics.
P15_EQUITY_PATH = Path("state/p15_equity.jsonl")


def _append_equity_event(event: dict) -> None:
    """Best-effort append. Never blocks detector path."""
    try:
        P15_EQUITY_PATH.parent.mkdir(parents=True, exist_ok=True)
        with P15_EQUITY_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, default=str) + "\n")
    except OSError:
        logger.exception("p15_rolling.equity_write_failed")


@dataclass
class _LegState:
    """Persistent state for one direction's P-15 cycle."""
    direction: str                   # "long" or "short"
    in_pos: bool = False
    layers: int = 0
    total_size_usd: float = 0.0
    weighted_entry: float = 0.0      # sum(entry_i * size_i)
    extreme_price: float = 0.0       # running_high (long) / running_low (short)
    last_extreme_ts: str = ""
    opened_at_ts: str = ""
    cum_dd_pct: float = 0.0
    last_emitted_stage: str = ""     # "OPEN" / "HARVEST" / "REENTRY" / "CLOSE" / ""
    last_emitted_ts: str = ""

    @property
    def avg_entry(self) -> float:
        if self.total_size_usd == 0:
            return 0.0
        return self.weighted_entry / self.total_size_usd

    def to_dict(self) -> dict:
        return {
            "direction": self.direction,
            "in_pos": self.in_pos,
            "layers": self.layers,
            "total_size_usd": self.total_size_usd,
            "weighted_entry": self.weighted_entry,
            "extreme_price": self.extreme_price,
            "last_extreme_ts": self.last_extreme_ts,
            "opened_at_ts": self.opened_at_ts,
            "cum_dd_pct": self.cum_dd_pct,
            "last_emitted_stage": self.last_emitted_stage,
            "last_emitted_ts": self.last_emitted_ts,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "_LegState":
        return cls(
            direction=raw.get("direction", "long"),
            in_pos=bool(raw.get("in_pos", False)),
            layers=int(raw.get("layers", 0)),
            total_size_usd=float(raw.get("total_size_usd", 0.0)),
            weighted_entry=float(raw.get("weighted_entry", 0.0)),
            extreme_price=float(raw.get("extreme_price", 0.0)),
            last_extreme_ts=str(raw.get("last_extreme_ts", "")),
            opened_at_ts=str(raw.get("opened_at_ts", "")),
            cum_dd_pct=float(raw.get("cum_dd_pct", 0.0)),
            last_emitted_stage=str(raw.get("last_emitted_stage", "")),
            last_emitted_ts=str(raw.get("last_emitted_ts", "")),
        )


def _state_key(pair: str, direction: str) -> str:
    return f"{pair}:{direction}"


def _load_state() -> dict[str, _LegState]:
    """Multi-pair state: keys are 'BTCUSDT:long', 'ETHUSDT:short', etc."""
    if not P15_STATE_PATH.exists():
        return {}
    try:
        raw = json.loads(P15_STATE_PATH.read_text(encoding="utf-8"))
        out: dict[str, _LegState] = {}
        for k, v in raw.items():
            if isinstance(v, dict):
                out[k] = _LegState.from_dict(v)
        return out
    except (OSError, ValueError, json.JSONDecodeError):
        logger.exception("p15.state_load_failed; resetting")
        return {}


def _save_state(state: dict[str, _LegState]) -> None:
    try:
        P15_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        P15_STATE_PATH.write_text(
            json.dumps({k: v.to_dict() for k, v in state.items()},
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        logger.exception("p15.state_save_failed")


def _get_or_create(state: dict, pair: str, direction: str) -> _LegState:
    k = _state_key(pair, direction)
    if k not in state:
        state[k] = _LegState(direction=direction)
    return state[k]


def _ema(values: list[float], n: int) -> float:
    """Compute final EMA value from a list. Skip if too short."""
    if len(values) < n:
        return values[-1] if values else 0.0
    k = 2.0 / (n + 1)
    e = sum(values[:n]) / n
    for v in values[n:]:
        e = v * k + e * (1 - k)
    return e


def _trend_gate(closes_1h: list[float], direction: str) -> bool:
    if len(closes_1h) < 200:
        return False
    e50 = _ema(closes_1h[-220:], 50)
    e200 = _ema(closes_1h[-220:], 200)
    last = closes_1h[-1]
    if direction == "long":
        return e50 > e200 and last > e50
    return e50 < e200 and last < e50


def _build_setup(
    *,
    setup_type: SetupType,
    ctx: DetectionContext,
    leg: _LegState,
    stage_payload: dict,
) -> Setup:
    """Build a Setup with full P-15 context as basis fields."""
    direction = leg.direction
    is_long = direction == "long"

    avg = leg.avg_entry
    cur = ctx.current_price
    pnl_pct = ((cur - avg) / avg) if avg > 0 and is_long else \
              ((avg - cur) / avg) if avg > 0 else 0.0
    unrealized_usd = leg.total_size_usd * pnl_pct

    basis = (
        SetupBasis(label="direction", value=direction, weight=0.0),
        SetupBasis(label="stage", value=stage_payload.get("stage", ""), weight=0.0),
        SetupBasis(label="avg_entry", value=round(avg, 2), weight=0.0),
        SetupBasis(label="extreme", value=round(leg.extreme_price, 2), weight=0.0),
        SetupBasis(label="layers", value=leg.layers, weight=0.0),
        SetupBasis(label="total_size_usd", value=round(leg.total_size_usd, 0), weight=0.0),
        SetupBasis(label="dd_pct", value=round(leg.cum_dd_pct, 2), weight=0.0),
        SetupBasis(label="unrealized_usd", value=round(unrealized_usd, 2), weight=0.0),
        SetupBasis(label="R_pct", value=P15_R_PCT, weight=0.0),
        SetupBasis(label="K_pct", value=P15_K_PCT, weight=0.0),
        *[SetupBasis(label=k, value=v, weight=0.0)
          for k, v in stage_payload.items() if k != "stage"],
    )

    # Cancel conditions vary by stage
    stage = stage_payload.get("stage", "")
    if stage == "OPEN":
        cancel = (
            f"trend gate flips ({'EMA50<EMA200' if is_long else 'EMA50>EMA200'})",
            f"cum_dd >= {P15_DD_CAP_PCT}% (emergency close)",
            f"manual /p15_close_{direction}",
        )
    elif stage == "HARVEST":
        cancel = (
            f"price did not pull back R={P15_R_PCT}% from extreme",
            "harvest already executed this cycle",
        )
    elif stage == "REENTRY":
        cancel = (
            "no harvest in current cycle",
            "trend already flipped",
        )
    elif stage == "CLOSE":
        cancel = ("position already closed",)
    else:
        cancel = ()

    portfolio_note = (
        f"P-15 leg={direction.upper()} layer={leg.layers} "
        f"avg=${avg:,.0f} now=${cur:,.0f} "
        f"unrealized={unrealized_usd:+,.1f}$"
    )

    return make_setup(
        setup_type=setup_type,
        pair=ctx.pair,
        current_price=cur,
        regime_label=ctx.regime_label,
        session_label=ctx.session_label,
        entry_price=cur,
        stop_price=None,  # P-15 has no fixed stop, only dd_cap
        tp1_price=None,
        tp2_price=None,
        risk_reward=None,
        strength=8,
        confidence_pct=70.0,
        basis=basis,
        cancel_conditions=cancel,
        window_minutes=240,
        portfolio_impact_note=portfolio_note,
        recommended_size_btc=0.0,
    )


def _detect_one_direction(ctx: DetectionContext, leg: _LegState,
                           closes_1h: list[float], now_iso: str,
                           all_legs: dict[str, "_LegState"] | None = None,
                           ) -> Optional[Setup]:
    """Run the state machine for one direction (long or short).

    `all_legs` is the cross-pair state map ({"BTCUSDT:long": _LegState, ...})
    used for cross-asset correlation cap on OPEN.

    Returns a Setup to emit (the new stage transition), or None if no change.
    Mutates `leg` in-place.
    """
    direction = leg.direction
    is_long = direction == "long"
    cur = ctx.current_price
    bars_15m = ctx.ohlcv_15m if ctx.ohlcv_15m is not None else None

    if bars_15m is None or len(bars_15m) < 50:
        return None

    high_now = float(bars_15m["high"].iloc[-1])
    low_now = float(bars_15m["low"].iloc[-1])

    gate = _trend_gate(closes_1h, direction)

    # IDLE → check for OPEN trigger
    if not leg.in_pos:
        if gate:
            # 2026-05-10 TZ-1: cross-asset correlation cap. Refuse OPEN if
            # ≥MAX_SAME_DIRECTION_LEGS already open in this direction across
            # other pairs — BTC/ETH/XRP are highly correlated, 3 same-side
            # legs would be 3x the same regime risk.
            current_pair = getattr(ctx, "pair", "BTCUSDT")
            n_same_dir = _count_same_direction_open_legs(
                all_legs or {}, direction, except_pair=current_pair,
            )
            if n_same_dir >= P15_MAX_SAME_DIRECTION_LEGS:
                logger.info(
                    "p15_rolling.open_blocked pair=%s dir=%s reason=correlation "
                    "(already %d legs open same direction)",
                    current_pair, direction, n_same_dir,
                )
                return None

            leg.in_pos = True
            leg.layers = 1
            base_size = _resolve_base_size_usd(current_pair)
            leg.total_size_usd = base_size
            leg.weighted_entry = cur * base_size
            leg.extreme_price = cur
            leg.opened_at_ts = now_iso
            leg.cum_dd_pct = 0.0
            leg.last_emitted_stage = "OPEN"
            leg.last_emitted_ts = now_iso
            # Equity curve event (2026-05-10 TZ#2)
            _append_equity_event({
                "ts": now_iso,
                "pair": current_pair,
                "direction": direction,
                "stage": "OPEN",
                "open_price": round(cur, 2),
                "size_usd": round(base_size, 2),
                "layers": 1,
            })
            stype = SetupType.P15_LONG_OPEN if is_long else SetupType.P15_SHORT_OPEN
            return _build_setup(
                setup_type=stype, ctx=ctx, leg=leg,
                stage_payload={
                    "stage": "OPEN",
                    "trigger": f"EMA50{'>' if is_long else '<'}EMA200 & close{'>' if is_long else '<'}EMA50",
                    "open_price": round(cur, 2),
                    "size_usd": base_size,
                },
            )
        return None

    # IN POSITION — update extreme + dd
    avg = leg.avg_entry
    if is_long:
        leg.extreme_price = max(leg.extreme_price, high_now)
        adverse_pct = (avg - low_now) / avg * 100.0 if avg > 0 else 0.0
        retrace_pct = (leg.extreme_price - low_now) / leg.extreme_price * 100.0 \
                      if leg.extreme_price > 0 else 0.0
        exit_price = leg.extreme_price * (1 - P15_R_PCT / 100.0)
        reentry_price = exit_price * (1 + P15_K_PCT / 100.0)
    else:
        leg.extreme_price = min(leg.extreme_price, low_now) if leg.extreme_price > 0 else low_now
        adverse_pct = (high_now - avg) / avg * 100.0 if avg > 0 else 0.0
        retrace_pct = (high_now - leg.extreme_price) / leg.extreme_price * 100.0 \
                      if leg.extreme_price > 0 else 0.0
        exit_price = leg.extreme_price * (1 + P15_R_PCT / 100.0)
        reentry_price = exit_price * (1 - P15_K_PCT / 100.0)

    leg.cum_dd_pct = max(leg.cum_dd_pct, adverse_pct)
    leg.last_extreme_ts = now_iso

    # CLOSE: dd_cap, gate flip, or time-stop (2026-05-10 TZ#8)
    close_reason: Optional[str] = None
    if leg.cum_dd_pct >= P15_DD_CAP_PCT:
        close_reason = f"dd_cap {P15_DD_CAP_PCT}% breached"
    elif not gate:
        close_reason = f"trend gate flipped (EMA50{'<' if is_long else '>'}EMA200)"
    elif leg.opened_at_ts and leg.last_emitted_stage in ("OPEN", "REENTRY"):
        # Stuck check: position held > MAX_HOLD_HOURS AND in drawdown but
        # never harvested (cum_dd > trigger but < dd_cap).
        try:
            opened_ts = datetime.fromisoformat(leg.opened_at_ts.replace("Z", "+00:00"))
            now_dt = datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
            held_hours = (now_dt - opened_ts).total_seconds() / 3600
            if (held_hours >= P15_MAX_HOLD_HOURS and
                leg.cum_dd_pct >= P15_TIME_STOP_DD_TRIGGER_PCT):
                close_reason = (f"time-stop {held_hours:.1f}h held with "
                               f"dd={leg.cum_dd_pct:.2f}% >= "
                               f"{P15_TIME_STOP_DD_TRIGGER_PCT}%")
        except (ValueError, AttributeError):
            pass

    if close_reason is not None:
        pnl_pct = ((cur - avg) / avg) if is_long else ((avg - cur) / avg)
        pnl_usd = leg.total_size_usd * pnl_pct
        stype = SetupType.P15_LONG_CLOSE if is_long else SetupType.P15_SHORT_CLOSE
        s = _build_setup(
            setup_type=stype, ctx=ctx, leg=leg,
            stage_payload={
                "stage": "CLOSE",
                "reason": close_reason,
                "close_price": round(cur, 2),
                "realized_pnl_usd": round(pnl_usd, 2),
            },
        )
        # Equity curve event (2026-05-10 TZ#2)
        _append_equity_event({
            "ts": now_iso,
            "pair": getattr(ctx, "pair", "BTCUSDT"),
            "direction": direction,
            "stage": "CLOSE",
            "reason": close_reason,
            "open_ts": leg.opened_at_ts,
            "avg_entry": round(avg, 2),
            "close_price": round(cur, 2),
            "qty_size_usd": round(leg.total_size_usd, 2),
            "layers": leg.layers,
            "cum_dd_pct": round(leg.cum_dd_pct, 2),
            "realized_pnl_usd": round(pnl_usd, 2),
        })
        # Reset state
        leg.in_pos = False
        leg.layers = 0
        leg.total_size_usd = 0.0
        leg.weighted_entry = 0.0
        leg.extreme_price = 0.0
        leg.cum_dd_pct = 0.0
        leg.last_emitted_stage = "CLOSE"
        leg.last_emitted_ts = now_iso
        return s

    # HARVEST: retrace >= R% AND we haven't already emitted HARVEST at this extreme
    # Simple guard: only fire if last_emitted_stage in (OPEN, REENTRY) — i.e. we're
    # in the "growing" phase, not the "just harvested, waiting for next cycle" phase.
    if retrace_pct >= P15_R_PCT and leg.last_emitted_stage in ("OPEN", "REENTRY"):
        if leg.layers < P15_MAX_LAYERS:
            harvest_size = leg.total_size_usd * 0.5
            harvest_pnl_pct = ((exit_price - avg) / avg) if is_long else ((avg - exit_price) / avg)
            harvest_pnl_usd = harvest_size * harvest_pnl_pct
            stype = SetupType.P15_LONG_HARVEST if is_long else SetupType.P15_SHORT_HARVEST
            s = _build_setup(
                setup_type=stype, ctx=ctx, leg=leg,
                stage_payload={
                    "stage": "HARVEST",
                    "exit_price": round(exit_price, 2),
                    "harvest_size_usd": round(harvest_size, 0),
                    "harvest_pnl_usd": round(harvest_pnl_usd, 2),
                    "next_reentry_price": round(reentry_price, 2),
                },
            )
            # Equity curve event (2026-05-10 TZ#2)
            _append_equity_event({
                "ts": now_iso,
                "pair": getattr(ctx, "pair", "BTCUSDT"),
                "direction": direction,
                "stage": "HARVEST",
                "open_ts": leg.opened_at_ts,
                "avg_entry": round(avg, 2),
                "exit_price": round(exit_price, 2),
                "harvest_size_usd": round(harvest_size, 0),
                "realized_pnl_usd": round(harvest_pnl_usd, 2),
                "layers": leg.layers,
            })
            # Mutate state: realize half, prepare for reentry
            reentry_size = _resolve_base_size_usd(getattr(ctx, "pair", "BTCUSDT"))
            leg.total_size_usd -= harvest_size
            leg.weighted_entry -= avg * harvest_size
            leg.weighted_entry += reentry_price * reentry_size
            leg.total_size_usd += reentry_size
            leg.layers += 1
            leg.extreme_price = reentry_price
            leg.last_emitted_stage = "HARVEST"
            leg.last_emitted_ts = now_iso
            return s

    # REENTRY: emitted as a separate stage card right after HARVEST.
    # Detected by transition: last stage was HARVEST, position is healthy, gate still on.
    # 2026-05-11 fix: reentry_size was defined inside the HARVEST branch above and
    # was out of scope when REENTRY ran on the next tick. UnboundLocalError fired
    # 131x in 24h until found via daily KPI. Now: re-resolve from pair.
    if leg.last_emitted_stage == "HARVEST":
        reentry_size_repo = _resolve_base_size_usd(getattr(ctx, "pair", "BTCUSDT"))
        stype = SetupType.P15_LONG_REENTRY if is_long else SetupType.P15_SHORT_REENTRY
        s = _build_setup(
            setup_type=stype, ctx=ctx, leg=leg,
            stage_payload={
                "stage": "REENTRY",
                "reentry_price": round(leg.extreme_price, 2),
                "new_avg_entry": round(avg, 2),
                "new_layer_size_usd": reentry_size_repo,
                "next_target_extreme_pct": f"+{P15_R_PCT}% from now",
            },
        )
        leg.last_emitted_stage = "REENTRY"
        leg.last_emitted_ts = now_iso
        return s

    return None


def detect_p15_long(ctx: DetectionContext) -> Optional[Setup]:
    """LONG-leg detector. Emits P15_LONG_* setups across the lifecycle."""
    return _detect_p15(ctx, "long")


def detect_p15_short(ctx: DetectionContext) -> Optional[Setup]:
    """SHORT-leg detector. Emits P15_SHORT_* setups across the lifecycle."""
    return _detect_p15(ctx, "short")


P15_VALIDATED_PAIRS = {"BTCUSDT", "ETHUSDT", "XRPUSDT"}


def _detect_p15(ctx: DetectionContext, direction: str) -> Optional[Setup]:
    if ctx.pair not in P15_VALIDATED_PAIRS:
        return None  # validated 2026-05-09 on BTC/ETH/XRP, all 6/6 PF>3, 4/4 folds
    if ctx.ohlcv_1h is None or len(ctx.ohlcv_1h) < 200:
        return None

    closes_1h = ctx.ohlcv_1h["close"].astype(float).tolist()
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    state = _load_state()
    leg = _get_or_create(state, ctx.pair, direction)
    setup = _detect_one_direction(ctx, leg, closes_1h, now_iso, all_legs=state)
    _save_state(state)
    return setup
