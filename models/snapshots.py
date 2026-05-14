from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


ALLOWED_ANALYSIS_DECISION_KEYS = {
    "direction",
    "direction_text",
    "action",
    "action_text",
    "manager_action",
    "manager_action_text",
    "mode",
    "regime",
    "confidence",
    "confidence_pct",
    "risk",
    "risk_level",
    "summary",
    "long_score",
    "short_score",
    "pressure_reason",
    "entry_reason",
    "invalidation",
    "active_bot",
    "range_position",
    "range_position_zone",
    "expectation",
    "expectation_text",
    "reasons",
    "mode_reasons",
    "market_state",
    "market_state_text",
    "setup_status",
    "setup_status_text",
    "late_entry_risk",
    "location_quality",
    "entry_type",
    "execution_mode",
    "no_trade_reason",
    "trap_risk",
    "breakout_risk",
    "soft_signal",
}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ("true", "1", "yes", "y", "on"):
            return True
        if v in ("false", "0", "no", "n", "off"):
            return False
    try:
        return bool(value)
    except Exception:
        return default


def _safe_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _safe_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def _sanitize_decision_like(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, DecisionSnapshot):
        raw = value.to_dict()
        return raw if isinstance(raw, dict) else {}
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for key, item in value.items():
            if key not in ALLOWED_ANALYSIS_DECISION_KEYS:
                continue
            if key == "decision":
                continue
            if isinstance(item, dict):
                out[key] = dict(item)
            elif isinstance(item, list):
                out[key] = list(item)
            elif hasattr(item, "to_dict") and not isinstance(item, (str, bytes)):
                try:
                    out[key] = item.to_dict()
                except Exception:
                    out[key] = _safe_str(item)
            else:
                out[key] = item
        return out
    if hasattr(value, "to_dict") and not isinstance(value, (str, bytes)):
        try:
            raw = value.to_dict()
        except Exception:
            return {}
        if raw is value or not isinstance(raw, dict):
            return {}
        return _sanitize_decision_like(raw)
    return {}


def _sanitize_analysis_dict(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    out: Dict[str, Any] = {}
    for key, item in value.items():
        if key == "decision":
            # decision живёт только в snapshot.decision, а не внутри analysis
            continue
        if item is value:
            continue
        if isinstance(item, dict):
            if item.get("analysis") is value:
                item = dict(item)
                item.pop("analysis", None)
            out[key] = dict(item)
        elif isinstance(item, list):
            out[key] = list(item)
        elif hasattr(item, "to_dict") and not isinstance(item, (str, bytes)):
            try:
                out[key] = item.to_dict()
            except Exception:
                out[key] = _safe_str(item)
        else:
            out[key] = item
    return out


@dataclass
class RangeSnapshot:
    low: float = 0.0
    mid: float = 0.0
    high: float = 0.0

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "RangeSnapshot":
        data = data or {}
        return cls(
            low=_safe_float(data.get("low")),
            mid=_safe_float(data.get("mid")),
            high=_safe_float(data.get("high")),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {"low": self.low, "mid": self.mid, "high": self.high}


@dataclass
class DecisionSnapshot:
    direction: str = "NEUTRAL"
    direction_text: str = "НЕЙТРАЛЬНО"
    action: str = "WAIT"
    action_text: str = "ЖДАТЬ"
    manager_action: str = "WAIT"
    manager_action_text: str = "ЖДАТЬ"
    mode: str = "MIXED"
    regime: str = "MIXED"
    confidence: float = 0.0
    confidence_pct: float = 0.0
    risk: str = "HIGH"
    risk_level: str = "HIGH"
    summary: str = ""
    long_score: float = 0.0
    short_score: float = 0.0
    pressure_reason: str = ""
    entry_reason: str = ""
    invalidation: str = ""
    active_bot: str = "none"
    range_position: str = "UNKNOWN"
    range_position_zone: str = "позиция в диапазоне не определена"
    expectation: List[str] = field(default_factory=list)
    expectation_text: str = ""
    reasons: List[str] = field(default_factory=list)
    mode_reasons: List[str] = field(default_factory=list)
    market_state: str = "UNKNOWN"
    market_state_text: str = "НЕДОСТАТОЧНО ДАННЫХ"
    setup_status: str = "WAIT"
    setup_status_text: str = "ЖДАТЬ"
    late_entry_risk: str = "HIGH"
    location_quality: str = "C"
    entry_type: str = "no_trade"
    execution_mode: str = "conservative"
    no_trade_reason: str = ""
    trap_risk: str = "MEDIUM"
    breakout_risk: str = "LOW"
    false_break_signal: str = "NONE"
    trap_comment: str = ""
    edge_bias: str = "NONE"
    edge_score: float = 0.0
    soft_signal: Dict[str, Any] = field(default_factory=dict)
    fake_move_detector: Dict[str, Any] = field(default_factory=dict)
    move_projection: Dict[str, Any] = field(default_factory=dict)
    move_type_context: Dict[str, Any] = field(default_factory=dict)
    bot_mode_context: Dict[str, Any] = field(default_factory=dict)
    range_bot_permission: Dict[str, Any] = field(default_factory=dict)
    action_output: Dict[str, Any] = field(default_factory=dict)
    bot_mode_action: str = "OFF"
    directional_action: str = "WAIT"
    best_trade_play: str = "wait"
    best_trade_side: str = "FLAT"
    best_trade_score: float = 0.0
    execution_verdict: Dict[str, Any] = field(default_factory=dict)
    top_plays: List[Any] = field(default_factory=list)
    avoid_plays: List[Any] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "DecisionSnapshot":
        data = _sanitize_decision_like(data)
        expectation = [_safe_str(x) for x in _safe_list(data.get("expectation")) if _safe_str(x)]
        return cls(
            direction=_safe_str(data.get("direction"), "NEUTRAL"),
            direction_text=_safe_str(data.get("direction_text"), "НЕЙТРАЛЬНО"),
            action=_safe_str(data.get("action"), "WAIT"),
            action_text=_safe_str(data.get("action_text"), "ЖДАТЬ"),
            manager_action=_safe_str(data.get("manager_action"), _safe_str(data.get("action"), "WAIT")),
            manager_action_text=_safe_str(data.get("manager_action_text"), _safe_str(data.get("action_text"), "ЖДАТЬ")),
            mode=_safe_str(data.get("mode"), "MIXED"),
            regime=_safe_str(data.get("regime"), _safe_str(data.get("mode"), "MIXED")),
            confidence=_safe_float(data.get("confidence")),
            confidence_pct=_safe_float(data.get("confidence_pct") or data.get("confidence")),
            risk=_safe_str(data.get("risk"), "HIGH"),
            risk_level=_safe_str(data.get("risk_level"), _safe_str(data.get("risk"), "HIGH")),
            summary=_safe_str(data.get("summary")),
            long_score=_safe_float(data.get("long_score")),
            short_score=_safe_float(data.get("short_score")),
            pressure_reason=_safe_str(data.get("pressure_reason")),
            entry_reason=_safe_str(data.get("entry_reason")),
            invalidation=_safe_str(data.get("invalidation")),
            active_bot=_safe_str(data.get("active_bot"), "none"),
            range_position=_safe_str(data.get("range_position"), "UNKNOWN"),
            range_position_zone=_safe_str(data.get("range_position_zone"), "позиция в диапазоне не определена"),
            expectation=expectation,
            expectation_text=_safe_str(data.get("expectation_text"), expectation[0] if expectation else ""),
            reasons=[_safe_str(x) for x in _safe_list(data.get("reasons")) if _safe_str(x)],
            mode_reasons=[_safe_str(x) for x in _safe_list(data.get("mode_reasons")) if _safe_str(x)],
            market_state=_safe_str(data.get("market_state"), "UNKNOWN"),
            market_state_text=_safe_str(data.get("market_state_text"), "НЕДОСТАТОЧНО ДАННЫХ"),
            setup_status=_safe_str(data.get("setup_status"), "WAIT"),
            setup_status_text=_safe_str(data.get("setup_status_text"), "ЖДАТЬ"),
            late_entry_risk=_safe_str(data.get("late_entry_risk"), "HIGH"),
            location_quality=_safe_str(data.get("location_quality"), "C"),
            entry_type=_safe_str(data.get("entry_type"), "no_trade"),
            execution_mode=_safe_str(data.get("execution_mode"), "conservative"),
            no_trade_reason=_safe_str(data.get("no_trade_reason")),
            trap_risk=_safe_str(data.get("trap_risk"), "MEDIUM"),
            breakout_risk=_safe_str(data.get("breakout_risk"), "LOW"),
            false_break_signal=_safe_str(data.get("false_break_signal"), "NONE"),
            trap_comment=_safe_str(data.get("trap_comment")),
            edge_bias=_safe_str(data.get("edge_bias"), "NONE"),
            edge_score=_safe_float(data.get("edge_score")),
            soft_signal=data.get('soft_signal') if isinstance(data.get('soft_signal'), dict) else {},
            fake_move_detector=data.get('fake_move_detector') if isinstance(data.get('fake_move_detector'), dict) else {},
            move_projection=data.get('move_projection') if isinstance(data.get('move_projection'), dict) else {},
            move_type_context=data.get('move_type_context') if isinstance(data.get('move_type_context'), dict) else {},
            bot_mode_context=data.get('bot_mode_context') if isinstance(data.get('bot_mode_context'), dict) else {},
            range_bot_permission=data.get('range_bot_permission') if isinstance(data.get('range_bot_permission'), dict) else {},
            action_output=data.get('action_output') if isinstance(data.get('action_output'), dict) else {},
            bot_mode_action=_safe_str(data.get('bot_mode_action'), 'OFF'),
            directional_action=_safe_str(data.get('directional_action'), _safe_str(data.get('action'), 'WAIT')),
            best_trade_play=_safe_str(data.get('best_trade_play'), 'wait'),
            best_trade_side=_safe_str(data.get('best_trade_side'), 'FLAT'),
            best_trade_score=_safe_float(data.get('best_trade_score')),
            execution_verdict=data.get('execution_verdict') if isinstance(data.get('execution_verdict'), dict) else {},
            top_plays=[x for x in _safe_list(data.get('top_plays'))],
            avoid_plays=[x for x in _safe_list(data.get('avoid_plays'))],
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "direction": self.direction,
            "direction_text": self.direction_text,
            "action": self.action,
            "action_text": self.action_text,
            "manager_action": self.manager_action,
            "manager_action_text": self.manager_action_text,
            "mode": self.mode,
            "regime": self.regime,
            "confidence": self.confidence,
            "confidence_pct": self.confidence_pct,
            "risk": self.risk,
            "risk_level": self.risk_level,
            "summary": self.summary,
            "long_score": self.long_score,
            "short_score": self.short_score,
            "pressure_reason": self.pressure_reason,
            "entry_reason": self.entry_reason,
            "invalidation": self.invalidation,
            "active_bot": self.active_bot,
            "range_position": self.range_position,
            "range_position_zone": self.range_position_zone,
            "expectation": list(self.expectation),
            "expectation_text": self.expectation_text,
            "reasons": list(self.reasons),
            "mode_reasons": list(self.mode_reasons),
            "market_state": self.market_state,
            "market_state_text": self.market_state_text,
            "setup_status": self.setup_status,
            "setup_status_text": self.setup_status_text,
            "late_entry_risk": self.late_entry_risk,
            "location_quality": self.location_quality,
            "entry_type": self.entry_type,
            "execution_mode": self.execution_mode,
            "no_trade_reason": self.no_trade_reason,
            "trap_risk": self.trap_risk,
            "breakout_risk": self.breakout_risk,
            "false_break_signal": self.false_break_signal,
            "trap_comment": self.trap_comment,
            "edge_bias": self.edge_bias,
            "edge_score": self.edge_score,
            "soft_signal": dict(self.soft_signal or {}),
            "fake_move_detector": dict(self.fake_move_detector or {}),
            "move_projection": dict(self.move_projection or {}),
            "move_type_context": dict(self.move_type_context or {}),
            "bot_mode_context": dict(self.bot_mode_context or {}),
            "range_bot_permission": dict(self.range_bot_permission or {}),
            "action_output": dict(self.action_output or {}),
            "bot_mode_action": self.bot_mode_action,
            "directional_action": self.directional_action,
            "best_trade_play": self.best_trade_play,
            "best_trade_side": self.best_trade_side,
            "best_trade_score": self.best_trade_score,
            "execution_verdict": dict(self.execution_verdict or {}),
            "top_plays": list(self.top_plays),
            "avoid_plays": list(self.avoid_plays),
        }


@dataclass
class AnalysisSnapshot:
    symbol: str = "BTCUSDT"
    timeframe: str = "1h"
    price: float = 0.0
    signal: str = "НЕЙТРАЛЬНО"
    final_decision: str = "НЕЙТРАЛЬНО"
    forecast_direction: str = "НЕЙТРАЛЬНО"
    forecast_confidence: float = 0.0
    reversal_signal: str = "NO_REVERSAL"
    reversal_confidence: float = 0.0
    reversal_patterns: List[str] = field(default_factory=list)
    history_pattern_direction: str = "NEUTRAL"
    history_pattern_confidence: float = 0.0
    history_pattern_summary: str = ""
    history_pattern_matches: int = 0
    pattern_memory_v2: Dict[str, Any] = field(default_factory=dict)
    pattern_forecast_direction: str = "НЕЙТРАЛЬНО"
    pattern_forecast_confidence: float = 0.0
    pattern_forecast_strength: str = "NEUTRAL"
    pattern_forecast_move: str = ""
    pattern_forecast_regime: str = ""
    pattern_forecast_style: str = ""
    pattern_scope: str = "recent_multi_cycle"
    pattern_years: List[Any] = field(default_factory=list)
    grid_strategy: Dict[str, Any] = field(default_factory=dict)
    grid_active_bots: List[str] = field(default_factory=list)
    grid_summary: str = ""
    range_state: str = "нет данных"
    range_position: str = "UNKNOWN"
    ct_now: str = "контртренд: явного перекоса нет"
    ginarea_advice: str = "нет данных"
    decision_summary: str = ""
    range: RangeSnapshot = field(default_factory=RangeSnapshot)
    decision: DecisionSnapshot = field(default_factory=DecisionSnapshot)
    stats: Dict[str, Any] = field(default_factory=dict)
    df: Any = None
    analysis: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]], *, symbol: Optional[str] = None, timeframe: str = "1h") -> "AnalysisSnapshot":
        data = data or {}
        range_dict = data.get("range")
        if not isinstance(range_dict, dict):
            range_dict = {
                "low": data.get("range_low"),
                "mid": data.get("range_mid"),
                "high": data.get("range_high"),
            }
        decision_dict = _sanitize_decision_like(data.get("decision"))
        return cls(
            symbol=_safe_str(symbol or data.get("symbol"), "BTCUSDT"),
            timeframe=_safe_str(data.get("timeframe"), timeframe),
            price=_safe_float(data.get("price")),
            signal=_safe_str(data.get("signal"), "НЕЙТРАЛЬНО"),
            final_decision=_safe_str(data.get("final_decision"), "НЕЙТРАЛЬНО"),
            forecast_direction=_safe_str(data.get("forecast_direction"), "НЕЙТРАЛЬНО"),
            forecast_confidence=_safe_float(data.get("forecast_confidence")),
            reversal_signal=_safe_str(data.get("reversal_signal"), "NO_REVERSAL"),
            reversal_confidence=_safe_float(data.get("reversal_confidence")),
            reversal_patterns=[_safe_str(x) for x in _safe_list(data.get("reversal_patterns")) if _safe_str(x)],
            history_pattern_direction=_safe_str(data.get("history_pattern_direction"), "NEUTRAL"),
            history_pattern_confidence=_safe_float(data.get("history_pattern_confidence")),
            history_pattern_summary=_safe_str(data.get("history_pattern_summary")),
            history_pattern_matches=int(_safe_float(data.get("history_pattern_matches"), 0.0)),
            pattern_memory_v2=data.get("pattern_memory_v2") if isinstance(data.get("pattern_memory_v2"), dict) else {},
            pattern_forecast_direction=_safe_str(data.get("pattern_forecast_direction"), "НЕЙТРАЛЬНО"),
            pattern_forecast_confidence=_safe_float(data.get("pattern_forecast_confidence")),
            pattern_forecast_strength=_safe_str(data.get("pattern_forecast_strength"), "NEUTRAL"),
            pattern_forecast_move=_safe_str(data.get("pattern_forecast_move")),
            pattern_forecast_regime=_safe_str(data.get("pattern_forecast_regime")),
            pattern_forecast_style=_safe_str(data.get("pattern_forecast_style")),
            pattern_scope=_safe_str(data.get("pattern_scope"), "recent_multi_cycle"),
            pattern_years=list(data.get("pattern_years") or []),
            grid_strategy=data.get("grid_strategy") if isinstance(data.get("grid_strategy"), dict) else {},
            grid_active_bots=[_safe_str(x) for x in _safe_list(data.get("grid_active_bots")) if _safe_str(x)],
            grid_summary=_safe_str(data.get("grid_summary")),
            range_state=_safe_str(data.get("range_state"), "нет данных"),
            range_position=_safe_str(data.get("range_position") or decision_dict.get("range_position"), "UNKNOWN"),
            ct_now=_safe_str(data.get("ct_now"), "контртренд: явного перекоса нет"),
            ginarea_advice=_safe_str(data.get("ginarea_advice"), "нет данных"),
            decision_summary=_safe_str(data.get("decision_summary")),
            range=RangeSnapshot.from_dict(range_dict),
            decision=DecisionSnapshot.from_dict(decision_dict),
            stats=data.get("stats") if isinstance(data.get("stats"), dict) else {},
            df=data.get("df"),
            analysis=_sanitize_analysis_dict(data.get("analysis")),
        )

    def to_dict(self) -> Dict[str, Any]:
        decision_dict = DecisionSnapshot.from_dict(self.decision).to_dict()
        analysis_dict = _sanitize_analysis_dict(self.analysis)
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "price": self.price,
            "signal": self.signal,
            "final_decision": self.final_decision,
            "forecast_direction": self.forecast_direction,
            "forecast_confidence": self.forecast_confidence,
            "reversal_signal": self.reversal_signal,
            "reversal_confidence": self.reversal_confidence,
            "reversal_patterns": list(self.reversal_patterns),
            "history_pattern_direction": self.history_pattern_direction,
            "history_pattern_confidence": self.history_pattern_confidence,
            "history_pattern_summary": self.history_pattern_summary,
            "history_pattern_matches": self.history_pattern_matches,
            "pattern_memory_v2": dict(self.pattern_memory_v2 or {}),
            "pattern_forecast_direction": self.pattern_forecast_direction,
            "pattern_forecast_confidence": self.pattern_forecast_confidence,
            "pattern_forecast_strength": self.pattern_forecast_strength,
            "pattern_forecast_move": self.pattern_forecast_move,
            "pattern_forecast_regime": self.pattern_forecast_regime,
            "pattern_forecast_style": self.pattern_forecast_style,
            "pattern_scope": self.pattern_scope,
            "pattern_years": list(self.pattern_years),
            "grid_strategy": dict(self.grid_strategy or {}),
            "grid_active_bots": list(self.grid_active_bots),
            "grid_summary": self.grid_summary,
            "range_state": self.range_state,
            "range_position": self.range_position,
            "ct_now": self.ct_now,
            "ginarea_advice": self.ginarea_advice,
            "decision_summary": self.decision_summary or decision_dict.get("summary", ""),
            "range_low": self.range.low,
            "range_mid": self.range.mid,
            "range_high": self.range.high,
            "range": self.range.to_dict(),
            "decision": decision_dict,
            "stats": dict(self.stats or {}),
            "analysis": analysis_dict,
            "df": self.df,
        }


@dataclass
class JournalSnapshot:
    trade_id: str = ""
    symbol: str = "BTCUSDT"
    side: str = ""
    timeframe: str = "1h"
    entry_price: float = 0.0
    opened_at: str = ""
    status: str = ""
    tp1_hit: bool = False
    tp2_hit: bool = False
    be_moved: bool = False
    partial_exit_done: bool = False
    closed: bool = False
    closed_at: str = ""
    close_reason: str = ""
    exit_price: float = 0.0
    result_pct: Optional[float] = None
    result_rr: Optional[float] = None
    holding_time_minutes: Optional[int] = None
    exit_quality: str = ""
    exit_reason_classifier: str = ""
    post_trade_summary: str = ""
    notes: str = ""
    lifecycle_state: str = "NO_TRADE"
    runner_active: bool = False
    lifecycle_history: List[Dict[str, Any]] = field(default_factory=list)
    has_active_trade: bool = False
    active: bool = False
    decision_snapshot: DecisionSnapshot = field(default_factory=DecisionSnapshot)
    analysis_snapshot: AnalysisSnapshot = field(default_factory=AnalysisSnapshot)
    close_context_snapshot: AnalysisSnapshot = field(default_factory=AnalysisSnapshot)

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "JournalSnapshot":
        data = data or {}
        has_active_trade = _safe_bool(data.get("has_active_trade"), _safe_bool(data.get("active")))
        return cls(
            trade_id=_safe_str(data.get("trade_id")),
            symbol=_safe_str(data.get("symbol"), "BTCUSDT"),
            side=_safe_str(data.get("side")),
            timeframe=_safe_str(data.get("timeframe"), "1h"),
            entry_price=_safe_float(data.get("entry_price")),
            opened_at=_safe_str(data.get("opened_at")),
            status=_safe_str(data.get("status")),
            tp1_hit=_safe_bool(data.get("tp1_hit")),
            tp2_hit=_safe_bool(data.get("tp2_hit")),
            be_moved=_safe_bool(data.get("be_moved")),
            partial_exit_done=_safe_bool(data.get("partial_exit_done")),
            closed=_safe_bool(data.get("closed")),
            closed_at=_safe_str(data.get("closed_at")),
            close_reason=_safe_str(data.get("close_reason")),
            exit_price=_safe_float(data.get("exit_price")),
            result_pct=data.get("result_pct"),
            result_rr=data.get("result_rr"),
            holding_time_minutes=data.get("holding_time_minutes"),
            exit_quality=_safe_str(data.get("exit_quality")),
            exit_reason_classifier=_safe_str(data.get("exit_reason_classifier")),
            post_trade_summary=_safe_str(data.get("post_trade_summary")),
            notes=_safe_str(data.get("notes")),
            lifecycle_state=_safe_str(data.get("lifecycle_state"), "NO_TRADE"),
            runner_active=_safe_bool(data.get("runner_active")),
            lifecycle_history=[item for item in _safe_list(data.get("lifecycle_history")) if isinstance(item, dict)],
            has_active_trade=has_active_trade,
            active=has_active_trade,
            decision_snapshot=DecisionSnapshot.from_dict(data.get("decision_snapshot") or {}),
            analysis_snapshot=AnalysisSnapshot.from_dict(data.get("analysis_snapshot") or {}, symbol=_safe_str(data.get("symbol"), "BTCUSDT"), timeframe=_safe_str(data.get("timeframe"), "1h")),
            close_context_snapshot=AnalysisSnapshot.from_dict(data.get("close_context_snapshot") or {}, symbol=_safe_str(data.get("symbol"), "BTCUSDT"), timeframe=_safe_str(data.get("timeframe"), "1h")),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "side": self.side,
            "timeframe": self.timeframe,
            "entry_price": self.entry_price,
            "opened_at": self.opened_at,
            "status": self.status,
            "tp1_hit": self.tp1_hit,
            "tp2_hit": self.tp2_hit,
            "be_moved": self.be_moved,
            "partial_exit_done": self.partial_exit_done,
            "closed": self.closed,
            "closed_at": self.closed_at,
            "close_reason": self.close_reason,
            "exit_price": self.exit_price,
            "result_pct": self.result_pct,
            "result_rr": self.result_rr,
            "holding_time_minutes": self.holding_time_minutes,
            "exit_quality": self.exit_quality,
            "exit_reason_classifier": self.exit_reason_classifier,
            "post_trade_summary": self.post_trade_summary,
            "notes": self.notes,
            "lifecycle_state": self.lifecycle_state,
            "runner_active": self.runner_active,
            "lifecycle_history": list(self.lifecycle_history),
            "has_active_trade": self.has_active_trade,
            "active": self.active,
            "decision_snapshot": self.decision_snapshot.to_dict(),
            "analysis_snapshot": self.analysis_snapshot.to_dict(),
            "close_context_snapshot": self.close_context_snapshot.to_dict(),
        }


@dataclass
class PositionSnapshot:
    has_position: bool = False
    side: str = ""
    symbol: str = "BTCUSDT"
    timeframe: str = "1h"
    entry_price: float = 0.0
    opened_at: str = ""
    comment: str = ""

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "PositionSnapshot":
        data = data or {}
        return cls(
            has_position=_safe_bool(data.get("has_position")),
            side=_safe_str(data.get("side")),
            symbol=_safe_str(data.get("symbol"), "BTCUSDT"),
            timeframe=_safe_str(data.get("timeframe"), "1h"),
            entry_price=_safe_float(data.get("entry_price")),
            opened_at=_safe_str(data.get("opened_at")),
            comment=_safe_str(data.get("comment")),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "has_position": self.has_position,
            "side": self.side,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "entry_price": self.entry_price,
            "opened_at": self.opened_at,
            "comment": self.comment,
        }
