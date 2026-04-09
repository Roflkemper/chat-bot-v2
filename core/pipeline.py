from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
from typing import Any, Dict, List, Tuple

from market_data.price_feed import get_price
from market_data.ohlcv import get_klines
from services.timeframe_aggregator import aggregate_to_4h, aggregate_to_1d
from features.trigger_detection import detect_trigger
from features.forecast import short_term_forecast, session_forecast, medium_forecast, build_consensus
from utils.safe_io import atomic_write_json, safe_read_json, ensure_parent_dir

NEAR_EDGE_THRESHOLD_PCT = 15.0
HEDGE_BUFFER_USD = 293.0
USE_LAST_N_TRADES = 50
SIGNAL_THROTTLE_SECONDS = 300
JOURNAL_DIR = Path("storage/journal")
SIGNAL_JOURNAL_FILE = JOURNAL_DIR / "signal_journal.jsonl"
TRADE_OUTCOMES_FILE = JOURNAL_DIR / "trade_outcomes.jsonl"
SETUP_STATS_FILE = JOURNAL_DIR / "setup_stats.json"
SIGNAL_CACHE_FILE = JOURNAL_DIR / "signal_cache.json"
PROJECT_VERSION_FILE = Path("VERSION.txt")


def _depth_label(depth_pct: float) -> str:
    if depth_pct < 15:
        return "EARLY"
    if depth_pct < 50:
        return "WORK"
    if depth_pct < 85:
        return "RISK"
    return "DEEP"


def _build_range(candles_1h):
    window = candles_1h[-48:] if len(candles_1h) >= 48 else candles_1h
    range_low = min(x["low"] for x in window)
    range_high = max(x["high"] for x in window)
    range_mid = (range_low + range_high) / 2.0
    return range_low, range_high, range_mid


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_jsonl(path: Path, row: Dict[str, Any]) -> None:
    ensure_parent_dir(str(path))
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def _atr(candles: List[Dict[str, Any]], period: int = 14) -> float:
    if len(candles) < 2:
        return 50.0
    trs: List[float] = []
    for i in range(1, len(candles)):
        cur = candles[i]
        prev = candles[i - 1]
        high = _safe_float(cur.get("high"))
        low = _safe_float(cur.get("low"))
        prev_close = _safe_float(prev.get("close"), high)
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    sample = trs[-period:] if trs else [50.0]
    return round(sum(sample) / max(len(sample), 1), 2)


def _close_direction(bar: Dict[str, Any]) -> str:
    op = _safe_float(bar.get("open"))
    cl = _safe_float(bar.get("close"))
    if cl > op:
        return "LONG"
    if cl < op:
        return "SHORT"
    return "NEUTRAL"


def _context_details(candles_1h: List[Dict[str, Any]], depth_label: str, scalp_direction: str, active_side: str) -> Tuple[int, str, List[str]]:
    details: List[str] = []
    score = 0
    if depth_label in ("EARLY", "WORK"):
        score += 1
        details.append("depth ok")
    if scalp_direction == active_side:
        score += 1
        details.append("scalp aligned")
    recent = candles_1h[-3:] if len(candles_1h) >= 3 else candles_1h
    aligned_bars = sum(1 for bar in recent if _close_direction(bar) == active_side)
    if aligned_bars >= 2:
        score += 1
        details.append("2/3 bars aligned")
    label = {3: "STRONG CONTEXT", 2: "VALID CONTEXT", 1: "WEAK CONTEXT", 0: "NO CONTEXT"}.get(score, "NO CONTEXT")
    return score, label, details


def _consensus_alignment(votes: Any) -> int:
    try:
        return int(votes)
    except Exception:
        return 0


def _block_pressure(active_side: str, consensus_direction: str, consensus_votes: int, session_fc: Dict[str, Any], medium_fc: Dict[str, Any]) -> Tuple[str, str, bool, str]:
    session_against = str(session_fc.get("direction") or "").upper() not in {"", "NEUTRAL", active_side}
    session_high = session_against and str(session_fc.get("strength") or "").upper() == "HIGH"
    medium_against = str(medium_fc.get("direction") or "").upper() not in {"", "NEUTRAL", active_side}
    medium_phase = str(medium_fc.get("phase") or "").upper()
    medium_trend_phase = medium_phase in {"MARKUP", "MARKDOWN"} and medium_against
    against = consensus_direction in {"LONG", "SHORT"} and consensus_direction != active_side
    with_block = consensus_direction == active_side and consensus_votes >= 2
    if against and consensus_votes == 3 and (session_high or medium_trend_phase):
        return "AGAINST", "HIGH", True, "все ТФ против активного блока — давление на смену зоны"
    if against and consensus_votes == 3:
        return "AGAINST", "MID", True, "все ТФ против активного блока"
    if against and consensus_votes >= 2 and medium_against:
        return "AGAINST", "LOW", True, "среднесрок и большинство ТФ против блока"
    if with_block:
        return "WITH", "MID" if consensus_votes == 2 else "HIGH", False, "консенсус поддерживает активный блок"
    return "NONE", "LOW", False, ""


def _setup_key(active_side: str, trigger_code: str, depth_label: str, context_label: str) -> str:
    return f"{active_side}_{trigger_code or 'NONE'}_{depth_label}_{context_label.split()[0]}"


def _load_feedback_stats(mode: str, setup_key: str) -> Dict[str, Any]:
    rows = [r for r in _read_jsonl(TRADE_OUTCOMES_FILE) if str(r.get("mode")) == mode and str(r.get("setup_key")) == setup_key]
    rows = rows[-USE_LAST_N_TRADES:]
    if not rows:
        return {"count_total": 0}
    wins = 0
    losses = 0
    invalidated = 0
    flip_exit = 0
    be_saved = 0
    r_values: List[float] = []
    for row in rows:
        rr = _safe_float(row.get("result_r"), 0.0)
        r_values.append(rr)
        status = str(row.get("result_status") or "").upper()
        if status == "WIN" or rr > 0:
            wins += 1
        elif status in {"LOSS", "INVALIDATED"} or rr < 0:
            losses += 1
        if status == "INVALIDATED":
            invalidated += 1
        if bool(row.get("flip_exit")):
            flip_exit += 1
        if bool(row.get("be_saved")):
            be_saved += 1
    count_total = len(rows)
    avg_result_r = round(sum(r_values) / max(count_total, 1), 4)
    win_rate = round(wins / max(count_total, 1), 4)
    loss_rate = round(losses / max(count_total, 1), 4)
    flip_exit_rate = round(flip_exit / max(count_total, 1), 4)
    be_saved_rate = round(be_saved / max(count_total, 1), 4)
    return {
        "count_total": count_total,
        "avg_result_r": avg_result_r,
        "win_rate": win_rate,
        "loss_rate": loss_rate,
        "flip_exit_rate": flip_exit_rate,
        "be_saved_rate": be_saved_rate,
        "invalidated_count": invalidated,
    }


def _feedback_from_stats(stats: Dict[str, Any], block_pressure: str, block_pressure_strength: str, raw_quality: str) -> Dict[str, Any]:
    count_total = int(stats.get("count_total") or 0)
    if count_total < 10:
        return {"history": "INSUFFICIENT DATA", "delta": 0, "confidence": "LOW", "note": "недостаточно наблюдений"}
    avg_r = _safe_float(stats.get("avg_result_r"), 0.0)
    win_rate = _safe_float(stats.get("win_rate"), 0.0)
    loss_rate = _safe_float(stats.get("loss_rate"), 0.0)
    flip_exit_rate = _safe_float(stats.get("flip_exit_rate"), 0.0)
    confidence = "LOW" if count_total < 20 else "MID" if count_total < 40 else "HIGH"
    delta = 0
    history = "NEUTRAL"
    note = "история сетапа смешанная"
    if avg_r <= -0.25 and (loss_rate > max(win_rate, 0.45) or flip_exit_rate >= 0.3):
        delta = -1
        history = "NEGATIVE"
        note = "исторически такой сетап часто даёт слабый результат"
    elif avg_r >= 0.25 and win_rate >= 0.55 and flip_exit_rate < 0.25:
        delta = 1
        history = "POSITIVE"
        note = "сетап статистически устойчив"
    if block_pressure == "AGAINST":
        if block_pressure_strength == "HIGH":
            delta = min(delta, 0)
        elif block_pressure_strength == "MID":
            if delta > 0:
                delta = 1
        elif block_pressure_strength == "LOW":
            pass
    return {"history": history, "delta": delta, "confidence": confidence, "note": note}


def _adjust_quality(raw_quality: str, feedback_delta: int, block_pressure: str, block_pressure_strength: str) -> str:
    order = ["NO_TRADE", "C", "B", "A"]
    idx = order.index(raw_quality) if raw_quality in order else 0
    if feedback_delta > 0:
        idx = min(idx + 1, len(order) - 1)
        if block_pressure == "AGAINST" and block_pressure_strength == "MID":
            idx = min(idx, order.index("B"))
    elif feedback_delta < 0:
        idx = max(idx - 1, 0)
    return order[idx]


def _entry_quality_and_profile(action: str, context_score: int, depth_label: str, trigger_detected: bool, trigger_confirmed: bool,
                               trigger_blocked: bool, forecast_relation: str, block_pressure: str, block_pressure_strength: str) -> Tuple[str, str, str, bool, bool]:
    if action == "WAIT" or trigger_blocked or context_score == 0 or not trigger_detected:
        return "NO_TRADE", "NO_ENTRY", "MINIMAL", False, False
    if trigger_confirmed and context_score == 3 and depth_label in ("EARLY", "WORK") and forecast_relation == "ALIGNED" and block_pressure != "AGAINST":
        quality = "A"
    elif context_score >= 2 and depth_label in ("EARLY", "WORK"):
        quality = "B"
    else:
        quality = "C"

    if quality == "A" and context_score == 3 and depth_label in ("EARLY", "WORK") and forecast_relation == "ALIGNED":
        profile = "AGGRESSIVE"
    elif forecast_relation == "NEUTRAL" and quality in {"A", "B"}:
        profile = "STANDARD"
    elif forecast_relation == "AGAINST":
        profile = "CONSERVATIVE" if quality in {"A", "B"} else "PROBE_ONLY"
    elif quality == "B":
        profile = "STANDARD"
    else:
        profile = "PROBE_ONLY"

    if block_pressure == "AGAINST" and block_pressure_strength == "HIGH":
        profile = "PROBE_ONLY" if quality != "NO_TRADE" else "NO_ENTRY"
    risk_mode = "FULL" if profile == "AGGRESSIVE" else "REDUCED" if profile in {"STANDARD", "CONSERVATIVE"} else "MINIMAL"
    partial_entry_allowed = quality in {"B", "C"}
    scale_in_allowed = depth_label not in {"RISK", "DEEP"}
    if quality == "C":
        scale_in_allowed = False
    return quality, profile, risk_mode, partial_entry_allowed, scale_in_allowed


def _trade_plan(snapshot: Dict[str, Any], candles_1h: List[Dict[str, Any]], execution_profile: str, final_quality: str) -> Dict[str, Any]:
    mode = "GRID" if snapshot.get("ginarea", {}).get("mode") == "PRIORITY_GRID" and final_quality == "NO_TRADE" else "DIRECTIONAL"
    atr_1h = _atr(candles_1h)
    sl_buffer = round(max(50.0, atr_1h * 0.5), 2)
    range_mid = _safe_float(snapshot.get("range_mid"))
    range_high = _safe_float(snapshot.get("range_high"))
    range_low = _safe_float(snapshot.get("range_low"))
    block_low = _safe_float(snapshot.get("block_low"))
    block_high = _safe_float(snapshot.get("block_high"))
    side = str(snapshot.get("active_side"))

    if mode == "GRID":
        return {
            "mode": mode,
            "entry_zone_low": round(block_low, 2),
            "entry_zone_high": round(block_high, 2),
            "profit_target_usd": 150 if snapshot.get("depth_label") in {"EARLY", "WORK"} else 90,
            "invalidation_level": round(range_high + sl_buffer, 2) if side == "SHORT" else round(range_low - sl_buffer, 2),
            "reduce_trigger": "REDUCE_GRID при усилении pressure против блока или уходе в RISK/DEEP",
            "grid_close_trigger": "confirmed breakout / смена режима / profit target",
            "lifecycle_mode": snapshot.get("ginarea", {}).get("lifecycle", "WAIT_GRID"),
        }

    if execution_profile == "AGGRESSIVE":
        entry_type = "MARKET"
    elif execution_profile == "STANDARD":
        entry_type = "LIMIT"
    elif execution_profile == "CONSERVATIVE":
        entry_type = "CONFIRMATION"
    else:
        entry_type = "LIMIT"

    if side == "SHORT":
        entry_zone_low = range_mid if execution_profile == "STANDARD" else max(block_low, block_high - (block_high - block_low) * 0.35)
        entry_zone_high = block_high
        tp1 = range_mid
        tp2 = range_low
        sl = block_high + sl_buffer
        invalidation = "закрепление выше блока"
    else:
        entry_zone_low = block_low
        entry_zone_high = range_mid if execution_profile == "STANDARD" else min(block_high, block_low + (block_high - block_low) * 0.35)
        tp1 = range_mid
        tp2 = range_high
        sl = block_low - sl_buffer
        invalidation = "закрепление ниже блока"

    be_trigger = None if execution_profile == "PROBE_ONLY" else 0.8 if execution_profile == "CONSERVATIVE" else 1.0
    management_mode = "DEFENSIVE" if execution_profile in {"CONSERVATIVE", "PROBE_ONLY"} else "INTRADAY"
    return {
        "mode": mode,
        "entry_zone_low": round(min(entry_zone_low, entry_zone_high), 2),
        "entry_zone_high": round(max(entry_zone_low, entry_zone_high), 2),
        "entry_type": entry_type,
        "entry_comment": "малый пробный вход у края" if execution_profile == "PROBE_ONLY" else "вход от блока после реакции",
        "tp1_price": round(tp1, 2),
        "tp2_price": round(tp2, 2),
        "tp_strategy": "PARTIAL + HOLD",
        "sl_price": round(sl, 2),
        "sl_buffer": sl_buffer,
        "invalidation_type": invalidation,
        "be_trigger_r": be_trigger,
        "partial_tp_r": 1.0,
        "management_mode": management_mode,
        "trade_plan_summary": f"{side} от активного блока, не входить в догонку",
    }


def _write_signal_journal(snapshot: Dict[str, Any]) -> None:
    cache = safe_read_json(str(SIGNAL_CACHE_FILE), {"signature": None, "ts": None})
    signature_payload = {
        "setup_key": snapshot.get("setup_key"),
        "action": snapshot.get("action"),
        "trigger_blocked": snapshot.get("trigger_blocked"),
        "context_label": snapshot.get("context_label"),
        "block_pressure": snapshot.get("block_pressure"),
        "entry_quality": snapshot.get("entry_quality"),
        "execution_profile": snapshot.get("execution_profile"),
    }
    signature = json.dumps(signature_payload, ensure_ascii=False, sort_keys=True)
    prev_sig = cache.get("signature")
    if prev_sig == signature:
        prev_ts = str(cache.get("ts") or "")
        try:
            prev_dt = datetime.fromisoformat(prev_ts)
            if (datetime.now(timezone.utc) - prev_dt).total_seconds() < SIGNAL_THROTTLE_SECONDS:
                return
        except Exception:
            pass
    row = {
        "timestamp": _now_iso(),
        "symbol": snapshot.get("symbol"),
        "tf": snapshot.get("tf"),
        "mode": "directional",
        "snapshot_id": f"{snapshot.get('symbol')}_{snapshot.get('timestamp')}_{snapshot.get('setup_key')}",
        "state": snapshot.get("state"),
        "active_block_side": snapshot.get("active_side"),
        "depth_label": snapshot.get("depth_label"),
        "depth_pct": snapshot.get("block_depth_pct"),
        "trigger_code": snapshot.get("trigger_type"),
        "trigger_detected": snapshot.get("trigger_detected"),
        "trigger_blocked": snapshot.get("trigger_blocked"),
        "trigger_block_reason_code": snapshot.get("trigger_block_reason_code"),
        "context_score": snapshot.get("context_score"),
        "context_label": snapshot.get("context_label"),
        "consensus_side": snapshot.get("consensus_direction"),
        "consensus_alignment": snapshot.get("consensus_votes"),
        "block_pressure": snapshot.get("block_pressure"),
        "block_pressure_strength": snapshot.get("block_pressure_strength"),
        "entry_quality": snapshot.get("entry_quality"),
        "execution_profile": snapshot.get("execution_profile"),
        "action": snapshot.get("action"),
        "trade_plan_type": snapshot.get("trade_plan", {}).get("mode"),
        "setup_key": snapshot.get("setup_key"),
    }
    _append_jsonl(SIGNAL_JOURNAL_FILE, row)
    atomic_write_json(str(SIGNAL_CACHE_FILE), {"signature": signature, "ts": _now_iso()})


def _update_setup_stats() -> None:
    rows = _read_jsonl(TRADE_OUTCOMES_FILE)
    stats: Dict[str, Any] = {}
    for row in rows:
        mode = str(row.get("mode") or "directional")
        key = str(row.get("setup_key") or "UNKNOWN")
        bucket = stats.setdefault(mode, {}).setdefault(key, {"count_total": 0, "sum_result_r": 0.0, "count_win": 0, "count_loss": 0, "count_flip_exit": 0, "count_be_saved": 0})
        bucket["count_total"] += 1
        rr = _safe_float(row.get("result_r"), 0.0)
        bucket["sum_result_r"] += rr
        if rr > 0:
            bucket["count_win"] += 1
        elif rr < 0:
            bucket["count_loss"] += 1
        if bool(row.get("flip_exit")):
            bucket["count_flip_exit"] += 1
        if bool(row.get("be_saved")):
            bucket["count_be_saved"] += 1
    for mode, mode_stats in stats.items():
        for key, bucket in mode_stats.items():
            n = max(bucket["count_total"], 1)
            bucket["avg_result_r"] = round(bucket["sum_result_r"] / n, 4)
            bucket["win_rate"] = round(bucket["count_win"] / n, 4)
            bucket["flip_exit_rate"] = round(bucket["count_flip_exit"] / n, 4)
            bucket["be_saved_rate"] = round(bucket["count_be_saved"] / n, 4)
    atomic_write_json(str(SETUP_STATS_FILE), stats)


def build_full_snapshot(symbol="BTCUSDT"):
    price = get_price(symbol)
    candles_1h = get_klines(symbol=symbol, interval="1h", limit=200)
    candles_4h = aggregate_to_4h(candles_1h)
    candles_1d = aggregate_to_1d(candles_1h)

    range_low, range_high, range_mid = _build_range(candles_1h)
    range_size = max(range_high - range_low, 1e-9)

    if price >= range_mid:
        active_side = "SHORT"
        active_block = "SHORT"
        block_low = range_mid
        block_high = range_high
        distance_to_upper_edge = range_high - price
        distance_to_lower_edge = price - range_low
        edge_distance_pct = max(0.0, ((block_high - price) / max(block_high - block_low, 1e-9)) * 100.0)
    else:
        active_side = "LONG"
        active_block = "LONG"
        block_low = range_low
        block_high = range_mid
        distance_to_upper_edge = range_high - price
        distance_to_lower_edge = price - range_low
        edge_distance_pct = max(0.0, ((price - block_low) / max(block_high - block_low, 1e-9)) * 100.0)

    block_size = max(block_high - block_low, 1e-9)
    block_depth_pct = ((price - block_low) / block_size) * 100.0
    range_position_pct = ((price - range_low) / range_size) * 100.0
    depth_label = _depth_label(block_depth_pct)

    trigger_confirmed, trigger_type, trigger_note = detect_trigger(candles_1h, active_block, range_low, range_high)
    trigger_detected = trigger_type is not None

    if price > range_high or price < range_low or block_depth_pct >= 100:
        state = "OVERRUN"
    elif trigger_confirmed:
        state = "CONFIRMED"
    elif edge_distance_pct <= NEAR_EDGE_THRESHOLD_PCT:
        state = "PRE_ACTIVATION"
    elif depth_label in ("WORK", "RISK", "DEEP"):
        state = "SEARCH_TRIGGER"
    else:
        state = "MID_RANGE"

    short_fc = short_term_forecast(candles_1h)
    session_fc = session_forecast(candles_4h)
    medium_fc = medium_forecast(candles_1d)
    consensus_direction, consensus_confidence, consensus_votes = build_consensus(short_fc, session_fc, medium_fc)
    consensus_votes = _consensus_alignment(consensus_votes)

    scalp_direction = str(short_fc.get("direction") or "NEUTRAL")
    context_score, context_label, context_details = _context_details(candles_1h, depth_label, scalp_direction, active_side)
    conflict_flag = consensus_direction in ("LONG", "SHORT") and consensus_direction != active_side
    block_pressure, block_pressure_strength, block_flip_warning, block_pressure_reason = _block_pressure(active_side, consensus_direction, consensus_votes, session_fc, medium_fc)

    trigger_blocked = False
    trigger_block_reason_code = None
    trigger_block_reason_text = None
    primary_blocker = None
    secondary_factors: List[str] = []
    context_risks: List[str] = []

    if block_pressure == "AGAINST" and context_score != 3 and trigger_detected:
        trigger_blocked = True
        trigger_block_reason_code = "PRESSURE_AGAINST_BLOCK"
        trigger_block_reason_text = "давление против блока"
        primary_blocker = "давление против блока"
    elif conflict_flag and trigger_detected and context_score == 0:
        trigger_blocked = True
        trigger_block_reason_code = "FORECAST_AGAINST_BLOCK"
        trigger_block_reason_text = "forecast против активного блока"
        primary_blocker = "forecast против активного блока"
    elif trigger_detected and context_score == 0:
        trigger_blocked = True
        trigger_block_reason_code = "NO_VALID_TRIGGER_CONTEXT"
        trigger_block_reason_text = "нет рабочего контекста"
        primary_blocker = "нет рабочего контекста"

    if conflict_flag and primary_blocker != "forecast против активного блока":
        secondary_factors.append("forecast против активного блока")
    if scalp_direction != active_side:
        secondary_factors.append("скальп против активного блока" if scalp_direction != "NEUTRAL" else "скальп не подтверждает — краткосрочного импульса нет")
    if context_score == 1 and not primary_blocker:
        secondary_factors.append("только 1 из 3 условий выполнено")
    if range_position_pct > 80:
        context_risks.append("край диапазона — повышенный риск резкого выноса")
    if block_depth_pct > 65:
        context_risks.append("глубоко в зоне — риск прошивки")
    if block_flip_warning:
        context_risks.insert(0, block_pressure_reason)

    if state == "OVERRUN":
        action = "PROTECT"
        entry_type = None
    elif trigger_confirmed and not trigger_blocked:
        action = "ENTER"
        entry_type = "ENTER"
    elif trigger_detected and not trigger_blocked and context_score >= 1:
        action = "PREPARE"
        entry_type = "PROBE" if context_score == 1 else "PREPARE"
    elif state == "PRE_ACTIVATION" and context_score >= 1 and not conflict_flag:
        action = "PREPARE"
        entry_type = "PROBE"
    else:
        action = "WAIT"
        entry_type = None

    hedge_state = "OFF"
    if block_depth_pct > 60:
        hedge_state = "PRE-TRIGGER"
    elif state in ("SEARCH_TRIGGER", "PRE_ACTIVATION"):
        hedge_state = "ARM"
    elif state == "OVERRUN":
        hedge_state = "TRIGGER"

    forecast_relation = "NEUTRAL"
    if consensus_direction == active_side:
        forecast_relation = "ALIGNED"
    elif consensus_direction in {"LONG", "SHORT"} and consensus_direction != active_side:
        forecast_relation = "AGAINST"

    raw_entry_quality, _raw_profile, _risk_mode, _partial_allowed, _scale_allowed = _entry_quality_and_profile(
        action, context_score, depth_label, trigger_detected, trigger_confirmed, trigger_blocked, forecast_relation, block_pressure, block_pressure_strength
    )

    setup_key = _setup_key(active_side, trigger_type or "NONE", depth_label, context_label)
    feedback_stats = _load_feedback_stats("directional", setup_key)
    feedback = _feedback_from_stats(feedback_stats, block_pressure, block_pressure_strength, raw_entry_quality)
    final_entry_quality = _adjust_quality(raw_entry_quality, int(feedback.get("delta") or 0), block_pressure, block_pressure_strength)
    entry_quality, execution_profile, risk_mode, partial_entry_allowed, scale_in_allowed = _entry_quality_and_profile(
        action if final_entry_quality != "NO_TRADE" else "WAIT", context_score, depth_label, trigger_detected, trigger_confirmed, trigger_blocked, forecast_relation, block_pressure, block_pressure_strength
    )
    if final_entry_quality != entry_quality and final_entry_quality in {"A", "B", "C", "NO_TRADE"}:
        entry_quality = final_entry_quality
        if entry_quality == "NO_TRADE":
            execution_profile = "NO_ENTRY"
            risk_mode = "MINIMAL"
            partial_entry_allowed = False
            scale_in_allowed = False

    trade_plan = _trade_plan({
        "ginarea": {"mode": "PRIORITY_GRID" if entry_quality == "NO_TRADE" else "DIRECTIONAL"},
        "depth_label": depth_label,
        "range_mid": range_mid,
        "range_high": range_high,
        "range_low": range_low,
        "block_low": block_low,
        "block_high": block_high,
        "active_side": active_side,
    }, candles_1h, execution_profile, entry_quality)

    ginarea = {
        "mode": "PRIORITY_GRID",
        "long_grid": "REDUCE" if active_side == "SHORT" else "WORK",
        "short_grid": "WORK" if active_side == "SHORT" else "REDUCE",
        "aggression": "LOW" if action != "ENTER" else "MID",
        "lifecycle": "REDUCE_GRID" if depth_label in ("RISK", "DEEP") else "ARM_GRID" if state in ("SEARCH_TRIGGER", "PRE_ACTIVATION") else "WAIT_GRID",
    }

    snapshot = {
        "version": PROJECT_VERSION_FILE.read_text(encoding="utf-8").strip() if PROJECT_VERSION_FILE.exists() else "V17.8.8.6",
        "symbol": symbol,
        "timestamp": datetime.now().strftime("%H:%M"),
        "tf": "1h",
        "price": round(price, 2),
        "range_low": round(range_low, 2),
        "range_high": round(range_high, 2),
        "range_mid": round(range_mid, 2),
        "range_position_pct": round(range_position_pct, 2),
        "active_block": active_block,
        "active_side": active_side,
        "block_low": round(block_low, 2),
        "block_high": round(block_high, 2),
        "block_depth_pct": round(block_depth_pct, 2),
        "depth_label": depth_label,
        "distance_to_upper_edge": round(distance_to_upper_edge, 2),
        "distance_to_lower_edge": round(distance_to_lower_edge, 2),
        "edge_distance_pct": round(edge_distance_pct, 2),
        "state": state,
        "trigger": trigger_confirmed,
        "trigger_detected": trigger_detected,
        "trigger_type": trigger_type,
        "trigger_note": trigger_note,
        "trigger_blocked": trigger_blocked,
        "trigger_block_reason_code": trigger_block_reason_code,
        "trigger_block_reason_text": trigger_block_reason_text,
        "action": action,
        "entry_type": entry_type,
        "hedge_state": hedge_state,
        "hedge_arm_up": round(range_high + HEDGE_BUFFER_USD, 2),
        "hedge_arm_down": round(range_low - HEDGE_BUFFER_USD, 2),
        "forecast": {
            "short": short_fc,
            "session": session_fc,
            "medium": medium_fc,
        },
        "consensus_direction": consensus_direction,
        "consensus_confidence": consensus_confidence,
        "consensus_votes": consensus_votes,
        "execution_side": active_side,
        "execution_confidence": "LOW" if conflict_flag else consensus_confidence,
        "conflict_flag": conflict_flag,
        "warnings": secondary_factors + context_risks,
        "primary_blocker": primary_blocker,
        "secondary_factors": secondary_factors,
        "context_risks": context_risks,
        "context_score": context_score,
        "context_label": context_label,
        "context_details": context_details,
        "block_pressure": block_pressure,
        "block_pressure_strength": block_pressure_strength,
        "block_flip_warning": block_flip_warning,
        "block_pressure_reason": block_pressure_reason,
        "forecast_relation": forecast_relation,
        "setup_key": setup_key,
        "feedback": feedback,
        "feedback_stats": feedback_stats,
        "entry_quality": entry_quality,
        "execution_profile": execution_profile,
        "entry_risk_mode": risk_mode,
        "partial_entry_allowed": partial_entry_allowed,
        "scale_in_allowed": scale_in_allowed if depth_label not in {"RISK", "DEEP"} and block_depth_pct <= 70 else False,
        "trade_plan": trade_plan,
        "ginarea": ginarea,
    }

    _write_signal_journal(snapshot)
    _update_setup_stats()
    return snapshot
